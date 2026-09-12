"""Jahresumsaetze aus SEC-XBRL -- der Nenner jeder Intensitaetskennzahl.

Statt 500 Einzelabfragen nutzen wir die ``frames``-API: eine Anfrage je
Konzept und Kalenderjahr liefert alle meldenden Firmen auf einmal. Die SEC
ordnet dabei abweichende Geschaeftsjahre dem passenden Kalenderrahmen zu.

Firmen taggen ihren Umsatz uneinheitlich, deshalb werden mehrere Konzepte in
Prioritaetsreihenfolge abgefragt; je Firma und Jahr gewinnt das erste, das
einen Wert liefert.
"""
from __future__ import annotations

import time

import pandas as pd

from .base import DataSource, get_json, register

FRAME = "https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/CY{year}.json"

# Reihenfolge = Prioritaet. ASC-606-Tag zuerst, dann die aelteren Varianten.
CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",  # Banken
]

YEARS = range(2016, 2026)


@register
class SecRevenueSource(DataSource):
    name = "sec_revenue"
    endpoint = "https://data.sec.gov/api/xbrl/frames/"
    description = "Jahresumsatz je CIK aus XBRL-Frames (FY2016-FY2025)"

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
        # Je CIK/Jahr das hoechstpriorisierte Konzept behalten.
        df = df.sort_values(["cik", "year", "prio"]).drop_duplicates(["cik", "year"])
        df["revenue_musd"] = df["revenue_usd"] / 1e6
        return df[["cik", "entity", "year", "revenue_musd", "concept"]].reset_index(drop=True)
