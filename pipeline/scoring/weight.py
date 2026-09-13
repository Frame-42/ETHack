"""Weighting registry. Input rows are companies and columns are normalized metrics; output weights sum to one. Equal weights provide a transparent reference, while entropy and CRITIC vary statistical emphasis in the sensitivity analysis."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

WEIGHTERS: dict[str, Callable[[pd.DataFrame], np.ndarray]] = {}


def register(name: str):
    def deco(fn):
        WEIGHTERS[name] = fn
        return fn

    return deco


@register("equal")
def equal(X: pd.DataFrame) -> np.ndarray:
    """Assign equal weight to each metric."""
    k = X.shape[1]
    return np.full(k, 1.0 / k)


@register("entropy")
def entropy(X: pd.DataFrame) -> np.ndarray:
    """Shannon entropy weights emphasize dispersion. Statistical variation is not substantive materiality, so use this as a sensitivity alternative."""
    A = X.to_numpy(dtype=float)
    A = np.where(np.isfinite(A), A, np.nan)
    col_sum = np.nansum(A, axis=0)
    col_sum[col_sum <= 0] = 1.0
    P = A / col_sum
    P = np.where((P > 0) & np.isfinite(P), P, 1e-12)
    n = max(A.shape[0], 2)
    e = -(P * np.log(P)).sum(axis=0) / np.log(n)
    d = 1.0 - e
    if d.sum() <= 1e-12:
        return equal(X)
    return d / d.sum()


@register("critic")
def critic(X: pd.DataFrame) -> np.ndarray:
    """CRITIC weights combine dispersion with lack of correlation to other metrics. Distinct statistical information need not imply greater sustainability importance."""
    A = X.to_numpy(dtype=float)
    sd = np.nanstd(A, axis=0, ddof=0)
    if X.shape[1] < 2:
        return equal(X)
    corr = pd.DataFrame(A).corr().to_numpy()
    corr = np.where(np.isfinite(corr), corr, 0.0)
    conflict = (1.0 - corr).sum(axis=0)
    c = sd * conflict
    if not np.isfinite(c).all() or c.sum() <= 1e-12:
        return equal(X)
    return c / c.sum()
