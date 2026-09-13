"""Construct company-year data, climate sensitivity bands, and diagnostics for the two configured study periods. Write analysis outputs separately from source observations."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from pipeline import analysis
from pipeline.canonical import build_company_year, build_panel, load_raw
from pipeline.config import OUT, PERIOD_A_END, PERIOD_B_START
from pipeline.scoring.montecarlo import Metric, MonteCarloConfig, run

METRICS = [
    Metric("co2_intensity", -1, "Emissions intensity (tonnes per million USD revenue)"),
    Metric("intensity_cagr", -1, "Annual emissions-intensity change"),
    Metric("absolute_cagr", -1, "Annual absolute-emissions change"),
]

PERIOD_A = (2018, PERIOD_A_END)


def jsonable(obj):
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items() if k != "detail"}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def main() -> None:
    t0 = time.time()
    raw = load_raw()
    from pipeline.universe import primary_master
    raw["sp500_master"] = primary_master()
    master, esg = raw["sp500_master"], raw["esg_snapshot"]
    stats: dict = {}

    # Company-year observations.
    company_year, diag = build_company_year(raw)
    company_year.to_csv(OUT / "company_year.csv", index=False)
    stats["data_basis"] = diag
    print(f"Companies with EPA attribution: {diag['companies_matched']} since {diag['sp500_companies']}")
    print(f"Share of emissions attributed: {diag['matched_share']*100:.1f} %")

    panel_a = build_panel(company_year, *PERIOD_A)
    panel_a = panel_a[panel_a["co2_intensity"].notna() & (panel_a["years_observed"] >= 3)]
    panel_a.to_csv(OUT / "climate_panel.csv", index=False)
    stats["period_a"] = {
        "years": list(PERIOD_A),
        "n_companies": int(len(panel_a)),
        "n_sectors": int(panel_a["gics_sector"].nunique()),
        "total_scope1_mt": float(panel_a["scope1_t"].sum() / 1e6),
    }
    print(f"Period A: {len(panel_a)} companies in the analysis panel")

    # Climate sensitivity analysis.
    cfg = MonteCarloConfig(n_draws=1500)
    bands, draws = run(panel_a, METRICS, cfg)
    bands = bands.sort_values("p50", ascending=False)
    bands.to_csv(OUT / "climate_bands.csv", index=False)
    draws.to_parquet(OUT / "climate_draws.parquet", index=False)
    stats["monte_carlo"] = {
        "n_draws": cfg.n_draws,
        "discrete_configurations": int(
            len(cfg.normalizers) * len(cfg.weighters) * len(cfg.aggregators)
            * len(cfg.peer_levels) * len(cfg.winsor_levels) * (len(METRICS) + 1)
        ),
        "median_band_width": float(bands["band_width"].median()),
        "p90_band_width": float(bands["band_width"].quantile(0.9)),
        "share_band_above_40": float((bands["band_width"] > 40).mean() * 100),
        "companies_stable_top": int((bands["share_top_quintile"] >= 90).sum()),
        "companies_stable_bottom": int((bands["share_bottom_quintile"] >= 90).sum()),
    }
    print(f"Monte Carlo median band width: {bands['band_width'].median():.1f} percentile points")

    # Compare method-only and noise-only runs with the combined run. Their median widths are descriptive and need not add to the combined width.
    cfg_m = MonteCarloConfig(n_draws=800, base_noise=0.0, match_noise=0.0)
    cfg_d = MonteCarloConfig(
        n_draws=800, normalizers=("winsor-z",), weighters=("equal",),
        aggregators=("geometric",), peer_levels=("gics_sector",),
        winsor_levels=(0.01,), p_drop=0.0,
    )
    band_m, _ = run(panel_a, METRICS, cfg_m)
    band_d, _ = run(panel_a, METRICS, cfg_d)
    group_sizes = panel_a["gics_sector"].value_counts()
    stats["uncertainty_diagnostics"] = {
        "method_only": float(band_m["band_width"].median()),
        "noise_only": float(band_d["band_width"].median()),
        "combined": float(bands["band_width"].median()),
        "mean_group_size": float(group_sizes.mean()),
        "smallest_group": int(group_sizes.min()),
        "percentiles_per_rank": float(100.0 / group_sizes.mean()),
        "median_band_in_ranks": float(
            bands["band_width"].median() / (100.0 / group_sizes.mean())
        ),
        "sectors_below_6_companies": group_sizes[group_sizes < 6].to_dict(),
    }
    corr = panel_a[[m.column for m in METRICS]].corr(method="spearman")
    corr.to_csv(OUT / "metric_correlations.csv")
    stats["metric_correlations"] = corr.round(3).to_dict()

    # Contextual warning signals.
    gw = analysis.greenwashing_axis(panel_a)
    gw.to_csv(OUT / "context_signals.csv", index=False)
    stats["greenwashing"] = {
        "n_intensity_illusion": int(gw["intensity_illusion"].sum()),
        "n_high_base_year": int(gw["base_year_flag"].sum()),
        "n_any_flag": int((gw["flags"] >= 1).sum()),
        "n_both_flags": int((gw["flags"] == 2).sum()),
        "share_any_flag": float((gw["flags"] >= 1).mean() * 100),
    }

    # Diagnostics.
    cov = analysis.coverage_by_sector(master, panel_a)
    cov.to_csv(OUT / "sector_coverage.csv", index=False)
    stats["coverage"] = {
        "sectors_without_data": cov[cov["companies_with_data"] == 0]["gics_sector"].tolist(),
        "sectors_below_25pct": cov[cov["coverage_pct"] < 25]["gics_sector"].tolist(),
        "table": cov.to_dict("records"),
    }

    per_sector, cmp_stat = analysis.compare_with_commercial(bands, esg)
    per_sector.to_csv(OUT / "commercial_comparison_sector.csv", index=False)
    stats["commercial_comparison"] = cmp_stat
    stats["commercial_comparison_sector"] = per_sector.to_dict("records")
    if "spearman_total" in cmp_stat:
        print(
            f"Rank correlation with historical commercial risk: {cmp_stat['spearman_total']:.2f} "
            f"(n={cmp_stat['n']})"
        )

    stats["size_bias"] = analysis.size_bias(bands, panel_a, esg)

    agg = analysis.aggregation_effect(panel_a, METRICS, cfg)
    agg.to_csv(OUT / "aggregation_comparison.csv", index=False)
    stats["aggregation"] = {
        "median_absolute_difference": float(agg["difference"].abs().median()),
        "max_absolute_difference": float(agg["difference"].abs().max()),
        "share_above_10_points": float((agg["difference"].abs() > 10).mean() * 100),
    }

    tickers = [c for c in draws.columns if c in set(panel_a["ticker"])]
    sens = analysis.method_sensitivity(draws, tickers)
    sens.to_csv(OUT / "method_sensitivity.csv", index=False)
    stats["method_sensitivity"] = sens.to_dict("records")

    # Reporting-lag analysis.
    stale = analysis.staleness_backtest(company_year, METRICS, cfg, lag=2, truth_year=2023)
    if "detail" in stale:
        stale["detail"].to_csv(OUT / "staleness_backtest.csv", index=False)
    stats["period_b"] = {
        "epa_last_year": int(company_year["year"].max()),
        "sec_last_year": int(raw["sec_revenue"]["year"].max()),
        "emissions_available": bool(
            (company_year["year"] >= PERIOD_B_START).any()
        ),
        "companies_with_2025_revenue": int(
            raw["sec_revenue"]
            .merge(master[["ticker", "cik"]], on="cik")
            .query("year == 2025")["ticker"]
            .nunique()
        ),
        "carry_forward": jsonable(stale),
    }
    print(
        "Period B: EPA panel ends in "
        f"{stats['period_b']['epa_last_year']}, SEC data extend through "
        f"{stats['period_b']['sec_last_year']}"
    )
    if "spearman" in stale:
        print(
            f"Two-year carry-forward: Spearman {stale['spearman']:.2f}, "
            f"Median difference {stale['median_percentile_difference']:.1f} percentile points"
        )

    stats["runtime_seconds"] = round(time.time() - t0, 1)
    (OUT / "analysis_summary.json").write_text(
        json.dumps(jsonable(stats), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nFinished in {stats['runtime_seconds']}s -> {OUT}")


if __name__ == "__main__":
    main()
