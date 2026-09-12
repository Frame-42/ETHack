"""Verdichtet eGRID, TRI, OSHA und ECHO auf Firmenebene.

Diese Aggregate wurden zuerst interaktiv gerechnet. Als die Team-Gegenprobe
Fehler in der Tochtertabelle aufdeckte, liessen sie sich nicht sauber neu
erzeugen -- deshalb stehen sie jetzt hier. Alle vier Zuordnungen nutzen
denselben Weg: exakter Name, Tochtertabelle, Präfix der Tochtertabelle.
Kein unscharfer Abgleich, weil Betriebs- und Filialnamen sonst beliebige
Treffer liefern.

Schreibt die CSV-Dateien, die ``pipeline/consolidate.py`` liest.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from pipeline.config import OUT, RAW
from pipeline.resolve import OVERRIDES, master_prefix, normalize

MASTER = pd.read_parquet(RAW / "sp500_master.parquet")
LOOKUP = {normalize(r.company): r.ticker for r in MASTER.itertuples()}


def to_ticker(name) -> str | None:
    k = normalize(name)
    if not k:
        return None
    if k in LOOKUP:
        return LOOKUP[k]
    if k in OVERRIDES:
        return OVERRIDES[k]
    hit = next((t for p, t in OVERRIDES.items() if k.startswith(p)), None)
    return hit or master_prefix(k, LOOKUP)


def with_meta(df: pd.DataFrame) -> pd.DataFrame:
    return df.merge(MASTER[["ticker", "company", "gics_sector"]], on="ticker", how="left")


def egrid() -> None:
    eg = pd.read_parquet(RAW / "egrid_plant.parquet")
    eg = eg[eg["co2_t"].notna() & (eg["net_generation_mwh"] > 0)].copy()
    eg["ticker"] = eg["operator_name"].map(to_ticker).fillna(eg["utility_name"].map(to_ticker))
    agg = eg.dropna(subset=["ticker"]).groupby("ticker", as_index=False).agg(
        kraftwerke=("plant_name", "nunique"), co2_t=("co2_t", "sum"),
        mwh=("net_generation_mwh", "sum"),
    )
    agg["t_co2_pro_mwh"] = agg["co2_t"] / agg["mwh"]
    with_meta(agg).to_csv(OUT / "egrid_je_firma.csv", index=False)
    print(f"eGRID: {len(agg)} Firmen")


def tri() -> None:
    t = pd.read_parquet(RAW / "epa_tri.parquet")
    t["ticker"] = t["standard_parent_co_name"].map(to_ticker)
    hit = t.dropna(subset=["ticker"]).copy()
    rel = "total_releases" if "total_releases" in hit.columns else "on-site_release_total"
    hit[rel] = pd.to_numeric(hit[rel], errors="coerce")
    hit["krebs"] = hit["carcinogen"].astype(str).str.upper().str.startswith("Y")
    hit["krebs_lbs"] = hit[rel].where(hit["krebs"], 0.0)
    agg = hit.groupby("ticker", as_index=False).agg(
        anlagen=("frs_id", "nunique"), freisetzung_lbs=(rel, "sum"), krebs_lbs=("krebs_lbs", "sum"),
    )
    with_meta(agg).to_csv(OUT / "tri_je_firma.csv", index=False)
    print(f"TRI: {len(agg)} Firmen")


def osha() -> None:
    o = pd.read_parquet(RAW / "osha_ita.parquet")
    o["ticker"] = o["company_name"].map(to_ticker)
    hit = o.dropna(subset=["ticker"])
    agg = hit.groupby("ticker", as_index=False).agg(
        betriebe=("establishment_name", "nunique"), stunden=("total_hours_worked", "sum"),
        dafw=("total_dafw_cases", "sum"), djtr=("total_djtr_cases", "sum"),
        tote=("total_deaths", "sum"),
    )
    for c in ("stunden", "dafw", "djtr", "tote"):
        agg[c] = pd.to_numeric(agg[c], errors="coerce")
    agg["dart_rate"] = (agg["dafw"] + agg["djtr"]) * 200000 / agg["stunden"].replace(0, np.nan)
    with_meta(agg).to_csv(OUT / "osha_je_firma.csv", index=False)
    print(f"OSHA: {len(agg)} Firmen")


def echo() -> None:
    e = pd.read_parquet(RAW / "epa_echo.parquet")
    fac = pd.read_parquet(RAW / "epa_facility.parquet")
    fi = fac[["frs_id", "parent_company"]].dropna().drop_duplicates()
    fi["frs_id"] = fi["frs_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    e["rid"] = e["registry_id"].astype("Int64").astype(str)
    j = e.merge(fi, left_on="rid", right_on="frs_id", how="inner")
    # Das Konzernfeld der EPA ist Freitext mit Quoten; der erste genannte
    # Eigentuemer entscheidet.
    first = j["parent_company"].astype(str).str.split(";").str[0].str.replace(
        r"\([^)]*\)", "", regex=True
    )
    j["ticker"] = first.map(to_ticker)
    hit = j.dropna(subset=["ticker"]).copy()
    hist = hit["fac_3yr_compliance_history"].fillna("").astype(str)
    hit["vq"] = hist.str.count(r"[A-Z]")
    hit["sv"] = hit["fac_compliance_status"].astype(str).str.contains("Significant", case=False).astype(int)
    agg = hit.groupby("ticker", as_index=False).agg(
        anlagen=("rid", "nunique"), strafen_usd=("fac_total_penalties", "sum"),
        inspektionen=("fac_inspection_count", "sum"), verstossquartale=("vq", "sum"),
        schwere_verstoesse=("sv", "sum"),
    )
    agg["verstossquartale_je_anlage"] = agg["verstossquartale"] / agg["anlagen"]
    with_meta(agg).to_csv(OUT / "echo_je_firma.csv", index=False)
    print(f"ECHO: {len(agg)} Firmen")


if __name__ == "__main__":
    egrid()
    tri()
    osha()
    echo()
