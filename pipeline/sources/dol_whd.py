"""DOL Wage and Hour Division: Lohnverstöße -- das S in ESG, als Behördenakte.

Die Arbeitsschutzbehörde OSHA misst Unfälle. Die Wage and Hour Division misst
etwas anderes: ob Beschäftigte korrekt bezahlt wurden -- Mindestlohn,
Überstunden, Kinderarbeit, Saisonarbeitsvisa. Jeder abgeschlossene Fall nennt
den Arbeitgeber, die nachzuzahlende Lohnsumme und die Zahl der betroffenen
Beschäftigten.

Die Quelle hat Janis im Team gefunden; hier wird sie frisch aus der
Bulk-Datei gezogen, damit Stand und Filter nachvollziehbar bleiben.

**Zuordnung.** Die Datei trägt keinen CIK. Zugeordnet wird über den
bereinigten Rechts- und Handelsnamen, exakt oder über die Tochtertabelle --
bewusst ohne unscharfen Abgleich, weil Filialnamen wie "Walmart Supercenter
#1234" sonst beliebige Treffer erzeugen.

**Filter.** Fälle mit Feststellungsende 2022 bis 2024, wie in der
Team-Auswertung, damit beide Zahlenreihen vergleichbar sind.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from ..config import RAW
from .base import DataSource, register, session

BULK = "https://data.dol.gov/data-catalog/WHD/enforcement/WHD_enforcement.zip"
LOCAL = RAW / "dol" / "WHD_enforcement.zip"
KEEP = [
    "CASE_ID", "TRADE_NM", "LEGAL_NAME", "ST_CD", "NAIC_CD", "CASE_VIOLTN_CNT",
    "CMP_ASSD", "EE_VIOLTD_CNT", "BW_ATP_AMT", "EE_ATP_CNT", "FINDINGS_END_DATE",
    "FLSA_REPEAT_VIOLATOR", "FLSA_CL_VIOLTN_CNT", "FLSA_CL_MINOR_CNT",
]


@register
class DolWhdSource(DataSource):
    name = "dol_whd"
    endpoint = BULK
    description = "DOL-WHD-Verfahren mit Nachzahlungen, Feststellungsende 2022-2024"

    def _fetch(self) -> pd.DataFrame:
        if not LOCAL.exists():
            LOCAL.parent.mkdir(parents=True, exist_ok=True)
            r = session().get(BULK, timeout=1800)
            r.raise_for_status()
            LOCAL.write_bytes(r.content)
        frames = []
        with zipfile.ZipFile(LOCAL) as z:
            for name in sorted(n for n in z.namelist() if n.lower().endswith(".csv")):
                with z.open(name) as fh:
                    df = pd.read_csv(
                        io.TextIOWrapper(fh, encoding="utf-8", errors="replace"),
                        usecols=lambda c: c in KEEP, dtype=str, low_memory=False,
                    )
                end = pd.to_datetime(df["FINDINGS_END_DATE"], errors="coerce", utc=True)
                frames.append(df[(end.dt.year >= 2022) & (end.dt.year <= 2024)])
        df = pd.concat(frames, ignore_index=True)
        for col in ("CASE_VIOLTN_CNT", "CMP_ASSD", "EE_VIOLTD_CNT", "BW_ATP_AMT",
                    "EE_ATP_CNT", "FLSA_CL_VIOLTN_CNT", "FLSA_CL_MINOR_CNT"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.columns = [c.lower() for c in df.columns]
        return df.reset_index(drop=True)
