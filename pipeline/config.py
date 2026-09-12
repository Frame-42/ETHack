"""Zentrale Pfade und Konstanten der Pipeline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "out"
REPORT = ROOT / "report"
FIGURES = REPORT / "figures"

for _p in (RAW, OUT, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)

# Die SEC verlangt einen identifizierenden User-Agent, sonst 403.
USER_AGENT = "ETHack S&P500 Sustainability Research (noah.schittenhelm@pm.me)"

# Periodengrenze: bis einschliesslich dieses Geschaeftsjahres reicht der
# kommerzielle ESG-Snapshot (Kaggle/Yahoo-Stand 2023/24). Danach faellt er weg.
PERIOD_A_END = 2023
PERIOD_B_START = 2024

# Letztes Jahr, fuer das die EPA Anlagendaten veroeffentlicht hat.
EPA_LAST_PUBLISHED_YEAR = 2023
