"""EPA TRI: Giftstofffreisetzung -- eine zweite Umweltdimension.

Bisher misst die Kernnote ausschliesslich CO2. Das ist eine Dimension, und
zwei der drei Kennzahlen daraus sind miteinander korreliert. Das Toxics
Release Inventory liefert eine davon unabhaengige Groesse: wie viel giftiger
Stoff eine Anlage in Luft, Wasser und Boden abgibt.

Zwei Dinge machen TRI fuer dieses Projekt besonders wertvoll:

1. **Die EPA hat die Konzernzuordnung schon gemacht.** Das Feld
   ``standardized_parent_company`` ist ein bereinigter Konzernname -- genau
   die Arbeit, die bei GHGRP von Hand nachgebaut werden musste.
2. **Ein Krebserreger-Kennzeichen.** Nicht jede Tonne ist gleich. TRI weist
   aus, welche Stoffe als krebserregend eingestuft sind, was eine gewichtete
   Auswertung erlaubt statt einer blossen Massensumme.

Bezogen ueber die vorbereitete Jahresdatei von Envirofacts, nicht ueber die
Einzeltabellen -- die Freisetzungstabelle allein hat 32 Millionen Zeilen.
"""
from __future__ import annotations

import io

import pandas as pd

from .base import DataSource, register, session

BASIC = "https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/{year}_US/csv/"
# Der Endpunkt erzeugt die Datei bei jedem Abruf neu und braucht dafuer rund
# sieben Minuten je Jahr. Fuer eine Querschnittsdimension genuegt ein Jahr.
YEARS = (2023,)


@register
class EpaTriSource(DataSource):
    name = "epa_tri"
    endpoint = BASIC.format(year=2023)
    description = "TRI-Freisetzungen je Anlage und Jahr, mit bereinigtem Konzernnamen"

    def _fetch(self) -> pd.DataFrame:
        frames = []
        for year in YEARS:
            r = session().get(BASIC.format(year=year), timeout=900)
            if r.status_code != 200 or not r.text.strip():
                continue
            df = pd.read_csv(io.StringIO(r.text), low_memory=False)
            df.columns = [
                c.split(". ", 1)[-1].strip().lower().replace(" ", "_").replace("/", "_")
                for c in df.columns
            ]
            df["year"] = year
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
