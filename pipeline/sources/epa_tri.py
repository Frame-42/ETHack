"""Retrieve EPA TRI toxic-release reports. Standardized parent names aid attribution; carcinogen flags allow separate totals. Raw release mass does not adjust for toxicity, exposure, or local harm, and is not assumed independent of emissions."""
from __future__ import annotations

import io

import pandas as pd

from .base import DataSource, register, session

BASIC = "https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/{year}_US/csv/"
# The prepared annual download can be slow to generate; use the configured cross-section year.
YEARS = (2023,)


@register
class EpaTriSource(DataSource):
    name = "epa_tri"
    endpoint = BASIC.format(year=2023)
    description = "Annual TRI facility releases with standardized parent names"

    def _fetch(self) -> pd.DataFrame:
        frames = []
        for year in YEARS:
            r = session().get(BASIC.format(year=year), timeout=900)
            if r.status_code != 200 or not r.text.strip():
                continue
            df = pd.read_csv(io.StringIO(r.text), low_memory=False)
            df.columns = [
                c.split(". ", 1)[-1].strip().lower().replace(" ", "_").replace("/", "_")
                for c in df.columns
            ]
            df["year"] = year
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
