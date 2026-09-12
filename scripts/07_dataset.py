"""Schreibt den gesammelten Datensatz und die Daten fuer die Web-Oberflaeche."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUT, ROOT
from pipeline.consolidate import write_all


def main() -> None:
    stats = write_all()
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    # Die Web-App liest die Daten direkt aus ihrem public-Ordner.
    web_public = ROOT / "web" / "public" / "data"
    if web_public.parent.exists():
        web_public.mkdir(parents=True, exist_ok=True)
        for name in ("companies.json", "sources.json", "metrics.json"):
            shutil.copy2(OUT / name, web_public / name)
        print(f"-> Web-Daten aktualisiert: {web_public}")


if __name__ == "__main__":
    main()
