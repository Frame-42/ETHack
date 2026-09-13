"""Read team snapshots from data/external/team, retaining original agency provenance and preparer attribution. The hard-variable snapshot was prepared by Janis (662d939); the WBA snapshot by Janis (24261f9)."""
from __future__ import annotations

import json

import pandas as pd

from ..config import DATA
from .base import DataSource, register

TEAM = DATA / "external" / "team"


@register
class TeamHardVariablesSource(DataSource):
    """Read Janis's cross-section of SEC finances, wage cases, and conflict-minerals filing information. Source columns retain detailed provenance."""

    name = "team_hard_variables"
    endpoint = "data/external/team/hard_variables.csv"
    description = "Janis: SEC FY2024 finances, DOL WHD 2022-2024, SEC Form SD filings"

    def _fetch(self) -> pd.DataFrame:
        df = pd.read_csv(TEAM / "hard_variables.csv", dtype=str)
        df["ticker"] = df["ticker"].str.strip().str.replace(".", "-", regex=False)
        return df


@register
class TeamWbaSource(DataSource):
    """Read WBA assessments from the team snapshot. Contextual footprint strings remain separate from numerical assessment fields."""

    name = "team_wba"
    endpoint = "data/external/team/wba_snapshot.json"
    description = "Janis: WBA ACT, Social, Nature, Just Transition (CC BY 4.0)"

    def _fetch(self) -> pd.DataFrame:
        snap = json.loads((TEAM / "wba_snapshot.json").read_text(encoding="utf-8"))
        rows = []
        for c in snap["companies"]:
            a = c.get("assessment")
            if not a:
                continue
            for t in c["tickers"]:
                rows.append(
                    {
                        "ticker": t.replace(".", "-"),
                        "wba_name": c["wba"]["name"],
                        "match_method": c["match_method"],
                        "tpq": a.get("tpq"),
                        "ctt": a.get("ctt"),
                        "act_grade": a.get("act_grade"),
                        "social": a.get("social"),
                        "nature": a.get("nature"),
                        "just_transition": a.get("just_transition"),
                        "profile_url": a["source"]["url"],
                        "retrieved_at": a["source"]["retrieved_at"],
                    }
                )
        return pd.DataFrame(rows)
