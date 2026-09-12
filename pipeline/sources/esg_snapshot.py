"""Kommerzieller ESG-Snapshot als Vergleichsmassstab fuer Periode A.

Sustainalytics-ESG-Risk-Ratings, ueber Yahoo Finance abgegriffen und als CSV
oeffentlich gespiegelt. Genau die Sorte Datensatz, die auf Kaggle unter
verschiedenen Namen kursiert: eingefroren, abgeschrieben, ohne Lizenz.

Wir nutzen ihn ausschliesslich als *Vergleichsmassstab* -- nie als Eingabe in
die eigene Note. Die Frage, die er beantwortet: Wie stark stimmt eine
kommerzielle Note mit einer physisch gemessenen Rangliste ueberein?

Achtung bei der Richtung: ``esgScore.tot`` ist ein Risiko-Score.
Hoeher = schlechter.
"""
from __future__ import annotations

import io

import pandas as pd

from .base import DataSource, register, session

CSV = "https://raw.githubusercontent.com/sburstein/ESG-Stock-Data/main/sp_esg_stock_data.csv"


@register
class EsgSnapshotSource(DataSource):
    name = "esg_snapshot"
    endpoint = CSV
    description = "Kommerzielle ESG-Risk-Ratings (Sustainalytics via Yahoo), Stand 2021"

    def _fetch(self) -> pd.DataFrame:
        r = session().get(CSV, timeout=120)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df = df.rename(
            columns={
                "esgScore.tot": "esg_risk_total",
                "esgScore.env": "esg_risk_env",
                "esgScore.soc": "esg_risk_soc",
                "esgScore.gov": "esg_risk_gov",
                "esgRank.tot": "esg_percentile",
                "esgRating": "esg_rating_label",
                "asOf": "as_of",
                "Market.Cap": "market_cap_usd",
            }
        )
        keep = [
            "ticker",
            "company",
            "sector",
            "esg_risk_total",
            "esg_risk_env",
            "esg_risk_soc",
            "esg_risk_gov",
            "esg_percentile",
            "esg_rating_label",
            "as_of",
            "market_cap_usd",
        ]
        df = df[[c for c in keep if c in df.columns]].copy()
        df["ticker"] = df["ticker"].astype(str).str.strip().str.replace(".", "-", regex=False)
        return df.dropna(subset=["esg_risk_total"]).reset_index(drop=True)
