"""Auswertungen fuer den Bericht.

Zwei Perioden:

**Periode A (FY2018-FY2023).** Alles vorhanden: EPA-Anlagendaten,
SEC-Umsaetze, dazu ein kommerzieller ESG-Snapshot als Vergleichsmassstab.
Hier laesst sich das eigene Ranking gegen eine gekaufte Note halten.

**Periode B (ab FY2024).** Die EPA hat Berichtsjahr 2024 bis heute nicht
veroeffentlicht. Umsaetze gibt es, Emissionen nicht. Die Frage ist nicht, ob
das Ranking schlechter wird, sondern ob es ueberhaupt noch eines ist.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def coverage_by_sector(master: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Wie viele Firmen je GICS-Sektor bekommen ueberhaupt Emissionsdaten?"""
    total = master.groupby("gics_sector")["ticker"].nunique().rename("firmen_gesamt")
    covered = panel.groupby("gics_sector")["ticker"].nunique().rename("firmen_mit_daten")
    emis = panel.groupby("gics_sector")["scope1_t"].sum().rename("scope1_t")
    out = pd.concat([total, covered, emis], axis=1).fillna(0)
    out["firmen_mit_daten"] = out["firmen_mit_daten"].astype(int)
    out["abdeckung_pct"] = out["firmen_mit_daten"] / out["firmen_gesamt"] * 100
    return out.sort_values("abdeckung_pct", ascending=False).reset_index()


def compare_with_commercial(
    bands: pd.DataFrame, esg: pd.DataFrame
) -> tuple[pd.DataFrame, dict]:
    """Vergleicht die physisch gemessene Rangliste mit einer gekauften Note.

    ``esg_risk_total`` ist ein Risikowert -- hoeher ist schlechter. Fuer den
    Vergleich wird er umgedreht, damit beide Skalen gleich zeigen.
    """
    m = bands.merge(esg[["ticker", "esg_risk_total", "esg_risk_env"]], on="ticker", how="inner")
    m = m.dropna(subset=["p50", "esg_risk_total"])
    stat: dict = {"n": len(m)}
    if len(m) >= 8:
        rho, p = stats.spearmanr(m["p50"], -m["esg_risk_total"])
        stat["spearman_gesamt"] = float(rho)
        stat["p_gesamt"] = float(p)
        rho_e, p_e = stats.spearmanr(m["p50"], -m["esg_risk_env"])
        stat["spearman_umwelt"] = float(rho_e)
        stat["p_umwelt"] = float(p_e)
    per_sector = []
    for sector, g in m.groupby("gics_sector"):
        if len(g) >= 6:
            rho, _ = stats.spearmanr(g["p50"], -g["esg_risk_total"])
            per_sector.append(
                {"gics_sector": sector, "n": len(g), "spearman": float(rho)}
            )
    return pd.DataFrame(per_sector).sort_values("spearman"), stat


def size_bias(bands: pd.DataFrame, panel: pd.DataFrame, esg: pd.DataFrame) -> dict:
    """Groessen-Verzerrung: haengt die Note an der Firmengroesse?

    Die Forschung findet den Effekt bei kommerziellen Noten deutlich. Eine
    physisch gemessene Intensitaet sollte ihn nicht zeigen -- pruefen wir.
    """
    m = bands.merge(panel[["ticker", "revenue_musd"]], on="ticker", how="left")
    m = m.dropna(subset=["revenue_musd", "p50"])
    m = m[m["revenue_musd"] > 0]
    out: dict = {}
    if len(m) >= 10:
        rho, p = stats.spearmanr(np.log(m["revenue_musd"]), m["p50"])
        out["eigene_note_vs_groesse"] = float(rho)
        out["p_eigene"] = float(p)
        out["n_eigene"] = len(m)
    e = esg.merge(panel[["ticker", "revenue_musd"]], on="ticker", how="inner")
    e = e.dropna(subset=["revenue_musd", "esg_risk_total"])
    e = e[e["revenue_musd"] > 0]
    if len(e) >= 10:
        rho, p = stats.spearmanr(np.log(e["revenue_musd"]), -e["esg_risk_total"])
        out["kommerzielle_note_vs_groesse"] = float(rho)
        out["p_kommerziell"] = float(p)
        out["n_kommerziell"] = len(e)
    return out


def aggregation_effect(panel: pd.DataFrame, metrics, cfg) -> pd.DataFrame:
    """Wie weit laufen additive und geometrische Rangliste auseinander?"""
    from .scoring.montecarlo import Draw, score_once

    base = dict(
        normalizer="z-getrimmt", weighter="gleich", peer_level="gics_sector",
        winsor=0.01, dropped=None,
    )
    geo = score_once(panel, metrics, Draw(aggregator="geometrisch", **base), cfg=cfg)
    add = score_once(panel, metrics, Draw(aggregator="additiv", **base), cfg=cfg)
    out = geo[["ticker", "percentile"]].rename(columns={"percentile": "geometrisch"})
    out = out.merge(
        add[["ticker", "percentile"]].rename(columns={"percentile": "additiv"}),
        on="ticker",
    )
    out["differenz"] = out["geometrisch"] - out["additiv"]
    return out.merge(
        panel[["ticker", "company", "gics_sector"]], on="ticker", how="left"
    )


def method_sensitivity(draws: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Wie stark verschiebt jede einzelne Methodenwahl das Ergebnis?

    Fuer jede Methodendimension: mittlere absolute Perzentilverschiebung
    zwischen den Auspraegungen, gemittelt ueber alle Firmen.
    """
    dims = ["normalizer", "weighter", "aggregator", "peer_level", "winsor"]
    rows = []
    for dim in dims:
        per_level = draws.groupby(dim)[tickers].mean()
        if len(per_level) < 2:
            continue
        spread = (per_level.max(axis=0) - per_level.min(axis=0)).mean()
        rows.append({"dimension": dim, "mittlere_spannweite_perzentil": float(spread)})
    return pd.DataFrame(rows).sort_values(
        "mittlere_spannweite_perzentil", ascending=False
    )


def staleness_backtest(
    company_year: pd.DataFrame, metrics, cfg, lag: int = 2, truth_year: int = 2023
) -> dict:
    """Was kostet es, veraltete Emissionsdaten fortzuschreiben?

    Genau die Frage fuer Periode B: Die EPA-Reihe endet 2023, der Umsatz
    laeuft weiter. Wer trotzdem ein Ranking ausgibt, schreibt Emissionen fort.
    Der Test simuliert das ruecklaufend -- Emissionen aus ``truth_year - lag``,
    Umsatz aus ``truth_year`` -- und misst, wie weit die Rangliste abweicht.
    """
    from .canonical import build_panel
    from .scoring.montecarlo import Draw, score_once

    truth = build_panel(company_year, truth_year - 5, truth_year)
    stale_src = company_year.copy()
    # Emissionen um ``lag`` Jahre nach vorne schreiben, Umsatz aktuell lassen.
    shifted = company_year[["ticker", "year", "scope1_t"]].copy()
    shifted["year"] = shifted["year"] + lag
    stale_src = stale_src.drop(columns=["scope1_t"]).merge(
        shifted, on=["ticker", "year"], how="inner"
    )
    stale_src["co2_intensity"] = (
        stale_src["scope1_t"] / stale_src["revenue_musd"]
    ).replace([np.inf, -np.inf], np.nan)
    stale = build_panel(stale_src, truth_year - 5, truth_year)

    common = sorted(set(truth["ticker"]) & set(stale["ticker"]))
    if len(common) < 20:
        return {"n": len(common)}
    draw = Draw("z-getrimmt", "gleich", "geometrisch", "gics_sector", 0.01, None)
    t = score_once(truth[truth.ticker.isin(common)], metrics, draw, cfg=cfg)
    s = score_once(stale[stale.ticker.isin(common)], metrics, draw, cfg=cfg)
    j = t[["ticker", "percentile"]].merge(
        s[["ticker", "percentile"]], on="ticker", suffixes=("_wahr", "_veraltet")
    ).dropna()
    rho, _ = stats.spearmanr(j["percentile_wahr"], j["percentile_veraltet"])
    diff = (j["percentile_wahr"] - j["percentile_veraltet"]).abs()
    return {
        "n": len(j),
        "lag_jahre": lag,
        "spearman": float(rho),
        "median_abweichung_perzentil": float(diff.median()),
        "p90_abweichung_perzentil": float(diff.quantile(0.90)),
        "anteil_ueber_10_perzentil": float((diff > 10).mean() * 100),
        "detail": j,
    }


def greenwashing_axis(panel: pd.DataFrame) -> pd.DataFrame:
    """Achse B: Signale, die getrennt von der Kernnote ausgewiesen werden."""
    out = panel[
        [
            "ticker",
            "company",
            "gics_sector",
            "intensity_cagr",
            "absolute_cagr",
            "intensity_illusion",
            "illusion_gap",
            "base_year_ratio",
            "match_confidence",
            "years_observed",
        ]
    ].copy()
    # Bequemes Basisjahr: erstes Jahr des Fensters liegt klar ueber dem Median.
    out["base_year_flag"] = out["base_year_ratio"] > 1.10
    out["flags"] = (
        out["intensity_illusion"].astype(int) + out["base_year_flag"].astype(int)
    )
    return out.sort_values(["flags", "illusion_gap"], ascending=[False, False])
