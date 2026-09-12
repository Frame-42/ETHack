"""Schreibt den gesammelten Datensatz und die Daten fuer die Web-Oberflaeche."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUT, ROOT
from pipeline.consolidate import write_all


def pruefe_export() -> None:
    """Harte Grenzen beim Export. Der Lauf bricht ab, statt Fehler auszuliefern.

    Phase 0 aus dem Verbesserungsbericht: Jede reparierte Ursache bekommt eine
    Grenze, damit sie nicht unbemerkt zurueckkommt.
    """
    import pandas as pd

    long = pd.read_parquet(OUT / "dataset_long.parquet")
    w = long.pivot_table(index=["ticker", "year"], columns="metric", values="value",
                         aggfunc="first")

    def grenze(metric: str, *, hoechstens=None, mindestens=None, text="") -> None:
        if metric not in w:
            return
        v = w[metric].dropna()
        if hoechstens is not None and (v > hoechstens).any():
            raise AssertionError(f"{metric}: {int((v > hoechstens).sum())} Werte ueber "
                                 f"{hoechstens} -- {text}")
        if mindestens is not None and (v < mindestens).any():
            raise AssertionError(f"{metric}: {int((v < mindestens).sum())} Werte unter "
                                 f"{mindestens} -- {text}")

    grenze("echo_nc_quarters_per_site", hoechstens=12, mindestens=0,
           text="drei Jahre haben zwoelf Quartale")
    grenze("t_co2_pro_mwh", hoechstens=1.3, text="Braunkohle liegt bei rund 1,15 t/MWh")
    grenze("absolute_cagr", hoechstens=1.0, mindestens=-1.0, text="Trend als Anteil je Jahr")
    grenze("intensity_cagr", hoechstens=1.0, mindestens=-1.0, text="Trend als Anteil je Jahr")
    for metric in ("scope1_t", "campd_co2_t"):
        if metric in w and (w[metric].dropna() <= 0).any():
            raise AssertionError(f"{metric}: exakte Null im Bestand -- fehlend statt 0 fuehren")
    doppelt = long.duplicated(["ticker", "year", "metric"]).sum()
    if doppelt:
        raise AssertionError(f"{doppelt} doppelte Zeilen (Ticker, Jahr, Kennzahl)")
    master = pd.read_parquet(ROOT / "data" / "raw" / "sp500_master.parquet")
    zweitlisting = set(master[master.duplicated("cik", keep=False)]["ticker"]) & set(long["ticker"])
    if len(zweitlisting) > master["cik"].duplicated().sum():
        raise AssertionError(f"Aktiengattungen derselben CIK doppelt im Bestand: {zweitlisting}")
    print("-> Export-Grenzen eingehalten")


def main() -> None:
    stats = write_all()
    pruefe_export()
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    # Die Web-App liest die Daten direkt aus ihrem public-Ordner.
    web_public = ROOT / "web" / "public" / "data"
    if web_public.parent.exists():
        web_public.mkdir(parents=True, exist_ok=True)
        for name in ("companies.json", "sources.json", "metrics.json"):
            shutil.copy2(OUT / name, web_public / name)
        # Alles, was der Download-Tab anbietet, an einen Ort.
        downloads = web_public.parent / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        for name in ("dataset_long.csv", "dataset_long.parquet", "companies.json",
                     "sources.json", "metrics.json"):
            shutil.copy2(OUT / name, downloads / name)
        katalog = ROOT / "report" / "datenkatalog.pdf"
        if katalog.exists():
            shutil.copy2(katalog, downloads / "datenkatalog.pdf")
            shutil.copy2(katalog, web_public.parent / "datenkatalog.pdf")
        print(f"-> Downloads aktualisiert: {downloads}")
        print(f"-> Web-Daten aktualisiert: {web_public}")


if __name__ == "__main__":
    main()
