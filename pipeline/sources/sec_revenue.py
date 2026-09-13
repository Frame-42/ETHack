"""Retrieve annual revenue through SEC XBRL frames. Query concepts in priority order and keep the first available value per CIK/year. Calendar frames can differ from companies' fiscal-year boundaries."""
from __future__ import annotations

import time

import pandas as pd

from .base import DataSource, get_json, register

FRAME = "https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/CY{year}.json"

# Concept priority: ASC 606 first, then older revenue tags.
CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",  # Bank revenue tags.
]

YEARS = range(2016, 2026)


@register
class SecRevenueSource(DataSource):
    name = "sec_revenue"
    endpoint = "https://data.sec.gov/api/xbrl/frames/"
    description = "Annual revenue per CIK from XBRL frames, 2016-2025"

    def _fetch(self) -> pd.DataFrame:
        rows: list[dict] = []
        for year in YEARS:
            for prio, concept in enumerate(CONCEPTS):
                data = get_json(FRAME.format(concept=concept, year=year), pause=0.12)
                if not data:
                    continue
                for rec in data.get("data", []):
                    rows.append(
                        {
                            "cik": rec["cik"],
                            "entity": rec.get("entityName", ""),
                            "year": year,
                            "revenue_usd": rec["val"],
                            "concept": concept,
                            "prio": prio,
                        }
                    )
                time.sleep(0.1)
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        # Keep the highest-priority concept for each CIK and year.
        df = df.sort_values(["cik", "year", "prio"]).drop_duplicates(["cik", "year"])
        df["revenue_musd"] = df["revenue_usd"] / 1e6
        return df[["cik", "entity", "year", "revenue_musd", "concept"]].reset_index(drop=True)
