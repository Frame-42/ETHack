"""EIA-API: Brennstoffverbrauch je Kraftwerk -- die unabhaengige Gegenprobe.

CAMPD misst am Schornstein, die EIA erhebt den Brennstoffeinsatz. Beide Wege
fuehren zur selben Groesse, aber ueber voellig getrennte Meldeketten. Wo sie
weit auseinanderliegen, stimmt etwas nicht -- entweder in den Daten oder in
unserer Zurechnung.

Das ist die einzige unabhaengige Kontrolle, die dieses Projekt hat. Alles
andere ist Plausibilitaet.

**Zugang.** Kostenloser Schluessel von https://www.eia.gov/opendata/register.php,
gelesen aus ``EIA_API_KEY`` in der ``.env``.
"""
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
    description = "EIA-923 Brennstoffeinsatz und Erzeugung je Kraftwerk (API v2)"

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
        # Die API liefert je Kraftwerk sowohl Einzelzeilen je Brennstoff und
        # Antriebsart als auch eine Summenzeile. Nur die Summe behalten, sonst
        # wird jedes Kraftwerk mehrfach gezaehlt.
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
