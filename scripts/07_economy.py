"""Assess economic viability from SEC companyfacts.

Usage: python scripts/07_economy.py fetch|score [data/raw/sec_facts]

The output contains cash-generation, shock-absorption, and debt-service dimensions, a geometric index, and a weakest-dimension level. The current implementation excludes the entire Financials sector. See docs/TECHNICAL.md for assumptions and limitations."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import ROOT
from pipeline.economy.fetch_sec_facts import main as fetch_main  # noqa: E402
from pipeline.economy import economic_viability as ev  # noqa: E402


def main(argv: list[str]) -> None:
    import os
    os.chdir(ROOT)
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
        # Write into the standard output directory.
        import os

        os.chdir(Path(__file__).resolve().parent.parent)
        ev.OUT = "data/out/economic_viability.csv"
        ev.main()


if __name__ == "__main__":
    main(sys.argv[1:])
