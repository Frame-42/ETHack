"""Read the retained S&P 500 membership snapshot, shared with the economic model. Update constituents.csv deliberately to change the study universe."""
from __future__ import annotations

import pandas as pd

from .base import DataSource, register


@register
class Sp500MasterSource(DataSource):
    name = "sp500_master"
    endpoint = "constituents.csv"
    description = "S&P 500 constituents with GICS sector, sub-industry, and CIK"

    def _fetch(self) -> pd.DataFrame:
        from ..config import ROOT
        df = pd.read_csv(ROOT / "constituents.csv")
        df = df.rename(
            columns={
                "Symbol": "ticker",
                "Security": "company",
                "GICS Sector": "gics_sector",
                "GICS Sub-Industry": "gics_sub_industry",
                "CIK": "cik",
                "Date added": "date_added",
            }
        )
        keep = ["ticker", "company", "gics_sector", "gics_sub_industry", "cik"]
        df = df[keep].copy()
        df["ticker"] = df["ticker"].astype(str).str.strip().str.replace(".", "-", regex=False)
        df["company"] = df["company"].astype(str).str.strip()
        df["gics_sector"] = df["gics_sector"].astype(str).str.strip()
        df["gics_sub_industry"] = df["gics_sub_industry"].astype(str).str.strip()
        df["cik"] = pd.to_numeric(df["cik"], errors="coerce").astype("Int64")
        return df.dropna(subset=["cik"]).reset_index(drop=True)
