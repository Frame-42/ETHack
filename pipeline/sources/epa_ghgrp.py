"""Retrieve GHGRP facility metadata and emissions by facility, year, sector, and gas from Envirofacts. Separate direct emitters, suppliers, injection, and biogenic CO2. The study is configured through 2023; that cutoff is not a live claim about EPA publication availability."""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .base import DataSource, register, session

BASE = "https://data.epa.gov/efservice/{table}/year/{year}/rows/{start}:{end}/CSV"
CHUNK = 10000
YEARS = range(2018, 2024)  # Fixed study-window endpoint.

# sector_type separates direct emitters (E),
# suppliers (S), and injection (I). Summing all
# three would mix operational emissions with
# supplied fuels and injected CO2, creating
# incompatible boundaries and double counting.
EMITTER_SECTORS = {2, 3, 4, 5, 6, 7, 8, 14, 15}

# Exclude biogenic CO2 from this direct- emissions total; it requires separate accounting.
BIOGENIC_GAS_ID = 8


def _chunk(table: str, year: int, start: int) -> pd.DataFrame:
    url = BASE.format(table=table, year=year, start=start, end=start + CHUNK - 1)
    r = session().get(url, timeout=300)
    r.raise_for_status()
    if not r.text.strip():
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(r.text), low_memory=False)


def _count(table: str, year: int) -> int:
    url = f"https://data.epa.gov/efservice/{table}/year/{year}/COUNT/JSON"
    r = session().get(url, timeout=120)
    r.raise_for_status()
    return int(r.json()[0]["TOTALQUERYRESULTS"])


def _fetch_table(table: str, keep: list[str]) -> pd.DataFrame:
    jobs: list[tuple[str, int, int]] = []
    for year in YEARS:
        n = _count(table, year)
        for start in range(0, n, CHUNK):
            jobs.append((table, year, start))
    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for df in pool.map(lambda j: _chunk(*j), jobs):
            if not df.empty:
                frames.append(df[[c for c in keep if c in df.columns]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


@register
class EpaFacilitySource(DataSource):
    name = "epa_facility"
    endpoint = "https://data.epa.gov/efservice/PUB_DIM_FACILITY/"
    description = "GHGRP facility metadata including parent_company, 2018-2023"

    def _fetch(self) -> pd.DataFrame:
        keep = [
            "facility_id",
            "year",
            "facility_name",
            "parent_company",
            "naics_code",
            "state",
            "city",
            "facility_types",
            "cems_used",
            # FRS identifiers link ECHO/TRI records without
            # another facility-name match.
            "frs_id",
        ]
        df = _fetch_table("PUB_DIM_FACILITY", keep)
        return df.drop_duplicates(["facility_id", "year"]).reset_index(drop=True)


@register
class EpaEmissionSource(DataSource):
    name = "epa_emission"
    endpoint = "https://data.epa.gov/efservice/PUB_FACTS_SECTOR_GHG_EMISSION/"
    description = "GHGRP annual facility CO2e, 2018-2023"

    def _fetch(self) -> pd.DataFrame:
        keep = ["facility_id", "year", "sector_id", "subsector_id", "gas_id", "co2e_emission"]
        df = _fetch_table("PUB_FACTS_SECTOR_GHG_EMISSION", keep)
        if df.empty:
            return df
        df = df.drop_duplicates(["facility_id", "year", "sector_id", "subsector_id", "gas_id"])

        supplied = (
            df[~df["sector_id"].isin(EMITTER_SECTORS)]
            .groupby(["facility_id", "year"], as_index=False)["co2e_emission"]
            .sum()
            .rename(columns={"co2e_emission": "supplied_t"})
        )

        direct = df[df["sector_id"].isin(EMITTER_SECTORS)]
        biogenic = (
            direct[direct["gas_id"] == BIOGENIC_GAS_ID]
            .groupby(["facility_id", "year"], as_index=False)["co2e_emission"]
            .sum()
            .rename(columns={"co2e_emission": "biogenic_t"})
        )
        out = (
            direct[direct["gas_id"] != BIOGENIC_GAS_ID]
            .groupby(["facility_id", "year"], as_index=False)["co2e_emission"]
            .sum()
            .rename(columns={"co2e_emission": "scope1_t"})
        )
        out = out.merge(biogenic, on=["facility_id", "year"], how="left")
        out = out.merge(supplied, on=["facility_id", "year"], how="outer")
        return out.fillna({"scope1_t": 0.0, "biogenic_t": 0.0, "supplied_t": 0.0})
