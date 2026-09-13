"""Retrieve SBTi target statuses from the published Excel download. Keep near-term status, target year, target class, and net-zero status separate. Target validation and withdrawal describe commitments; they are not measurements of achieved emissions reductions. Coverage depends on voluntary participation."""
from __future__ import annotations

import io

import pandas as pd

from .base import DataSource, register, session

EXCEL = "https://sciencebasedtargets.org/download/excel"


@register
class SbtiTargetSource(DataSource):
    name = "sbti_targets"
    endpoint = EXCEL
    description = "SBTi organization target statuses (near-term, net-zero, classification)"

    def _fetch(self) -> pd.DataFrame:
        r = session().get(EXCEL, timeout=180, allow_redirects=True)
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content))
        keep = {
            "company_name": "company_name",
            "isin": "isin",
            "lei": "lei",
            "sector": "sbti_sector",
            "location": "location",
            "near_term_status": "near_term_status",
            "near_term_target_classification": "near_term_class",
            "near_term_target_year": "near_term_year",
            "long_term_status": "long_term_status",
            "net_zero_status": "net_zero_status",
            "net_zero_year": "net_zero_year",
        }
        df = df[[c for c in keep if c in df.columns]].rename(columns=keep)
        # Normalize numeric and FY-prefixed target years.
        for col in ("near_term_year", "net_zero_year"):
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.extract(r"(\d{4})")[0], errors="coerce"
                ).astype("Int64")
        df["commitment_removed"] = (
            df["near_term_status"].astype(str).str.contains("removed", case=False)
            | df["net_zero_status"].astype(str).str.contains("removed", case=False)
        )
        df["has_validated_target"] = (
            df["near_term_status"].astype(str).str.contains("Targets set", case=False)
        )
        return df.reset_index(drop=True)
