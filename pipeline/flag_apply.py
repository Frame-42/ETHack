"""Hängt Prüfergebnisse an die Werte des Datensatzes.

Eine Flag ändert keinen Wert. Sie ergänzt drei Spalten, damit jede spätere
Nutzung selbst entscheiden kann, was sie damit tut:

``quality_status``  ok | fehler | pruefen
``quality_rule``    Regelkennung, z. B. F02_null_statt_fehlend
``quality_note``    Begründung in einem Satz, bei KI-Prüfung mit deren Urteil

Rangfolge der Entscheidung: menschliche Entscheidung > automatisch
übernommenes KI-Urteil > Regel. Ein Wert mit Status ``fehler`` bleibt im
Langformat erhalten (nachvollziehbar), wird aber aus der verdichteten
Firmenansicht genommen.
"""
from __future__ import annotations

import pandas as pd

from .config import OUT


def load_flags() -> pd.DataFrame:
    p = OUT / "flags_gepruft.csv"
    if not p.exists():
        p = OUT / "flags.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def status_of(row: pd.Series) -> str:
    """Endgültiger Status einer Flag."""
    decision = str(row.get("entscheidung", "") or "").strip().lower()
    if decision in ("fehler", "unterdruecken", "korrigieren"):
        return "fehler"
    if decision in ("ok", "behalten", "plausibel"):
        return "ok"
    # Automatisch entschiedene Fälle folgen dem Vorschlag des Modells: Das ist
    # der Sinn der Weiterleitung. Alles Strittige ist vorher zu einem Menschen
    # gegangen, und jede Entscheidung lässt sich über entscheidungen.csv
    # zurücknehmen.
    if row.get("route") == "automatisch":
        aktion = str(row.get("ai_action", "") or "").strip().lower()
        if aktion in ("unterdruecken", "korrigieren"):
            return "fehler"
        if aktion == "behalten":
            return "ok"
        return "pruefen"
    return str(row.get("severity", "pruefen"))


def apply(long: pd.DataFrame) -> pd.DataFrame:
    flags = load_flags()
    long = long.copy()
    long["quality_status"] = "ok"
    long["quality_rule"] = ""
    long["quality_note"] = ""
    if flags.empty:
        return long
    flags["status"] = flags.apply(status_of, axis=1)
    rank = {"fehler": 2, "pruefen": 1, "ok": 0}
    for f in flags.sort_values("status", key=lambda s: s.map(rank)).itertuples(index=False):
        if f.metric == "*":
            mask = long.ticker == f.ticker
        else:
            mask = (long.ticker == f.ticker) & (long.metric == f.metric)
            if pd.notna(f.year):
                mask &= long.year == int(f.year)
        note = f.message
        if isinstance(getattr(f, "ai_explanation", None), str):
            note = f"{f.message} KI: {f.ai_verdict} ({f.ai_confidence:.2f}) -- {f.ai_explanation}"
        long.loc[mask, "quality_status"] = f.status
        long.loc[mask, "quality_rule"] = f.rule
        long.loc[mask, "quality_note"] = note
    return long
