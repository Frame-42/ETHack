"""Export consolidated observations and check data integrity."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUT, ROOT
from pipeline.consolidate import write_all


def validate_export() -> None:
    """Enforce source constraints during export. Fail rather than ship duplicate issuer observations or unclassified value provenance."""
    import pandas as pd

    long = pd.read_parquet(OUT / "dataset_long.parquet")
    w = long.pivot_table(index=["ticker", "year"], columns="metric", values="value",
                         aggfunc="first")

    def check_bound(metric: str, *, at_most=None, at_least=None, text="") -> None:
        if metric not in w:
            return
        v = w[metric].dropna()
        if at_most is not None and (v > at_most).any():
            raise AssertionError(f"{metric}: {int((v > at_most).sum())} values above "
                                 f"{at_most} -- {text}")
        if at_least is not None and (v < at_least).any():
            raise AssertionError(f"{metric}: {int((v < at_least).sum())} values below "
                                 f"{at_least} -- {text}")

    # Apply constraints supported by the source definition.
    if {"echo_nc_quarters", "echo_facilities"} <= set(w.columns):
        too_many = w["echo_nc_quarters"] > 12 * w["echo_facilities"]
        if too_many.any():
            raise AssertionError(f"{int(too_many.sum())} companies exceeding 12 noncompliance "
                                 "quarters per facility in the three-year window")
    # Require provenance classification for every value.
    types = set(long["value_type"].dropna().unique())
    if not types <= {"reported", "aggregated"}:
        raise AssertionError(f"Unrecognized provenance classifications: {types}")
    if long["value_type"].isna().any():
        raise AssertionError("Observations without a provenance classification")
    for metric in ("scope1_t", "campd_co2_t"):
        if metric in w and (w[metric].dropna() <= 0).any():
            raise AssertionError(f"{metric}: nonpositive emissions; investigate missing-report semantics")
    duplicates = long.duplicated(["ticker", "year", "metric"]).sum()
    if duplicates:
        raise AssertionError(f"{duplicates} duplicate ticker/year/metric rows")
    master = pd.read_parquet(ROOT / "data" / "raw" / "sp500_master.parquet")
    observed_issuers = long[["ticker"]].drop_duplicates().merge(
        master[["ticker", "cik"]], on="ticker", validate="one_to_one")
    repeated = observed_issuers.groupby("cik").ticker.nunique()
    if (repeated > 1).any():
        raise AssertionError(f"Repeated share classes for CIKs: {repeated[repeated > 1].index.tolist()}")
    print("-> Export constraints passed")


def main() -> None:
    stats = write_all()
    validate_export()
    print(json.dumps(stats, indent=2, ensure_ascii=False))



if __name__ == "__main__":
    main()
