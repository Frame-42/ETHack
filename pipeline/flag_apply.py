"""Attach quality_status, quality_rule, and quality_note without changing values. Human decisions take precedence. Model advice may flag a value for review; only a human decision or a hard rule classifies it as an error."""
from __future__ import annotations

import pandas as pd

from .config import OUT


def load_flags() -> pd.DataFrame:
    p = OUT / "reviewed_flags.csv"
    if not p.exists():
        p = OUT / "flags.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def status_of(row: pd.Series) -> str:
    """Resolve the final quality status of one flag."""
    decision = str(row.get("decision", "") or "").strip().lower()
    if decision in ("error", "suppress", "correct"):
        return "error"
    if decision in ("ok", "keep", "plausible"):
        return "ok"
    # Human decisions can override model advice.
    # Automatic model recommendations can clear a
    # plausible observation or request review, but
    # cannot remove a reported value.
    if row.get("route") == "automatic":
        action = str(row.get("ai_action", "") or "").strip().lower()
        if action == "keep" and row.get("ai_verdict") == "plausible":
            return "ok"
        return "review"
    return str(row.get("severity", "review"))


def apply(long: pd.DataFrame) -> pd.DataFrame:
    flags = load_flags()
    long = long.copy()
    long["quality_status"] = "ok"
    long["quality_rule"] = ""
    long["quality_note"] = ""
    if flags.empty:
        return long
    flags["status"] = flags.apply(status_of, axis=1)
    rank = {"error": 2, "review": 1, "ok": 0}
    for f in flags.sort_values("status", key=lambda s: s.map(rank)).itertuples(index=False):
        if f.metric == "*":
            mask = long.ticker == f.ticker
        else:
            mask = (long.ticker == f.ticker) & (long.metric == f.metric)
            if pd.notna(f.year):
                mask &= long.year == int(f.year)
        note = f.message
        if isinstance(getattr(f, "ai_explanation", None), str):
            note = f"{f.message} AI: {f.ai_verdict} ({f.ai_confidence:.2f}) -- {f.ai_explanation}"
        long.loc[mask, "quality_status"] = f.status
        long.loc[mask, "quality_rule"] = f.rule
        long.loc[mask, "quality_note"] = note
    return long
