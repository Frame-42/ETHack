"""Aggregations-Register -- die folgenreichste der drei Entscheidungen.

Additiv heisst volle Kompensierbarkeit: ein katastrophaler CO2-Wert laesst
sich durch gute Werte anderswo vollstaendig zurueckkaufen. Geometrisch heisst
begrenzte Kompensierbarkeit: ein sehr schlechter Wert zieht die Gesamtnote
nach unten und bleibt sichtbar.

Fuer eine Nachhaltigkeitsnote ist das der entscheidende Unterschied. Beide
Verfahren sind trotzdem registriert -- der Bericht zeigt an den Daten, wie
weit die Ranglisten auseinanderlaufen.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

AGGREGATORS: dict[str, Callable[[pd.DataFrame, np.ndarray], pd.Series]] = {}


def register(name: str):
    def deco(fn):
        AGGREGATORS[name] = fn
        return fn

    return deco


@register("geometrisch")
def geometric(X: pd.DataFrame, w: np.ndarray) -> pd.Series:
    """Gewichtetes geometrisches Mittel."""
    A = np.clip(X.to_numpy(dtype=float), 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_score = np.nansum(np.log(A) * w, axis=1)
        mask = np.sum(np.where(np.isnan(A), 0.0, w), axis=1)
    mask = np.where(mask <= 0, np.nan, mask)
    return pd.Series(np.exp(log_score / mask), index=X.index)


@register("additiv")
def arithmetic(X: pd.DataFrame, w: np.ndarray) -> pd.Series:
    """Gewichtete Summe -- der uebliche Weg, und der kompensierbare."""
    A = X.to_numpy(dtype=float)
    num = np.nansum(A * w, axis=1)
    den = np.sum(np.where(np.isnan(A), 0.0, w), axis=1)
    den = np.where(den <= 0, np.nan, den)
    return pd.Series(num / den, index=X.index)
