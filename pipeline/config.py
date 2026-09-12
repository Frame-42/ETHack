"""Zentrale Pfade und Konstanten der Pipeline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "out"
REPORT = ROOT / "report"
FIGURES = REPORT / "figures"

for _p in (RAW, OUT, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)

# Die SEC verlangt einen identifizierenden User-Agent, sonst 403.
USER_AGENT = "ETHack S&P500 Sustainability Research (noah.schittenhelm@pm.me)"

# Periodengrenze: bis einschliesslich dieses Geschaeftsjahres reicht der
# kommerzielle ESG-Snapshot (Kaggle/Yahoo-Stand 2023/24). Danach faellt er weg.
PERIOD_A_END = 2023
PERIOD_B_START = 2024

# Letztes Jahr, fuer das die EPA Anlagendaten veroeffentlicht hat.
EPA_LAST_PUBLISHED_YEAR = 2023


# ---------------------------------------------------------------------------
# Zugangsschluessel aus .env laden. Die Datei steht in .gitignore; eine
# Vorlage ohne Werte liegt als .env.example bei.
# ---------------------------------------------------------------------------
def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # Fallback ohne zusaetzliche Abhaengigkeit
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


def require_key(name: str, where: str) -> str:
    """Holt einen Schluessel oder erklaert verstaendlich, wo er herkommt."""
    import os

    val = os.environ.get(name, "")
    if not val:
        raise RuntimeError(
            f"{name} fehlt. Kostenlos anfordern unter {where}, dann in .env "
            f"eintragen (Vorlage: .env.example)."
        )
    return val
