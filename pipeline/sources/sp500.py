"""S&P-500-Konstituenten: Ticker, Name, GICS-Branche, CIK.

Diese Quelle ist das Rueckgrat der Pipeline. Sie definiert die Grundgesamtheit,
die Branchengruppe fuer den relativen Vergleich und ueber die CIK die Bruecke
zur SEC.
"""
from __future__ import annotations

import io

import pandas as pd

from .base import DataSource, register, session

WIKI = (
    "https://en.wikipedia.org/w/api.php?action=parse"
    "&page=List_of_S%26P_500_companies&prop=text&format=json"
)


@register
class Sp500MasterSource(DataSource):
    name = "sp500_master"
    endpoint = WIKI
    description = "S&P-500-Konstituenten mit GICS-Sektor, Sub-Industry und CIK"

    def _fetch(self) -> pd.DataFrame:
        r = session().get(WIKI, timeout=60)
        r.raise_for_status()
        html = r.json()["parse"]["text"]["*"]
        tables = pd.read_html(io.StringIO(html))
        # Die Konstituenten-Tabelle ist die einzige mit einer CIK-Spalte.
        df = next(t for t in tables if "CIK" in t.columns and "Symbol" in t.columns)
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
