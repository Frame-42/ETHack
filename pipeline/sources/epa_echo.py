"""EPA ECHO: Verstoesse und Strafen -- Governance, gemessen statt behauptet.

Governance ist der Teilbereich, bei dem sich kommerzielle ESG-Anbieter am
staerksten widersprechen: Ihre Noten korrelieren dort nur mit etwa 0,30. Ein
Grund ist, dass sie ueberwiegend Strukturen bewerten -- Ausschuesse,
Richtlinien, Verguetungsregeln -- statt Verhalten.

ECHO fuehrt das Gegenteil: dokumentiertes Verhalten gegenueber
Umweltauflagen, je Anlage. Drei Rechtsgebiete auf einmal:

* **CAA** -- Luftreinhaltung
* **CWA** -- Gewaesserschutz, inklusive Einleitungsmessungen
* **RCRA** -- Abfall und Gefahrstoffe

Nutzbare Felder: ``FAC_TOTAL_PENALTIES`` (Strafsumme), ``FAC_PENALTY_COUNT``,
``FAC_INSPECTION_COUNT`` und ``FAC_QTRS_IN_NC`` -- die Zahl der Quartale in
Nichteinhaltung innerhalb der letzten drei Jahre. Letztere ist die
interessanteste: Sie misst Dauer statt Einzelereignis und laesst sich nicht
durch eine einmalige Zahlung bereinigen.

**Zuordnung.** ECHO fuehrt kein Konzernfeld, aber jede Anlage traegt ihre
FRS-Kennung (``REGISTRY_ID``). Dieselbe Kennung steht im GHGRP-Datensatz als
``frs_id``. Damit lassen sich ECHO-Anlagen ohne Namensabgleich an bereits
zugeordnete Konzerne haengen -- der praeziseste Weg, den dieses Projekt hat.

Die Bulk-Datei ist rund 408 MB gepackt.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from .base import DataSource, register, session

EXPORTER = "https://echo.epa.gov/files/echodownloads/echo_exporter.zip"

KEEP = [
    "REGISTRY_ID", "FAC_NAME", "FAC_STATE", "FAC_NAICS_CODES",
    "FAC_TOTAL_PENALTIES", "FAC_PENALTY_COUNT", "FAC_INSPECTION_COUNT",
    "FAC_QTRS_IN_NC", "FAC_COMPLIANCE_STATUS", "FAC_DATE_LAST_PENALTY",
    "CAA_QTRS_IN_NC", "CWA_QTRS_IN_NC", "RCRA_QTRS_IN_NC",
    "FAC_3YR_COMPLIANCE_HISTORY",
]


@register
class EpaEchoSource(DataSource):
    name = "epa_echo"
    endpoint = EXPORTER
    description = "ECHO-Konformitaetsakte je Anlage: Strafen, Inspektionen, Verstossquartale"

    def _fetch(self) -> pd.DataFrame:
        r = session().get(EXPORTER, timeout=1800, stream=False)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(name) as fh:
                df = pd.read_csv(
                    fh, low_memory=False,
                    usecols=lambda c: c.strip().upper() in {k.upper() for k in KEEP},
                )
        df.columns = [c.strip().lower() for c in df.columns]
        for col in ("fac_total_penalties", "fac_penalty_count",
                    "fac_inspection_count", "fac_qtrs_in_nc"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.reset_index(drop=True)
