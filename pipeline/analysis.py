"""Diagnostics for coverage, sensitivity, historical benchmarks, and reporting lag.

Period A uses the configured 2018-2023 GHGRP window and SEC revenue. The commercial snapshot is a separate historical benchmark. Period B explores the consequences of carrying emissions forward beyond that configured window; it does not establish current source availability."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def coverage_by_sector(master: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Count companies with emissions data within each GICS sector."""
    total = master.groupby("gics_sector")["ticker"].nunique().rename("total_companies")
    covered = panel.groupby("gics_sector")["ticker"].nunique().rename("companies_with_data")
    emis = panel.groupby("gics_sector")["scope1_t"].sum().rename("scope1_t")
    out = pd.concat([total, covered, emis], axis=1).fillna(0)
    out["companies_with_data"] = out["companies_with_data"].astype(int)
    out["coverage_pct"] = out["companies_with_data"] / out["total_companies"] * 100
    return out.sort_values("coverage_pct", ascending=False).reset_index()


def compare_with_commercial(
    bands: pd.DataFrame, esg: pd.DataFrame
) -> tuple[pd.DataFrame, dict]:
    """Compare climate percentiles with a historical commercial risk score. Reverse ESG risk so that higher values consistently mean better results."""
    if not {"ticker", "esg_risk_total", "esg_risk_env"} <= set(esg):
        return pd.DataFrame(columns=["gics_sector", "n", "spearman"]), {"n": 0}
    m = bands.merge(esg[["ticker", "esg_risk_total", "esg_risk_env"]], on="ticker", how="inner")
    m = m.dropna(subset=["p50", "esg_risk_total"])
    stat: dict = {"n": len(m)}
    if len(m) >= 8:
        rho, p = stats.spearmanr(m["p50"], -m["esg_risk_total"])
        stat["spearman_total"] = float(rho)
        stat["p_total"] = float(p)
        rho_e, p_e = stats.spearmanr(m["p50"], -m["esg_risk_env"])
        stat["spearman_environment"] = float(rho_e)
        stat["p_environment"] = float(p_e)
    per_sector = []
    for sector, g in m.groupby("gics_sector"):
        if len(g) >= 6:
            rho, _ = stats.spearmanr(g["p50"], -g["esg_risk_total"])
            per_sector.append(
                {"gics_sector": sector, "n": len(g), "spearman": float(rho)}
            )
    return pd.DataFrame(per_sector, columns=["gics_sector", "n", "spearman"]).sort_values("spearman"), stat


def size_bias(bands: pd.DataFrame, panel: pd.DataFrame, esg: pd.DataFrame) -> dict:
    """Test the association between scores and company size. A small correlation is a diagnostic, not proof that a model is unbiased."""
    m = bands.merge(panel[["ticker", "revenue_musd"]], on="ticker", how="left")
    m = m.dropna(subset=["revenue_musd", "p50"])
    m = m[m["revenue_musd"] > 0]
    out: dict = {}
    if len(m) >= 10:
        rho, p = stats.spearmanr(np.log(m["revenue_musd"]), m["p50"])
        out["framework_score_vs_size"] = float(rho)
        out["p_framework"] = float(p)
        out["n_framework"] = len(m)
    if not {"ticker", "esg_risk_total"} <= set(esg):
        return out
    e = esg.merge(panel[["ticker", "revenue_musd"]], on="ticker", how="inner")
    e = e.dropna(subset=["revenue_musd", "esg_risk_total"])
    e = e[e["revenue_musd"] > 0]
    if len(e) >= 10:
        rho, p = stats.spearmanr(np.log(e["revenue_musd"]), -e["esg_risk_total"])
        out["commercial_score_vs_size"] = float(rho)
        out["p_commercial"] = float(p)
        out["n_commercial"] = len(e)
    return out


def aggregation_effect(panel: pd.DataFrame, metrics, cfg) -> pd.DataFrame:
    """Compare percentile rankings under arithmetic and geometric aggregation."""
    from .scoring.montecarlo import Draw, score_once

    base = dict(
        normalizer="winsor-z", weighter="equal", peer_level="gics_sector",
        winsor=0.01, dropped=None,
    )
    geo = score_once(panel, metrics, Draw(aggregator="geometric", **base), cfg=cfg)
    add = score_once(panel, metrics, Draw(aggregator="arithmetic", **base), cfg=cfg)
    out = geo[["ticker", "percentile"]].rename(columns={"percentile": "geometric"})
    out = out.merge(
        add[["ticker", "percentile"]].rename(columns={"percentile": "arithmetic"}),
        on="ticker",
    )
    out["difference"] = out["geometric"] - out["arithmetic"]
    return out.merge(
        panel[["ticker", "company", "gics_sector"]], on="ticker", how="left"
    )


def method_sensitivity(draws: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """For each method dimension, calculate the range of conditional mean percentiles, averaged across companies. This is descriptive sensitivity, not a variance decomposition."""
    dims = ["normalizer", "weighter", "aggregator", "peer_level", "winsor"]
    rows = []
    for dim in dims:
        per_level = draws.groupby(dim)[tickers].mean()
        if len(per_level) < 2:
            continue
        spread = (per_level.max(axis=0) - per_level.min(axis=0)).mean()
        rows.append({"dimension": dim, "mean_percentile_range": float(spread)})
    return pd.DataFrame(rows).sort_values(
        "mean_percentile_range", ascending=False
    )


def staleness_backtest(
    company_year: pd.DataFrame, metrics, cfg, lag: int = 2, truth_year: int = 2023
) -> dict:
    """Simulate reporting lag by pairing emissions from truth_year - lag with revenue from truth_year, then compare the resulting peer percentiles with the contemporaneous panel."""
    from .canonical import build_panel
    from .scoring.montecarlo import Draw, score_once

    truth = build_panel(company_year, truth_year - 5, truth_year)
    stale_src = company_year.copy()
    # Shift emissions forward by lag years while retaining current revenue.
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
    draw = Draw("winsor-z", "equal", "geometric", "gics_sector", 0.01, None)
    t = score_once(truth[truth.ticker.isin(common)], metrics, draw, cfg=cfg)
    s = score_once(stale[stale.ticker.isin(common)], metrics, draw, cfg=cfg)
    j = t[["ticker", "percentile"]].merge(
        s[["ticker", "percentile"]], on="ticker", suffixes=("_actual", "_stale")
    ).dropna()
    rho, _ = stats.spearmanr(j["percentile_actual"], j["percentile_stale"])
    diff = (j["percentile_actual"] - j["percentile_stale"]).abs()
    return {
        "n": len(j),
        "lag_years": lag,
        "spearman": float(rho),
        "median_percentile_difference": float(diff.median()),
        "p90_percentile_difference": float(diff.quantile(0.90)),
        "share_above_10_percentiles": float((diff > 10).mean() * 100),
        "detail": j,
    }


def greenwashing_axis(panel: pd.DataFrame) -> pd.DataFrame:
    """Return contextual warning signals separately from climate performance."""
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
    # Flag a starting year above the median of the observation window.
    out["base_year_flag"] = out["base_year_ratio"] > 1.10
    out["flags"] = (
        out["intensity_illusion"].astype(int) + out["base_year_flag"].astype(int)
    )
    return out.sort_values(["flags", "illusion_gap"], ascending=[False, False])
