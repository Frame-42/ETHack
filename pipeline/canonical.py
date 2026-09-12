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
                "intensity_cagr": _cagr(intensity["co2_intensity"], intensity["year"]),
                "absolute_cagr": _cagr(g["scope1_t"], g["year"]),
                # Achse B: Basisjahr-Bequemlichkeit. Liegt das erste Jahr des
                # Fensters deutlich ueber dem Median, sieht jede spaetere
                # Reduktion beeindruckender aus, als sie ist.
                "base_year_ratio": float(base / median_t) if median_t and median_t > 0 else np.nan,
            }
        )
    panel = pd.DataFrame(rows)

    # Achse B: Intensitaets-Illusion. Intensitaet faellt, absolut steigt.
    panel["intensity_illusion"] = (
        (panel["intensity_cagr"] < 0) & (panel["absolute_cagr"] > 0)
    )
    panel["illusion_gap"] = panel["absolute_cagr"] - panel["intensity_cagr"]
    return panel
