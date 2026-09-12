"""Stufen 03-06: kanonischer Datensatz, Monte Carlo, Zwei-Perioden-Auswertung.

Schreibt alle Ergebnisse nach ``data/out`` -- CSV zum Nachrechnen und eine
JSON-Datei mit den Kennzahlen, die der LaTeX-Bericht zitiert.
"""
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
    Metric("co2_intensity", -1, "CO2-Intensitaet (t je Mio. USD Umsatz)"),
    Metric("intensity_cagr", -1, "Trend der Intensitaet (%/Jahr)"),
    Metric("absolute_cagr", -1, "Trend der absoluten Tonnen (%/Jahr)"),
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
    master, esg = raw["sp500_master"], raw["esg_snapshot"]
    stats: dict = {}

    # ---------------------------------------------------------------- Stufe 03/04
    company_year, diag = build_company_year(raw)
    company_year.to_csv(OUT / "company_year.csv", index=False)
    stats["datenbasis"] = diag
    print(f"Firmen mit EPA-Zuordnung: {diag['companies_matched']} von {diag['sp500_companies']}")
    print(f"Zugeordneter Emissionsanteil: {diag['matched_share']*100:.1f} %")

    panel_a = build_panel(company_year, *PERIOD_A)
    panel_a = panel_a[panel_a["co2_intensity"].notna() & (panel_a["years_observed"] >= 3)]
    panel_a.to_csv(OUT / "panel_periode_a.csv", index=False)
    stats["periode_a"] = {
        "jahre": list(PERIOD_A),
        "n_firmen": int(len(panel_a)),
        "n_sektoren": int(panel_a["gics_sector"].nunique()),
        "scope1_gesamt_mt": float(panel_a["scope1_t"].sum() / 1e6),
    }
    print(f"Periode A: {len(panel_a)} Firmen bewertbar")

    # ---------------------------------------------------------------- Stufe 05 A
    cfg = MonteCarloConfig(n_draws=1500)
    bands, draws = run(panel_a, METRICS, cfg)
    bands = bands.sort_values("p50", ascending=False)
    bands.to_csv(OUT / "rangbaender_periode_a.csv", index=False)
    draws.to_parquet(OUT / "draws_periode_a.parquet", index=False)
    stats["monte_carlo"] = {
        "n_zuege": cfg.n_draws,
        "kombinationsraum": int(
            len(cfg.normalizers) * len(cfg.weighters) * len(cfg.aggregators)
            * len(cfg.peer_levels) * len(cfg.winsor_levels) * (len(METRICS) + 1)
        ),
        "median_bandbreite": float(bands["band_width"].median()),
        "p90_bandbreite": float(bands["band_width"].quantile(0.9)),
        "anteil_band_ueber_40": float((bands["band_width"] > 40).mean() * 100),
        "firmen_stabil_oben": int((bands["share_top_quintile"] >= 90).sum()),
        "firmen_stabil_unten": int((bands["share_bottom_quintile"] >= 90).sum()),
    }
    print(f"Monte Carlo: mediane Bandbreite {bands['band_width'].median():.1f} Perzentilpunkte")

    # Zerlegung der Unsicherheit: kommt das Band aus der Methodenwahl oder aus
    # der Rauschannahme? Ohne diese Trennung waere die Bandbreite nicht
    # interpretierbar, sondern nur eine Folge gesetzter Parameter.
    cfg_m = MonteCarloConfig(n_draws=800, base_noise=0.0, match_noise=0.0)
    cfg_d = MonteCarloConfig(
        n_draws=800, normalizers=("z-getrimmt",), weighters=("gleich",),
        aggregators=("geometrisch",), peer_levels=("gics_sector",),
        winsor_levels=(0.01,), p_drop=0.0,
    )
    band_m, _ = run(panel_a, METRICS, cfg_m)
    band_d, _ = run(panel_a, METRICS, cfg_d)
    group_sizes = panel_a["gics_sector"].value_counts()
    stats["unsicherheits_zerlegung"] = {
        "nur_methodenwahl": float(band_m["band_width"].median()),
        "nur_datenrauschen": float(band_d["band_width"].median()),
        "beides": float(bands["band_width"].median()),
        "mittlere_gruppengroesse": float(group_sizes.mean()),
        "kleinste_gruppe": int(group_sizes.min()),
        "perzentil_je_rangplatz": float(100.0 / group_sizes.mean()),
        "median_band_in_rangplaetzen": float(
            bands["band_width"].median() / (100.0 / group_sizes.mean())
        ),
        "sektoren_unter_6_firmen": group_sizes[group_sizes < 6].to_dict(),
    }
    corr = panel_a[[m.column for m in METRICS]].corr(method="spearman")
    corr.to_csv(OUT / "kennzahlen_korrelation.csv")
    stats["kennzahlen_korrelation"] = corr.round(3).to_dict()

    # ---------------------------------------------------------------- Stufe 05 B
    gw = analysis.greenwashing_axis(panel_a)
    gw.to_csv(OUT / "greenwashing_periode_a.csv", index=False)
    stats["greenwashing"] = {
        "n_intensitaets_illusion": int(gw["intensity_illusion"].sum()),
        "n_bequemes_basisjahr": int(gw["base_year_flag"].sum()),
        "n_mind_ein_flag": int((gw["flags"] >= 1).sum()),
        "n_beide_flags": int((gw["flags"] == 2).sum()),
        "anteil_mind_ein_flag": float((gw["flags"] >= 1).mean() * 100),
    }

    # ---------------------------------------------------------------- Auswertungen
    cov = analysis.coverage_by_sector(master, panel_a)
    cov.to_csv(OUT / "abdeckung_sektor.csv", index=False)
    stats["abdeckung"] = {
        "sektoren_ohne_daten": cov[cov["firmen_mit_daten"] == 0]["gics_sector"].tolist(),
        "sektoren_unter_25pct": cov[cov["abdeckung_pct"] < 25]["gics_sector"].tolist(),
        "tabelle": cov.to_dict("records"),
    }

    per_sector, cmp_stat = analysis.compare_with_commercial(bands, esg)
    per_sector.to_csv(OUT / "vergleich_kommerziell_sektor.csv", index=False)
    stats["vergleich_kommerziell"] = cmp_stat
    stats["vergleich_kommerziell_sektor"] = per_sector.to_dict("records")
    if "spearman_gesamt" in cmp_stat:
        print(
            f"Rangkorrelation mit kommerzieller Note: {cmp_stat['spearman_gesamt']:.2f} "
            f"(n={cmp_stat['n']})"
        )

    stats["groessen_verzerrung"] = analysis.size_bias(bands, panel_a, esg)

    agg = analysis.aggregation_effect(panel_a, METRICS, cfg)
    agg.to_csv(OUT / "aggregation_vergleich.csv", index=False)
    stats["aggregation"] = {
        "median_abs_differenz": float(agg["differenz"].abs().median()),
        "max_abs_differenz": float(agg["differenz"].abs().max()),
        "anteil_ueber_10_punkte": float((agg["differenz"].abs() > 10).mean() * 100),
    }

    tickers = [c for c in draws.columns if c in set(panel_a["ticker"])]
    sens = analysis.method_sensitivity(draws, tickers)
    sens.to_csv(OUT / "methoden_sensitivitaet.csv", index=False)
    stats["methoden_sensitivitaet"] = sens.to_dict("records")

    # ---------------------------------------------------------------- Periode B
    stale = analysis.staleness_backtest(company_year, METRICS, cfg, lag=2, truth_year=2023)
    if "detail" in stale:
        stale["detail"].to_csv(OUT / "staleness_backtest.csv", index=False)
    stats["periode_b"] = {
        "epa_letztes_jahr": int(company_year["year"].max()),
        "sec_letztes_jahr": int(raw["sec_revenue"]["year"].max()),
        "emissionsdaten_verfuegbar": bool(
            (company_year["year"] >= PERIOD_B_START).any()
        ),
        "firmen_mit_umsatz_2025": int(
            raw["sec_revenue"]
            .merge(master[["ticker", "cik"]], on="cik")
            .query("year == 2025")["ticker"]
            .nunique()
        ),
        "fortschreibung": jsonable(stale),
    }
    print(
        "Periode B: EPA endet "
        f"{stats['periode_b']['epa_letztes_jahr']}, SEC laeuft bis "
        f"{stats['periode_b']['sec_letztes_jahr']}"
    )
    if "spearman" in stale:
        print(
            f"Fortschreibung um 2 Jahre: Spearman {stale['spearman']:.2f}, "
            f"Median-Abweichung {stale['median_abweichung_perzentil']:.1f} Perzentilpunkte"
        )

    stats["laufzeit_sekunden"] = round(time.time() - t0, 1)
    (OUT / "kennzahlen.json").write_text(
        json.dumps(jsonable(stats), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nFertig in {stats['laufzeit_sekunden']}s -> {OUT}")


if __name__ == "__main__":
    main()
