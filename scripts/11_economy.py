"""Stufe 11: Economic-Viability-Pfeiler (aus feat/economy).

    Kann eine Firma Belegschaft, Lieferanten und Kredite aus dem eigenen
    operativen Cashflow bezahlen — auch im schlechtesten selbst erlebten Jahr?

    Ablauf (zwei Schritte, SEC EDGAR companyfacts):
      1. python scripts/11_economy.py fetch data/raw/sec_facts
      2. python scripts/11_economy.py score data/raw/sec_facts

    Ergebnis: data/out/economic_viability.csv mit
      score_cash_generation / score_shock_absorption / score_debt_service,
      viability_index (0-100) und viability_level
      (viable / strained / at risk / not assessable).

    Grundsaetze: Kapazitaet statt Groesse/Profit (Saturierung),
    nur berichtete 10-K/10-Q-Werte, schwächstes Glied entscheidet
    (geometrisches Mittel). Banken/Versicherer = not assessable.
    Details: report/economic_viability.tex, pipeline/economy/.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.economy.fetch_sec_facts import main as fetch_main  # noqa: E402
from pipeline.economy import economic_viability as ev  # noqa: E402


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in ("fetch", "score"):
        print(__doc__)
        raise SystemExit(2)
    if argv[0] == "fetch":
        out = argv[1] if len(argv) > 1 else "data/raw/sec_facts"
        sys.argv = ["fetch_sec_facts.py", out]
        fetch_main()
    else:
        facts_dir = argv[1] if len(argv) > 1 else "data/raw/sec_facts"
        sys.argv = ["economic_viability.py", facts_dir]
        # Ausgabe ins Standard-Out-Verzeichnis umleiten
        import os

        os.chdir(Path(__file__).resolve().parent.parent)
        ev.OUT = "data/out/economic_viability.csv"
        ev.HEALTH_CSV = "data/out/financial_health.csv"
        ev.main()


if __name__ == "__main__":
    main(sys.argv[1:])
