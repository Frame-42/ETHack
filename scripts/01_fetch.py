"""Stufe 01+02: alle registrierten Quellen ziehen und als Parquet cachen."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.sources import base
from pipeline.sources import epa_ghgrp, esg_snapshot, sec_revenue, sp500  # noqa: F401


def main(only: list[str] | None = None, force: bool = False) -> None:
    for name, cls in base.available().items():
        if only and name not in only:
            continue
        src = cls()
        t0 = time.time()
        print(f"[{name}] laedt ...", flush=True)
        try:
            df = src.fetch(force=force)
            print(
                f"[{name}] {len(df):,} Zeilen, {time.time() - t0:.1f}s "
                f"-> {src.cache_path.name}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] FEHLER: {exc}", flush=True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(only=args or None, force="--force" in sys.argv)
