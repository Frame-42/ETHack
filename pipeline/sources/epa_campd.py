"""EPA CAMPD: die Antwort auf die Datenluecke nach 2023.

Das GHGRP-Programm (siehe ``epa_ghgrp``) veroeffentlicht mit jahrelanger
Verzoegerung -- Berichtsjahr 2024 ist bis heute nicht draussen. Die Clean Air
Markets Program Data stammen aus einem voellig anderen Meldeweg: kontinuierliche
Emissionsmessung (CEMS) an Kraftwerksbloecken, quartalsweise veroeffentlicht
mit zwei bis drei Monaten Verzug. Damit reicht die Reihe bis ins laufende Jahr.

Zwei Dinge machen diese Quelle ueber die Aktualitaet hinaus wertvoll:

1. **Gemessen statt gerechnet.** CEMS misst am Schornstein, statt Emissionen
   aus Brennstoffmengen hochzurechnen.
2. **Eigentuemer und Betreiber getrennt.** Das Feld ``ownerOperator`` nennt
   beide Rollen einzeln. Damit laesst sich die Zurechnung nach Equity Share
   *und* nach operativer Kontrolle rechnen -- bisher steckte diese
   Ermessensentscheidung unsichtbar im Code.

Die Grenze: nur Stromerzeugung. Anlagen ausserhalb der Handelsprogramme
(Raffinerien, Zementwerke, Chemie) fehlen vollstaendig.

**Zugang.** Die API verlangt einen kostenlosen Schluessel von
https://www.epa.gov/power-sector/cam-api-portal. Ohne Schluessel greift
``DEMO_KEY`` mit rund 30 Anfragen je Stunde -- genug fuer einen Durchlauf,
zu wenig fuer regelmaessigen Betrieb. Der Schluessel wird aus der
Umgebungsvariable ``EPA_CAMD_API_KEY`` gelesen.
"""
from __future__ import annotations

import os
import time

import pandas as pd

from ..config import _load_env  # laedt .env beim Import
from .base import DataSource, register, session

BASE = "https://api.epa.gov/easey"
PER_PAGE = 500  # Obergrenze der API
YEARS = range(2019, 2027)


def api_key() -> str:
    """Schluessel aus .env; ohne ihn greift DEMO_KEY mit 10 Anfragen je Stunde."""
    return os.environ.get("EPA_CAMD_API_KEY") or "DEMO_KEY"


def _paged(path: str, params: dict, max_pages: int = 40) -> list[dict]:
    """Holt alle Seiten eines CAMPD-Endpunkts."""
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        q = {**params, "page": page, "perPage": PER_PAGE}
        r = session().get(
            f"{BASE}/{path}", params=q, headers={"x-api-key": api_key()}, timeout=120
        )
        if r.status_code == 429:
            raise RuntimeError(
                "CAMPD-Kontingent erschoepft. Eigenen Schluessel unter "
                "https://www.epa.gov/power-sector/cam-api-portal anfordern und "
                "als EPA_CAMD_API_KEY setzen."
            )
        r.raise_for_status()
        payload = r.json()
        # Je nach Endpunkt kommt entweder eine blanke Liste oder ein Objekt
        # mit dem Schluessel "items" zurueck.
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
    description = "CEMS-gemessenes CO2 je Kraftwerksblock und Jahr (2019 bis heute)"

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
        # co2Mass kommt in short tons -> in metrische Tonnen umrechnen.
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
    description = "Kraftwerks-Stammdaten inkl. getrennter Eigentuemer- und Betreiberangabe"

    def _fetch(self) -> pd.DataFrame:
        frames = []
        for year in YEARS:
            rows = _paged("facilities-mgmt/facilities/attributes", {"year": year})
            if not rows:
                continue
            df = pd.DataFrame(rows)
            keep = [
                c
                for c in ("facilityId", "facilityName", "year", "ownerOperator",
                          "sourceCategory", "primaryFuelInfo", "stateCode",
                          "operatingStatus")
                if c in df.columns
            ]
            frames.append(df[keep])
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        return df.drop_duplicates(["facilityId", "year"]).reset_index(drop=True)


def split_owner_operator(raw: str) -> list[tuple[str, str]]:
    """Zerlegt ``ownerOperator`` in ``[(Name, Rolle), ...]``.

    Das Feld sieht so aus::

        Alabama Power Company (Owner)|Alabama Power Company (Operator)

    Rollen sind ``Owner``, ``Operator`` und gelegentlich beides. Die Trennung
    erlaubt beide Zurechnungsregeln des GHG-Protokolls: Equity Share folgt den
    Eigentuemern, operative Kontrolle folgt dem Betreiber.
    """
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
