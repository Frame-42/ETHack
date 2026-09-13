"""Retrieve EIA fuel and generation data for comparison with power-sector emissions. Differences can reflect reporting boundaries or attribution as well as errors. Read EIA_API_KEY from .env; registration is available at https://www.eia.gov/opendata/register.php."""
from __future__ import annotations

import time

import pandas as pd

from ..config import require_key
from .base import DataSource, register, session

BASE = "https://api.eia.gov/v2/electricity/facility-fuel/data/"
YEARS = range(2019, 2027)
PER_PAGE = 5000


@register
class EiaApiFacilityFuelSource(DataSource):
    name = "eia_api_facility_fuel"
    endpoint = BASE
    description = "EIA-923 plant fuel use and generation, API v2"

    def _fetch(self) -> pd.DataFrame:
        key = require_key("EIA_API_KEY", "https://www.eia.gov/opendata/register.php")
        rows: list[dict] = []
        for year in YEARS:
            offset = 0
            while True:
                params = {
                    "api_key": key,
                    "frequency": "annual",
                    "data[0]": "generation",
                    "data[1]": "total-consumption-btu",
                    "start": str(year),
                    "end": str(year),
                    "offset": offset,
                    "length": PER_PAGE,
                }
                r = session().get(BASE, params=params, timeout=180)
                if r.status_code != 200:
                    break
                payload = r.json().get("response", {})
                batch = payload.get("data", [])
                if not batch:
                    break
                rows.extend(batch)
                offset += PER_PAGE
                if offset >= int(payload.get("total", 0)):
                    break
                time.sleep(0.2)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # Keep total rows rather than adding totals to
        # fuel/technology subtotals and counting
        # generation twice.
        if "fuel2002" in df.columns:
            df = df[df["fuel2002"].astype(str).str.upper() == "ALL"]
        if "primeMover" in df.columns:
            df = df[df["primeMover"].astype(str).str.upper() == "ALL"]
        df["year"] = pd.to_numeric(df.get("period"), errors="coerce")
        for col in ("generation", "total-consumption-btu"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        keep = [
            c
            for c in ("plantCode", "plantName", "state", "primeMover", "fuel2002",
                      "generation", "total-consumption-btu", "year")
            if c in df.columns
        ]
        return (
            df[keep]
            .groupby([c for c in ("plantCode", "plantName", "state", "year") if c in keep],
                     as_index=False, dropna=False)
            .agg(
                generation_mwh=("generation", "sum"),
                consumption_mmbtu=("total-consumption-btu", "sum"),
            )
        )
