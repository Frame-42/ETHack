"""SBTi-Zieldatenbank -- die Luecke der Greenwashing-Achse.

Im ersten Bericht stand, die Science Based Targets initiative habe kein
oeffentliches API und man muesse die Dashboard-Seite mit einem Headless-Browser
abgreifen. Das war zu pessimistisch: ``/download/excel`` leitet auf eine
veroeffentlichte Tabelle weiter und liefert den vollstaendigen Datensatz als
xlsx -- ohne Anmeldung, ohne Schluessel, 15 605 Organisationen.

Was daraus wird:

``sbti_near_term_status``      gesetzt / zugesagt / zurueckgezogen
``sbti_near_term_year``        das Zwischenzieljahr -- Warnsignal 1
``sbti_target_class``          1,5 Grad, deutlich unter 2 Grad, 2 Grad
``sbti_net_zero_year``         Netto-null-Jahr
``sbti_commitment_removed``    Zusage zurueckgezogen -- eigenes Warnsignal

Der Status ``Commitment removed`` ist der interessanteste Wert im Datensatz.
Eine Firma, die sich ein Ziel gesetzt und es spaeter zurueckgezogen hat, sagt
mehr ueber ihre Glaubwuerdigkeit als jede Selbstbeschreibung.

Abdeckung im S&P 500 spiegelt die EPA-Abdeckung: stark bei Technologie,
Gesundheit und Immobilien, schwach bei Versorgern, null bei Energie. Die
beiden Quellen ergaenzen sich fast perfekt.
"""
from __future__ import annotations

import io

import pandas as pd

from .base import DataSource, register, session

EXCEL = "https://sciencebasedtargets.org/download/excel"


@register
class SbtiTargetSource(DataSource):
    name = "sbti_targets"
    endpoint = EXCEL
    description = "SBTi-Zielstatus je Organisation (Nahziel, Netto-null, Klassifizierung)"

    def _fetch(self) -> pd.DataFrame:
        r = session().get(EXCEL, timeout=180, allow_redirects=True)
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content))
        keep = {
            "company_name": "company_name",
            "isin": "isin",
            "lei": "lei",
            "sector": "sbti_sector",
            "location": "location",
            "near_term_status": "near_term_status",
            "near_term_target_classification": "near_term_class",
            "near_term_target_year": "near_term_year",
            "long_term_status": "long_term_status",
            "net_zero_status": "net_zero_status",
            "net_zero_year": "net_zero_year",
        }
        df = df[[c for c in keep if c in df.columns]].rename(columns=keep)
        # Zieljahre kommen gemischt als Zahl und als "FY2030" -- vereinheitlichen.
        for col in ("near_term_year", "net_zero_year"):
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.extract(r"(\d{4})")[0], errors="coerce"
                ).astype("Int64")
        df["commitment_removed"] = (
            df["near_term_status"].astype(str).str.contains("removed", case=False)
            | df["net_zero_status"].astype(str).str.contains("removed", case=False)
        )
        df["has_validated_target"] = (
            df["near_term_status"].astype(str).str.contains("Targets set", case=False)
        )
        return df.reset_index(drop=True)
