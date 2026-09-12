"""EPA GHGRP: Scope-1-Emissionen je US-Anlage, mit Konzernzuordnung.

Die einzige unabhaengig ueberpruefte, kostenlose Emissionsquelle auf
Anlagenebene. Zwei Tabellen aus Envirofacts:

* ``PUB_DIM_FACILITY``            -- Stammdaten inkl. Freitextfeld ``parent_company``
* ``PUB_FACTS_SECTOR_GHG_EMISSION`` -- CO2e je Anlage, Jahr, Sektor und Gas

Wichtig fuer den Bericht: die oeffentlich abrufbare Reihe endet mit dem
Berichtsjahr 2023. Berichtsjahr 2024 war im Mai 2025 einzureichen, ist aber
bis heute nicht veroeffentlicht.
"""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .base import DataSource, register, session

BASE = "https://data.epa.gov/efservice/{table}/year/{year}/rows/{start}:{end}/CSV"
CHUNK = 10000
YEARS = range(2018, 2024)  # 2024 ist nicht veroeffentlicht

# Die GHGRP-Tabelle mischt drei Arten von Meldern. ``sector_type`` trennt sie:
#   E = Direktemittent   -> echtes Scope 1 der meldenden Anlage
#   S = Lieferant        -> CO2, das *spaeter* beim Kunden entsteht
#   I = CO2-Injektion    -> eingelagertes, nicht ausgestossenes CO2
# Wer alles aufsummiert, verdreifacht die Zahl und rechnet einem Oelkonzern
# die Emissionen seiner Kunden als eigene an -- genau die Doppelzaehlung, die
# das GHG-Protokoll verbietet.
EMITTER_SECTORS = {2, 3, 4, 5, 6, 7, 8, 14, 15}

# Biogenes CO2 wird nach GHG-Protokoll getrennt ausgewiesen und nicht in die
# Brutto-Scope-1-Bilanz eingerechnet.
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
    description = "EPA-GHGRP-Anlagenstammdaten inkl. parent_company (2018-2023)"

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
        ]
        df = _fetch_table("PUB_DIM_FACILITY", keep)
        return df.drop_duplicates(["facility_id", "year"]).reset_index(drop=True)


@register
class EpaEmissionSource(DataSource):
    name = "epa_emission"
    endpoint = "https://data.epa.gov/efservice/PUB_FACTS_SECTOR_GHG_EMISSION/"
    description = "EPA-GHGRP-CO2e je Anlage und Jahr (2018-2023)"

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
