"""OSHA ITA: Arbeitsunfaelle -- das S in ESG, als harte Zahl.

Die soziale Dimension wird in ESG-Bewertungen fast durchgaengig aus
Selbstauskuenften und Richtlinientexten gebildet. Fuer US-Betriebsstaetten
gibt es eine Alternative: die Meldungen nach OSHA-Formular 300A. Sie enthalten
gearbeitete Stunden, Beschaeftigtenzahl und Faelle mit Arbeitsausfall.

Daraus laesst sich die **DART-Rate** berechnen, die Standardkennzahl der
US-Arbeitssicherheit::

    DART = (Faelle mit Arbeitsausfall + Faelle mit Einschraenkung) * 200000
           / gearbeitete Stunden

Der Faktor 200 000 entspricht 100 Vollzeitkraeften in einem Jahr; die Rate ist
damit zwischen Betrieben unterschiedlicher Groesse vergleichbar.

Wichtig fuer die Zuordnung: die Datei enthaelt ``company_name`` neben dem
Betriebsstaettennamen -- die Aggregation auf Konzernebene ist also vorgesehen.

**Zugang.** Der Server lehnt Anfragen ohne vollstaendige Browser-Kopfzeilen mit
403 ab; insbesondere ``Accept-Encoding`` muss gesetzt sein.
"""
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
    "establishment_name", "company_name", "ein", "state", "naics_code",
    "industry_description", "size", "annual_average_employees",
    "total_hours_worked", "total_deaths", "total_dafw_cases",
    "total_djtr_cases", "total_other_cases", "total_injuries", "year_filing_for",
]


@register
class OshaItaSource(DataSource):
    name = "osha_ita"
    endpoint = FILES[2025]
    description = "OSHA-300A-Meldungen je Betriebsstaette (Unfallraten), 2023-2025"

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

        # Kennungsfelder kommen je nach Jahrgang als Zahl oder als Text.
        for col in ("ein", "naics_code", "size", "state"):
            if col in df.columns:
                df[col] = df[col].astype(str)

        hours = pd.to_numeric(df.get("total_hours_worked"), errors="coerce")
        dafw = pd.to_numeric(df.get("total_dafw_cases"), errors="coerce").fillna(0)
        djtr = pd.to_numeric(df.get("total_djtr_cases"), errors="coerce").fillna(0)
        df["dart_rate"] = ((dafw + djtr) * 200000 / hours).where(hours > 0)
        return df.reset_index(drop=True)
