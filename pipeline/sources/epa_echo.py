"""Retrieve EPA ECHO enforcement/compliance records for air, water, and waste regulations. Match facilities through FRS registry IDs. Penalties and noncompliance histories provide a narrow governance-related signal, not a comprehensive measure of governance quality. The compliance window spans up to twelve quarters per facility."""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from .base import DataSource, register, session

EXPORTER = "https://echo.epa.gov/files/echodownloads/echo_exporter.zip"

KEEP = [
    "REGISTRY_ID", "FAC_NAME", "FAC_STATE", "FAC_NAICS_CODES",
    "FAC_TOTAL_PENALTIES", "FAC_PENALTY_COUNT", "FAC_INSPECTION_COUNT",
    "FAC_QTRS_IN_NC", "FAC_COMPLIANCE_STATUS", "FAC_DATE_LAST_PENALTY",
    "CAA_QTRS_IN_NC", "CWA_QTRS_IN_NC", "RCRA_QTRS_IN_NC",
    "FAC_3YR_COMPLIANCE_HISTORY",
]


@register
class EpaEchoSource(DataSource):
    name = "epa_echo"
    endpoint = EXPORTER
    description = "ECHO facility compliance: penalties, inspections, noncompliance quarters"

    def _fetch(self) -> pd.DataFrame:
        r = session().get(EXPORTER, timeout=1800, stream=False)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(name) as fh:
                df = pd.read_csv(
                    fh, low_memory=False,
                    usecols=lambda c: c.strip().upper() in {k.upper() for k in KEEP},
                )
        df.columns = [c.strip().lower() for c in df.columns]
        for col in ("fac_total_penalties", "fac_penalty_count",
                    "fac_inspection_count", "fac_qtrs_in_nc"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.reset_index(drop=True)
