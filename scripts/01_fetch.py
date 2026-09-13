"""Fetch registered sources and cache them as Parquet."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.sources import base
from pipeline.sources import (  # noqa: F401
    dol_whd, egrid, eia_api, eia_generation, epa_campd, epa_echo, epa_ghgrp,
    epa_tri, esg_snapshot, osha_ita, sbti, sec_revenue, sp500, team,
)


def main(only: list[str] | None = None, force: bool = False) -> None:
    unknown = set(only or []) - set(base.available())
    if unknown:
        raise ValueError(f"Unknown sources: {sorted(unknown)}")
    failures = []
    for name, cls in base.available().items():
        if only and name not in only:
            continue
        src = cls()
        t0 = time.time()
        print(f"[{name}] loading ...", flush=True)
        try:
            df = src.fetch(force=force)
            print(
                f"[{name}] {len(df):,} rows, {time.time() - t0:.1f}s "
                f"-> {src.cache_path.name}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] ERROR: {exc}", flush=True)
            failures.append(name)
    if failures:
        raise SystemExit(f"Sources failed: {', '.join(failures)}. Re-run those sources before dependent stages.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(only=args or None, force="--force" in sys.argv)
