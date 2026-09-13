"""Normalization registry. Map oriented peer-group observations to positive scores with floor EPS. Registered methods enter the Monte Carlo method space. A positive floor keeps geometric aggregation defined; it is a modeling choice."""
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
    """direction=-1 means lower is better, for example emissions intensity."""
    return s * direction


def _rescale(s: pd.Series) -> pd.Series:
    """Rescale to [EPS, 1]; use 0.5 for constant groups."""
    lo, hi = s.min(), s.max()
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-12:
        return pd.Series(0.5, index=s.index)
    return EPS + (1 - EPS) * (s - lo) / (hi - lo)


def _winsorize(s: pd.Series, pct: float) -> pd.Series:
    if pct <= 0 or len(s.dropna()) < 5:
        return s
    lo, hi = s.quantile(pct), s.quantile(1 - pct)
    return s.clip(lower=lo, upper=hi)


@register("rank")
def rank_norm(s: pd.Series, direction: int, winsor: float) -> pd.Series:
    """Percentile ranks reduce outlier magnitude effects but discard distances."""
    oriented = _orient(s, direction)
    r = oriented.rank(pct=True, na_option="keep")
    return EPS + (1 - EPS) * r


@register("winsor-z")
def winsor_z(s: pd.Series, direction: int, winsor: float) -> pd.Series:
    """Winsorize, standardize, clip z-scores to [-3, 3], and rescale."""
    oriented = _orient(_winsorize(s, winsor), direction)
    mu, sd = oriented.mean(), oriented.std(ddof=0)
    z = (oriented - mu) / sd if sd and sd > 1e-12 else oriented * 0.0
    return _rescale(z.clip(-3, 3))


@register("min-max")
def minmax(s: pd.Series, direction: int, winsor: float) -> pd.Series:
    """Rescale oriented, optionally winsorized observations using their extremes."""
    return _rescale(_orient(_winsorize(s, winsor), direction))


@register("median-mad")
def robust_z(s: pd.Series, direction: int, winsor: float) -> pd.Series:
    """Standardize using the median and scaled median absolute deviation, then clip and rescale."""
    oriented = _orient(s, direction)
    med = oriented.median()
    mad = (oriented - med).abs().median()
    z = (oriented - med) / (1.4826 * mad) if mad and mad > 1e-12 else oriented * 0.0
    return _rescale(z.clip(-3, 3))
