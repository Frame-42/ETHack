"""Retrieve EPA CAMPD power-sector emissions and ownership/operator metadata. Its reporting cadence supplements the fixed GHGRP study window, but its coverage is limited to participating power facilities. Owner/operator roles permit different attribution approaches; this implementation must not be mistaken for a full equity-share allocation. Access uses EPA_CAMD_API_KEY or the limited DEMO_KEY fallback."""
from __future__ import annotations

import os
import time

import pandas as pd

from ..config import _load_env  # Load .env during configuration import.
from .base import DataSource, register, session

BASE = "https://api.epa.gov/easey"
PER_PAGE = 500  # API page-size limit.
YEARS = range(2019, 2027)


def api_key() -> str:
    """Read the EPA key, falling back to a rate-limited demo key."""
    return os.environ.get("EPA_CAMD_API_KEY") or "DEMO_KEY"


def _paged(path: str, params: dict, max_pages: int = 40) -> list[dict]:
    """Retrieve all pages of a CAMPD endpoint."""
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        q = {**params, "page": page, "perPage": PER_PAGE}
        r = session().get(
            f"{BASE}/{path}", params=q, headers={"x-api-key": api_key()}, timeout=120
        )
        if r.status_code == 429:
            raise RuntimeError(
                "CAMPD rate limit reached. Register for a key at "
                "https://www.epa.gov/power-sector/cam-api-portal and "
                "set EPA_CAMD_API_KEY."
            )
        r.raise_for_status()
        payload = r.json()
        # Handle either a plain list or an object
        # containing items.
        rows = payload.get("items", []) if isinstance(payload, dict) else payload
        if not rows:
            break
        out.extend(rows)
        total = int(r.headers.get("x-total-count", 0))
        if len(out) >= total or len(rows) < PER_PAGE:
            break
        time.sleep(0.3)
    return out


@register
class EpaCampdEmissionSource(DataSource):
    name = "campd_emission"
    endpoint = f"{BASE}/emissions-mgmt/emissions/apportioned/annual"
    description = "Annual power-unit CO2 reports, 2019 onward"

    def _fetch(self) -> pd.DataFrame:
        frames = []
        for year in YEARS:
            rows = _paged("emissions-mgmt/emissions/apportioned/annual", {"year": year})
            if not rows:
                continue
            df = pd.DataFrame(rows)
            keep = [
                c
                for c in ("facilityId", "facilityName", "unitId", "year",
                          "co2Mass", "grossLoad", "heatInput", "primaryFuelInfo",
                          "stateCode")
                if c in df.columns
            ]
            frames.append(df[keep])
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        # Convert co2Mass from US short tons to metric tonnes.
        df["co2_t"] = pd.to_numeric(df["co2Mass"], errors="coerce") * 0.90718474
        return (
            df.groupby(["facilityId", "year"], as_index=False)
            .agg(
                facility_name=("facilityName", "first"),
                state=("stateCode", "first"),
                co2_t=("co2_t", "sum"),
                gross_load_mwh=("grossLoad", "sum"),
                n_units=("unitId", "nunique"),
            )
        )


@register
class EpaCampdFacilitySource(DataSource):
    name = "campd_facility"
    endpoint = f"{BASE}/facilities-mgmt/facilities/attributes"
    description = "Plant metadata with separate owners and operators"

    def _fetch(self) -> pd.DataFrame:
        frames = []
        for year in YEARS:
            rows = _paged("facilities-mgmt/facilities/attributes", {"year": year})
            if not rows:
                continue
            df = pd.DataFrame(rows)
            keep = [
                c
                # programCodeInfo distinguishes CO2-reporting
                # programs from NOx-only programs whose zero
                # CO2 field is not a measured zero.
                for c in ("facilityId", "facilityName", "year", "ownerOperator",
                          "sourceCategory", "primaryFuelInfo", "stateCode",
                          "operatingStatus", "programCodeInfo")
                if c in df.columns
            ]
            frames.append(df[keep])
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        return df.drop_duplicates(["facilityId", "year"]).reset_index(drop=True)


def split_owner_operator(raw: str) -> list[tuple[str, str]]:
    """Parse ownerOperator into (name, role) pairs. Owner and operator are distinct roles; fractional ownership is not inferred here."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    out: list[tuple[str, str]] = []
    for part in raw.split("|"):
        part = part.strip()
        if not part:
            continue
        role = "unknown"
        if "(" in part and part.endswith(")"):
            name, _, tail = part.rpartition("(")
            role = tail.rstrip(")").strip().lower()
            part = name.strip()
        out.append((part, role))
    return out
