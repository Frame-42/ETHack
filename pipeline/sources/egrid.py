"""eGRID: CO2 je Megawattstunde, je Kraftwerk, mit Betreibernamen.

Die Frage nach einem physischen Nenner laesst sich fuer den Stromsektor ohne
eigene Rechnung beantworten. Die EPA fuehrt mit eGRID eine Datenbank, die
Emissionen aus dem Messprogramm und Erzeugung aus den EIA-Formularen bereits
auf Kraftwerksebene zusammenfuehrt -- einschliesslich Betreiber- und
Versorgernamen.

Damit entfaellt die Bruecke zwischen zwei Kennungssystemen, die sonst ueber
ORIS-Codes gebaut werden muesste. Relevante Felder:

``ORISPL``    ORIS-Kraftwerkskennung, der Schluessel zu EIA und CAMPD
``OPRNAME``   Betreiber
``UTLSRVNM``  Versorgungsunternehmen
``PLNGENAN``  Nettoerzeugung im Jahr, MWh
``PLCO2AN``   CO2 im Jahr, metrische Tonnen (in der metrischen Ausgabe)
``PLCO2RTA``  CO2-Rate, kg je MWh

Die Kennzahl ``t CO2 je MWh`` ist gegen Preisschwankungen immun -- anders als
``t CO2 je Umsatzdollar``, wo ein Jahr mit hohen Grosshandelspreisen einen
Versorger sauberer aussehen laesst, ohne dass sich physisch etwas aendert.

Grenze: nur Stromerzeugung, und der Datensatz erscheint mit rund zwei Jahren
Verzug. Fuer aktuellere Jahre ist CAMPD zusammen mit EIA-923 der Weg.
"""
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
    """Findet die neueste metrische Jahresdatei auf der Downloadseite."""
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
    description = "eGRID-Kraftwerksdaten: CO2, Erzeugung und Betreiber je Anlage"

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
