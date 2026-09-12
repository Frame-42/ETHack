"""Stufe 05/07: Grafiken fuer den Bericht erzeugen."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from pipeline import figures
from pipeline.canonical import load_raw
from pipeline.config import OUT


def main() -> None:
    raw = load_raw()
    esg = raw["esg_snapshot"]
    stats = json.loads((OUT / "kennzahlen.json").read_text(encoding="utf-8"))

    bands = pd.read_csv(OUT / "rangbaender_periode_a.csv")
    panel = pd.read_csv(OUT / "panel_periode_a.csv")
    cov = pd.read_csv(OUT / "abdeckung_sektor.csv")
    agg = pd.read_csv(OUT / "aggregation_vergleich.csv")
    sens = pd.read_csv(OUT / "methoden_sensitivitaet.csv")
    gw = pd.read_csv(OUT / "greenwashing_periode_a.csv")

    made = [
        figures.fig_availability(
            last_epa=stats["periode_b"]["epa_letztes_jahr"],
            last_sec=stats["periode_b"]["sec_letztes_jahr"],
            esg_asof=2021,
        ),
        figures.fig_coverage(cov),
        figures.fig_bands(bands, "Utilities"),
        figures.fig_band_width(bands),
        figures.fig_sensitivity(sens),
        figures.fig_aggregation(agg),
        figures.fig_vs_commercial(bands, esg),
        figures.fig_size_bias(bands, panel, esg),
        figures.fig_greenwashing(gw),
    ]

    stale_path = OUT / "staleness_backtest.csv"
    if stale_path.exists():
        detail = pd.read_csv(stale_path)
        fb = stats["periode_b"]["fortschreibung"]
        made.append(
            figures.fig_staleness(
                detail, fb["spearman"], fb["median_abweichung_perzentil"]
            )
        )

    for p in made:
        print("->", Path(p).name)


if __name__ == "__main__":
    main()
