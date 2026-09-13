"""Retrieve OSHA Form 300A establishment reports: hours, employee counts, injuries, and deaths. A DART rate can be derived as (days-away cases + restricted-duty/transfer cases) * 200000 / hours, but the observation table retains counts and hours separately. Company-name fields aid attribution but do not establish parent ownership. HTTP access may require browser-style headers."""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from .base import DataSource, register, session

FILES = {
    2023: "https://www.osha.gov/sites/default/files/ITA_300A_Summary_Data_2023_through_12-31-2024.zip",
    2024: "https://www.osha.gov/sites/default/files/ITA_300A_Summary_Data_2024_through_12-31-2025.zip",
    2025: "https://www.osha.gov/sites/default/files/ITA_300A_Summary_Data_2025_through_03-15-2026_v2.csv",
}

BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

KEEP = [
    "establishment_name", "company_name", "one", "state", "naics_code",
    "industry_description", "size", "annual_average_employees",
    "total_hours_worked", "total_deaths", "total_dafw_cases",
    "total_djtr_cases", "total_other_cases", "total_injuries", "year_filing_for",
]


@register
class OshaItaSource(DataSource):
    name = "osha_ita"
    endpoint = FILES[2025]
    description = "OSHA Form 300A establishment reports, 2023-2025"

    def _fetch(self) -> pd.DataFrame:
        frames = []
        for year, url in FILES.items():
            r = session().get(url, headers=BROWSER, timeout=600)
            if r.status_code != 200:
                continue
            if url.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    names = [n for n in z.namelist() if n.lower().endswith(".csv")]
                    if not names:
                        continue
                    with z.open(names[0]) as fh:
                        df = pd.read_csv(fh, low_memory=False)
            else:
                df = pd.read_csv(io.StringIO(r.text), low_memory=False)
            df.columns = [c.strip().lower() for c in df.columns]
            df["year"] = year
            frames.append(df[[c for c in KEEP if c in df.columns] + ["year"]])
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)

        # Normalize identifier types across annual releases.
        for col in ("one", "naics_code", "size", "state"):
            if col in df.columns:
                df[col] = df[col].astype(str)

        hours = pd.to_numeric(df.get("total_hours_worked"), errors="coerce")
        dafw = pd.to_numeric(df.get("total_dafw_cases"), errors="coerce").fillna(0)
        djtr = pd.to_numeric(df.get("total_djtr_cases"), errors="coerce").fillna(0)
        df["dart_rate"] = ((dafw + djtr) * 200000 / hours).where(hours > 0)
        return df.reset_index(drop=True)
