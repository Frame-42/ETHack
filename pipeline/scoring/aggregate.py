"""Aggregation registry. Arithmetic means allow more compensation across dimensions; geometric means penalize low positive scores more strongly but do not prohibit compensation. Both are included in the climate sensitivity analysis."""
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


@register("geometric")
def geometric(X: pd.DataFrame, w: np.ndarray) -> pd.Series:
    """Weighted geometric mean over observed metrics."""
    A = np.clip(X.to_numpy(dtype=float), 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_score = np.nansum(np.log(A) * w, axis=1)
        mask = np.sum(np.where(np.isnan(A), 0.0, w), axis=1)
    mask = np.where(mask <= 0, np.nan, mask)
    return pd.Series(np.exp(log_score / mask), index=X.index)


@register("arithmetic")
def arithmetic(X: pd.DataFrame, w: np.ndarray) -> pd.Series:
    """Weighted arithmetic mean over observed metrics."""
    A = X.to_numpy(dtype=float)
    num = np.nansum(A * w, axis=1)
    den = np.sum(np.where(np.isnan(A), 0.0, w), axis=1)
    den = np.where(den <= 0, np.nan, den)
    return pd.Series(num / den, index=X.index)
