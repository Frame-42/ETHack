"""Stufe 04: der kanonische Datensatz -- eine Zeile je Firma und Jahr.

Ab hier kennt die Bewertungslogik keine Datenquellen mehr, nur noch Spalten.
Jede Kennzahl traegt ihre Herkunft und ihre Konfidenz mit.

Die Kennzahlen der Kernnote (Achse A) messen ausschliesslich physische
Ergebnisse:

``co2_intensity``      Scope-1-Tonnen je Million USD Umsatz
``intensity_cagr``     jaehrliche Veraenderung der Intensitaet
``absolute_cagr``      jaehrliche Veraenderung der absoluten Tonnen

Die dritte Kennzahl ist kein Beiwerk. Die UN kritisiert ausdruecklich, dass
eine Firma ihre Intensitaet senken und trotzdem absolut mehr ausstossen kann,
wenn sie schnell genug waechst. Wer nur Intensitaet misst, belohnt genau das.

Achse B (Greenwashing) wird getrennt berechnet und nie in die Kernnote
eingerechnet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RAW
from .resolve import resolve_owners


def _cagr(values: pd.Series, years: pd.Series) -> float:
    """Jaehrliche Wachstumsrate ueber log-lineare Regression.

    Robuster als Endpunkt-durch-Anfangspunkt, weil ein einzelnes Ausreisserjahr
    das Ergebnis nicht allein bestimmt.
    """
    v = pd.to_numeric(values, errors="coerce")
    y = pd.to_numeric(years, errors="coerce")
    mask = np.isfinite(v) & np.isfinite(y) & (v > 0)
    if mask.sum() < 3:
        return np.nan
    slope = np.polyfit(y[mask], np.log(v[mask]), 1)[0]
    return float(np.exp(slope) - 1.0)


def load_raw() -> dict[str, pd.DataFrame]:
    out = {}
    for name in ("sp500_master", "epa_facility", "epa_emission", "sec_revenue", "esg_snapshot"):
        path = RAW / f"{name}.parquet"
        out[name] = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    return out


def build_company_year(raw: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    """Baut die Firma-Jahr-Tabelle und gibt Diagnosekennzahlen zurueck."""
    master = raw["sp500_master"]
    fac = raw["epa_facility"]
    emi = raw["epa_emission"]
    rev = raw["sec_revenue"]

    facilities = fac.merge(emi, on=["facility_id", "year"], how="inner")
    # Eine gemeldete 0 heisst bei der EPA fast nie "emissionsfrei", sondern
    # "keine Menge gemeldet": Die Anlage bleibt im Stammsatz stehen, auch wenn
    # sie nach der Aussteigeregel (40 CFR 98.2(i), unter 25 kt) nicht mehr
    # melden muss. Als 0 verrechnet macht das Firmen sauberer und erzeugt
    # Trends, die nur das Meldeverhalten abbilden -- deshalb fehlend fuehren.
    n_zero = int((facilities["scope1_t"].fillna(0) <= 0).sum())
    facilities = facilities[facilities["scope1_t"] > 0]
    total_emissions = facilities["scope1_t"].sum()

    owners = resolve_owners(facilities, master)
    alloc = facilities.merge(owners, on=["facility_id", "year"], how="inner")
    alloc["scope1_attributed_t"] = alloc["scope1_t"] * alloc["share"]

    matched_emissions = alloc["scope1_attributed_t"].sum()

    company_year = (
        alloc.groupby(["ticker", "year"], as_index=False)
        .agg(
            scope1_t=("scope1_attributed_t", "sum"),
            n_facilities=("facility_id", "nunique"),
            match_confidence=("match_confidence", "mean"),
        )
    )

    # Jahre mit erkennbar unvollstaendiger Zuordnung entfernen. PPL hatte 2018
    # eine einzige zugeordnete Anlage mit 5 kt, ab 2019 neun Anlagen mit 28 Mt:
    # Der Sprung misst die Zuordnung, nicht das Verhalten der Firma. Kriterium
    # ist beides zusammen -- viel weniger Anlagen als sonst *und* ein Bruchteil
    # der sonstigen Menge; echtes Wachstum trifft das nicht.
    med = company_year.groupby("ticker")[["n_facilities", "scope1_t"]].transform("median")
    luecke = (
        (company_year["n_facilities"] <= 0.34 * med["n_facilities"])
        & (company_year["scope1_t"] <= 0.2 * med["scope1_t"])
        & (med["n_facilities"] >= 3)
    )
    n_luecke = int(luecke.sum())
    company_year = company_year[~luecke].reset_index(drop=True)

    # Umsatz ueber die CIK anhaengen.
    rev_join = rev.merge(master[["ticker", "cik"]], on="cik", how="inner")
    company_year = company_year.merge(
        rev_join[["ticker", "year", "revenue_musd"]], on=["ticker", "year"], how="left"
    )
    company_year["co2_intensity"] = (
        company_year["scope1_t"] / company_year["revenue_musd"]
    ).replace([np.inf, -np.inf], np.nan)

    company_year = company_year.merge(
        master[["ticker", "company", "gics_sector", "gics_sub_industry"]],
        on="ticker",
        how="left",
    )

    diag = {
        "epa_facility_rows": len(fac),
        "anlagenjahre_ohne_menge": n_zero,
        "firmenjahre_zuordnung_unvollstaendig": n_luecke,
        "epa_emission_rows": len(emi),
        "facilities_with_emissions": facilities["facility_id"].nunique(),
        "total_epa_emissions_t": float(total_emissions),
        "matched_emissions_t": float(matched_emissions),
        "matched_share": float(matched_emissions / total_emissions) if total_emissions else 0.0,
        "sp500_companies": len(master),
        "companies_matched": company_year["ticker"].nunique(),
        "owner_match_methods": owners["match_method"].value_counts().to_dict()
        if not owners.empty
        else {},
    }
    return company_year, diag


def build_panel(company_year: pd.DataFrame, year_from: int, year_to: int) -> pd.DataFrame:
    """Verdichtet die Jahresreihe eines Zeitfensters zu einer Zeile je Firma."""
    win = company_year[
        (company_year["year"] >= year_from) & (company_year["year"] <= year_to)
    ].copy()
    if win.empty:
        return win

    rows: list[dict] = []
    for ticker, g in win.groupby("ticker"):
        g = g.sort_values("year")
        last = g.iloc[-1]
        intensity = g.dropna(subset=["co2_intensity"])
        base = g.iloc[0]["scope1_t"]
        median_t = g["scope1_t"].median()
        # Schutz gegen instabile Basisjahre: Liegt das erste Jahr des Fensters
        # weit weg vom Median, misst die Quote die Anlagenzuordnung, nicht das
        # Verhalten der Firma (PPL 2018: eine Anlage statt neun). Dann keine
        # Zahl ausweisen, sondern die Instabilitaet kennzeichnen.
        ratio = float(base / median_t) if median_t and median_t > 0 else np.nan
        basis_stabil = bool(np.isfinite(ratio) and 0.2 <= ratio <= 2.5)
        # Ein Trend braucht mindestens drei gemessene Jahre. Raten jenseits von
        # 100 % im Jahr sind Zuordnungssspruenge, keine Klimaentwicklung.
        genug_jahre = int(g["year"].nunique()) >= 3
        def _guard(v: float) -> float:
            return float(v) if (genug_jahre and basis_stabil
                                and np.isfinite(v) and abs(v) <= 1.0) else np.nan
        rows.append(
            {
                "ticker": ticker,
                "company": last["company"],
                "gics_sector": last["gics_sector"],
                "gics_sub_industry": last["gics_sub_industry"],
                "years_observed": int(g["year"].nunique()),
                "year_last": int(last["year"]),
                "scope1_t": float(last["scope1_t"]),
                "revenue_musd": float(last["revenue_musd"])
                if pd.notna(last["revenue_musd"])
                else np.nan,
                "co2_intensity": float(last["co2_intensity"])
                if pd.notna(last["co2_intensity"])
                else np.nan,
                "n_facilities": int(last["n_facilities"]),
                "match_confidence": float(g["match_confidence"].mean()),
                "intensity_cagr": _guard(_cagr(intensity["co2_intensity"], intensity["year"])),
                "absolute_cagr": _guard(_cagr(g["scope1_t"], g["year"])),
                "trend_belastbar": genug_jahre and basis_stabil,
                # Achse B: Basisjahr-Bequemlichkeit. Liegt das erste Jahr des
                # Fensters deutlich ueber dem Median, sieht jede spaetere
                # Reduktion beeindruckender aus, als sie ist.
                "base_year_ratio": ratio if basis_stabil else np.nan,
                "basis_stabil": basis_stabil,
            }
        )
    panel = pd.DataFrame(rows)

    # Achse B: Intensitaets-Illusion. Intensitaet faellt, absolut steigt.
    panel["intensity_illusion"] = (
        (panel["intensity_cagr"] < 0) & (panel["absolute_cagr"] > 0)
    )
    panel["illusion_gap"] = panel["absolute_cagr"] - panel["intensity_cagr"]
    return panel
