"""Retrieve eGRID plant emissions, generation, and operator/utility names. ORISPL identifies the plant, OPRNAME the operator, UTLSRVNM the utility, and PLNGENAN generation. Check the file's unit convention before converting CO2. Physical intensity can be calculated separately from these source observations; publication lag remains relevant."""
from __future__ import annotations

import io
import re

import pandas as pd

from .base import DataSource, register, session

DOWNLOAD_PAGE = "https://www.epa.gov/egrid/download-data"
FALLBACK = (
    "https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_metric_rev2.xlsx"
)
BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/140.0"}

KEEP = {
    "ORISPL": "oris_code",
    "PNAME": "plant_name",
    "PSTATABB": "state",
    "OPRNAME": "operator_name",
    "UTLSRVNM": "utility_name",
    "PLPRMFL": "primary_fuel",
    "PLNGENAN": "net_generation_mwh",
    "PLCO2AN": "co2_t",
    "PLCO2RTA": "co2_kg_per_mwh",
    "NAMEPCAP": "capacity_mw",
}


def _latest_url() -> str:
    """Locate the latest metric annual workbook on the download page."""
    try:
        r = session().get(DOWNLOAD_PAGE, headers=BROWSER, timeout=90)
        links = re.findall(r'href="([^"]*egrid\d{4}_data_metric[^"]*\.xlsx)"', r.text, re.I)
        if links:
            return sorted(links)[-1]
    except Exception:  # noqa: BLE001
        pass
    return FALLBACK


@register
class EgridSource(DataSource):
    name = "egrid_plant"
    endpoint = DOWNLOAD_PAGE
    description = "eGRID plant CO2, generation, and operator data"

    def _fetch(self) -> pd.DataFrame:
        url = _latest_url()
        r = session().get(url, headers=BROWSER, timeout=900)
        r.raise_for_status()
        xl = pd.ExcelFile(io.BytesIO(r.content))
        sheet = next(s for s in xl.sheet_names if s.upper().startswith("PLNT"))
        df = xl.parse(sheet, skiprows=1)
        df = df[[c for c in KEEP if c in df.columns]].rename(columns=KEEP)
        year = re.search(r"egrid(\d{4})", url)
        df["year"] = int(year.group(1)) if year else None
        for col in ("net_generation_mwh", "co2_t", "co2_kg_per_mwh", "capacity_mw"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df[df["net_generation_mwh"].notna()].reset_index(drop=True)
