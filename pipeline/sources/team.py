"""Datensätze aus dem Team, die bereits im Repository liegen.

Drei Kolleginnen und Kollegen haben parallel eigene Quellen erschlossen. Ihre
Dateien werden hier nicht neu abgerufen, sondern aus ``data/external/team``
gelesen -- sie sind der Stand, auf den sich ihre eigenen Auswertungen
beziehen. Die Herkunft wird dabei nicht auf "Team" verkürzt: Jeder Wert
behält die Behörde oder Organisation, von der er ursprünglich stammt, und
zusätzlich den Vermerk, wer ihn aufbereitet hat.

``sp500_harte_variablen.csv``   Janis, Commit 662d939
``mycelium_constituents.xlsx``  Phurinont, Commit c57cc92
``wba_snapshot.json``           Janis (feat/sustainability-observatory), Commit 24261f9
"""
from __future__ import annotations

import json

import pandas as pd

from ..config import DATA
from .base import DataSource, register

TEAM = DATA / "external" / "team"


@register
class TeamHardVariablesSource(DataSource):
    """Janis' Querschnitt: SEC-Finanzen, DOL-Lohnverstöße, Konfliktmineralien.

    Die zweite Zeile der Datei erklärt jede Spalte ("Bedeutung: ...") und wird
    übersprungen. Jede Zeile trägt in ``*_source`` die exakte Herkunft.
    """

    name = "team_harte_variablen"
    endpoint = "data/external/team/sp500_harte_variablen.csv"
    description = "Janis: SEC-Finanzen FY2024, DOL WHD 2022-2024, SEC SD-Meldungen"

    def _fetch(self) -> pd.DataFrame:
        df = pd.read_csv(TEAM / "sp500_harte_variablen.csv", skiprows=[1], dtype=str)
        df["ticker"] = df["ticker"].str.strip().str.replace(".", "-", regex=False)
        return df


@register
class TeamMyceliumSource(DataSource):
    """Phurinont: Mycelium-Emissionsprofile, gemeldet und geschätzt getrennt.

    **Nur zur internen Gegenprobe, nicht für den öffentlichen Datensatz.** Die
    Nutzungsbedingungen von Mycelium (mycelium.global/emissions-data-terms-of-use)
    untersagen, "a substantial part of the database" als "dataset, feed, or
    downloadable archive" weiterzugeben -- auch nicht-kommerziell -- und
    verlangen für systematisches Abrufen eine Lizenz. ``consolidate`` übernimmt
    diese Quelle deshalb nicht; ``INTERNAL_ONLY`` markiert sie.

    Nur Zeilen mit sicherer Zuordnung (``Match status == matched``) werden
    gelesen. Die 35 Zeilen, die das Team selbst zur Prüfung markiert hat,
    bleiben draußen -- darunter Moderna, zugeordnet zu einem Kosmetiksalon.
    """

    INTERNAL_ONLY = True

    name = "team_mycelium"
    endpoint = "data/external/team/mycelium_constituents.xlsx"
    description = "Phurinont: Mycelium-Emissionen je Firma und Jahr, Anteil Schätzung"

    def _fetch(self) -> pd.DataFrame:
        xl = pd.ExcelFile(TEAM / "mycelium_constituents.xlsx")
        cons = xl.parse("Constituents")
        years = xl.parse("Emissions by year")
        ok = cons[cons["Match status"] == "matched"][
            ["Symbol", "Profile URL", "Mycelium score", "Transparency score", "Match status"]
        ]
        df = years.merge(ok, on="Symbol", how="inner")
        df = df.rename(
            columns={
                "Symbol": "ticker",
                "Year": "year",
                "Total tCO2e": "total_t",
                "Reported tCO2e": "reported_t",
                "Estimated tCO2e": "estimated_t",
                "Estimated share": "estimated_share",
                "Profile URL": "profile_url",
                "Mycelium score": "mycelium_score",
                "Transparency score": "transparency_score",
            }
        )
        df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False)
        return df.drop(columns=["Security", "Mycelium slug"], errors="ignore")


@register
class TeamWbaSource(DataSource):
    """Janis: World Benchmarking Alliance, öffentliche Unternehmensprofile 2026.

    Übernommen werden nur die vier Bewertungen und die ACT-Note. Die
    Fußabdruck-Zeichenketten auf den Profilseiten ("59 million tCO2e") hat das
    Team bewusst nur als Kontext gespeichert -- sie bleiben auch hier draußen.
    """

    name = "team_wba"
    endpoint = "data/external/team/wba_snapshot.json"
    description = "Janis: WBA ACT, Social, Nature, Just Transition (CC BY 4.0)"

    def _fetch(self) -> pd.DataFrame:
        snap = json.loads((TEAM / "wba_snapshot.json").read_text(encoding="utf-8"))
        rows = []
        for c in snap["companies"]:
            a = c.get("assessment")
            if not a:
                continue
            for t in c["tickers"]:
                rows.append(
                    {
                        "ticker": t.replace(".", "-"),
                        "wba_name": c["wba"]["name"],
                        "match_method": c["match_method"],
                        "tpq": a.get("tpq"),
                        "ctt": a.get("ctt"),
                        "act_grade": a.get("act_grade"),
                        "social": a.get("social"),
                        "nature": a.get("nature"),
                        "just_transition": a.get("just_transition"),
                        "profile_url": a["source"]["url"],
                        "retrieved_at": a["source"]["retrieved_at"],
                    }
                )
        return pd.DataFrame(rows)
