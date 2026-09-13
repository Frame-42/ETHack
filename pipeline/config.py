"""Shared repository paths, configured study periods, and environment loading."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "out"

for _p in (RAW, OUT):
    _p.mkdir(parents=True, exist_ok=True)

# SEC access requires an identifying User-Agent.


# Fixed study-period boundary. The separate commercial snapshot is historical and is not a time-matched 2023 observation.
PERIOD_A_END = 2023
PERIOD_B_START = 2024

# Final GHGRP year configured for this study, not a live availability claim.
EPA_LAST_PUBLISHED_YEAR = 2023


# Load access keys from ignored .env;
# .env.example contains placeholders.
def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # Fallback without the optional dependency.
        env = ROOT / ".env"
        if not env.exists():
            return
        import os

        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())
        return
    load_dotenv(ROOT / ".env")


_load_env()
USER_AGENT = os.environ.get("SEC_USER_AGENT", "ETHack sustainability research")


def require_key(name: str, where: str) -> str:
    """Read a required API key and explain where to obtain it."""
    import os

    val = os.environ.get(name, "")
    if not val:
        raise RuntimeError(
            f"{name} is missing. Register at {where}, then add the key to .env "
            f"(template: .env.example)."
        )
    return val
