"""Normalisierungs-Register.

Jede Funktion bekommt eine Serie von Rohwerten *einer Branchengruppe* und die
Richtung der Kennzahl und gibt eine Guete in ``[0, 1]`` zurueck: 1 = bester
Wert der Gruppe.

Alle Verfahren geben strikt positive Werte zurueck (Untergrenze ``EPS``), weil
die geometrische Aggregation sonst auf Null kollabiert -- genau die Huerde, die
das OECD-Handbuch bei multiplikativer Zusammenfassung nennt.

Neues Verfahren registrieren heisst: Funktion schreiben, Dekorator dran. Die
Monte-Carlo-Schleife nimmt es automatisch in den Kombinationsraum auf.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

EPS = 0.01

NORMALIZERS: dict[str, Callable[[pd.Series, int, float], pd.Series]] = {}


def register(name: str):
    def deco(fn):
        NORMALIZERS[name] = fn
        return fn

    return deco


def _orient(s: pd.Series, direction: int) -> pd.Series:
    """direction=-1 bedeutet: kleiner ist besser (z. B. CO2-Intensitaet)."""
    return s * direction


def _rescale(s: pd.Series) -> pd.Series:
    """Auf [EPS, 1] bringen; konstante Gruppen bekommen 0.5."""
    lo, hi = s.min(), s.max()
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-12:
        return pd.Series(0.5, index=s.index)
    return EPS + (1 - EPS) * (s - lo) / (hi - lo)


def _winsorize(s: pd.Series, pct: float) -> pd.Series:
    if pct <= 0 or len(s.dropna()) < 5:
        return s
    lo, hi = s.quantile(pct), s.quantile(1 - pct)
    return s.clip(lower=lo, upper=hi)


@register("rang")
def rank_norm(s: pd.Series, direction: int, winsor: float) -> pd.Series:
    """Perzentilrang. Robust gegen Ausreisser, verliert aber die Abstaende."""
    oriented = _orient(s, direction)
    r = oriented.rank(pct=True, na_option="keep")
    return EPS + (1 - EPS) * r


@register("z-getrimmt")
def winsor_z(s: pd.Series, direction: int, winsor: float) -> pd.Series:
    """Gestutzter Z-Wert -- die Empfehlung fuer Daten mit Extremwerten."""
    oriented = _orient(_winsorize(s, winsor), direction)
    mu, sd = oriented.mean(), oriented.std(ddof=0)
    z = (oriented - mu) / sd if sd and sd > 1e-12 else oriented * 0.0
    return _rescale(z.clip(-3, 3))


@register("min-max")
def minmax(s: pd.Series, direction: int, winsor: float) -> pd.Series:
    """Auf 0 bis 1 skalieren. Der Extremwert wird zum Massstab fuer alle."""
    return _rescale(_orient(_winsorize(s, winsor), direction))


@register("median-mad")
def robust_z(s: pd.Series, direction: int, winsor: float) -> pd.Series:
    """Median und mittlere absolute Abweichung statt Mittelwert und Streuung."""
    oriented = _orient(s, direction)
    med = oriented.median()
    mad = (oriented - med).abs().median()
    z = (oriented - med) / (1.4826 * mad) if mad and mad > 1e-12 else oriented * 0.0
    return _rescale(z.clip(-3, 3))
