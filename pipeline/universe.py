"""Canonical issuer identity for the retained membership snapshot."""
import csv
from .config import ROOT, RAW


def load_members():
    """Keep one security per CIK, using longest ticker then lexical order."""
    with (ROOT / "constituents.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    primary = {}
    for row in sorted(rows, key=lambda r: (-len(r["Symbol"]), r["Symbol"])):
        primary.setdefault(int(row["CIK"]), row)
    return sorted(primary.values(), key=lambda r: r["Symbol"])


def load_master():
    """Use the fetched universe when present, otherwise the retained snapshot."""
    import pandas as pd
    cache = RAW / "sp500_master.parquet"
    if cache.exists():
        frame = pd.read_parquet(cache)
    else:
        frame = pd.read_csv(ROOT / "constituents.csv").rename(columns={
            "Symbol": "ticker", "Security": "company", "CIK": "cik",
            "GICS Sector": "gics_sector", "GICS Sub-Industry": "gics_sub_industry"})
    frame["ticker"] = frame["ticker"].str.replace(".", "-", regex=False)
    return frame


def primary_master():
    frame = load_master()
    return frame.assign(_length=frame.ticker.str.len()).sort_values(
        ["_length", "ticker"], ascending=[False, True]).drop_duplicates("cik").drop(columns="_length").sort_values("ticker")
