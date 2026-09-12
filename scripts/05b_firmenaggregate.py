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
from pipeline.resolve import OVERRIDES, master_prefix, normalize, override_prefix

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
    return override_prefix(k) or master_prefix(k, LOOKUP)


def with_meta(df: pd.DataFrame) -> pd.DataFrame:
    return df.merge(MASTER[["ticker", "company", "gics_sector"]], on="ticker", how="left")


# Die Stromrate beschreibt ein Geschaeftsmodell, kein Unternehmen: Wer ein
# eigenes Blockheizkraftwerk betreibt, bekommt sonst eine "Kraftwerksnote".
# Laut Quellen-Caveat ist die Kennzahl nur fuer Stromerzeuger aussagekraeftig.
VERSORGER_BRANCHEN = ("Utilities",)
# Die Branchenkennung allein reicht nicht: Berkshire Hathaway Energy betreibt
# 113 Kraftwerke mit 83 TWh, GICS fuehrt den Konzern als Finanzwert. Wer eine
# Flotte betreibt, ist Stromerzeuger -- unabhaengig von der Kennung. Ein
# einzelnes Werk mit viel Strom ist dagegen eher ein Zuordnungsfehler.
FLOTTE_TWH, FLOTTE_KRAFTWERKE = 1.0, 3
# Physikalische Obergrenze: Braunkohle liegt bei rund 1,15 t CO2 je MWh.
MAX_T_PRO_MWH = 1.3


def egrid() -> None:
    eg = pd.read_parquet(RAW / "egrid_plant.parquet")
    eg = eg[eg["co2_t"].notna() & (eg["net_generation_mwh"] > 0)].copy()
    eg["ticker"] = eg["operator_name"].map(to_ticker).fillna(eg["utility_name"].map(to_ticker))
    agg = eg.dropna(subset=["ticker"]).groupby("ticker", as_index=False).agg(
        kraftwerke=("plant_name", "nunique"), co2_t=("co2_t", "sum"),
        mwh=("net_generation_mwh", "sum"),
    )
    agg["t_co2_pro_mwh"] = agg["co2_t"] / agg["mwh"]
    voll = with_meta(agg)
    flotte = (voll["mwh"] >= FLOTTE_TWH * 1e6) & (voll["kraftwerke"] >= FLOTTE_KRAFTWERKE)
    ist_versorger = voll["gics_sector"].isin(VERSORGER_BRANCHEN) | flotte
    # Nicht-Versorger behalten Kraftwerkszahl und Menge, aber keine Rate.
    voll.loc[~ist_versorger, "t_co2_pro_mwh"] = np.nan
    unmoeglich = voll["t_co2_pro_mwh"] > MAX_T_PRO_MWH
    if unmoeglich.any():
        print(f"eGRID: {int(unmoeglich.sum())} Raten ueber {MAX_T_PRO_MWH} t/MWh verworfen "
              f"({', '.join(voll.loc[unmoeglich, 'ticker'])})")
        voll.loc[unmoeglich, "t_co2_pro_mwh"] = np.nan
    voll.to_csv(OUT / "egrid_je_firma.csv", index=False)
    print(f"eGRID: {len(voll)} Firmen, davon {int(ist_versorger.sum())} mit Rate")


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


# OSHA prueft die Meldungen nicht ("OSHA also does not validate the counts of
# workers, hours, or injury and illness counts", ITA Data Users Guide). Eine
# Unfallrate ist Faelle je Stunden -- ein falscher Nenner erzeugt jede
# beliebige Rate. Vollzeit sind rund 2 000 Stunden im Jahr; ausserhalb dieses
# Bandes ist die Meldung als Nenner unbrauchbar.
STUNDEN_MIN, STUNDEN_MAX = 200, 4000


def osha() -> None:
    o = pd.read_parquet(RAW / "osha_ita.parquet")
    o["ticker"] = o["company_name"].map(to_ticker)
    hit = o.dropna(subset=["ticker"]).copy()
    stunden = pd.to_numeric(hit["total_hours_worked"], errors="coerce")
    koepfe = pd.to_numeric(hit["annual_average_employees"], errors="coerce")
    je_kopf = stunden / koepfe.replace(0, np.nan)
    brauchbar = je_kopf.between(STUNDEN_MIN, STUNDEN_MAX)
    verworfen = int((~brauchbar).sum())
    hit = hit[brauchbar]
    print(f"OSHA: {verworfen} Meldungen mit unplausiblem Stundennenner verworfen")
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
    # Dieselbe Anlage kann ueber mehrere Schreibweisen des Konzernnamens
    # mehrfach im Join landen. Tesla hatte so 24 Verstossquartale auf einer
    # Anlage -- moeglich sind in drei Jahren hoechstens 12.
    vorher = len(hit)
    hit = hit.drop_duplicates(subset=["rid", "ticker"])
    if vorher != len(hit):
        print(f"ECHO: {vorher - len(hit)} doppelte Anlagenzeilen aus dem Join entfernt")
    # Die Konformitaetshistorie hat genau ein Zeichen je Quartal, drei Jahre
    # lang: "_" beanstandungsfrei, "V" Verstoss, "S" schwerer Verstoss,
    # "U" ungeklaert, Leerzeichen keine Daten. Gezaehlt gehoeren nur V und S --
    # vorher wurde jeder Grossbuchstabe gezaehlt, also auch "U".
    hist = hit["fac_3yr_compliance_history"].fillna("").astype(str).str.slice(0, 12)
    hit["vq"] = hist.str.count(r"[VS]").clip(0, 12)
    hit["sv"] = hit["fac_compliance_status"].astype(str).str.contains("Significant", case=False).astype(int)
    agg = hit.groupby("ticker", as_index=False).agg(
        anlagen=("rid", "nunique"), strafen_usd=("fac_total_penalties", "sum"),
        inspektionen=("fac_inspection_count", "sum"), verstossquartale=("vq", "sum"),
        schwere_verstoesse=("sv", "sum"),
    )
    agg["verstossquartale_je_anlage"] = agg["verstossquartale"] / agg["anlagen"]
    assert agg["verstossquartale_je_anlage"].max() <= 12, "mehr als 12 Quartale je Anlage"
    with_meta(agg).to_csv(OUT / "echo_je_firma.csv", index=False)
    print(f"ECHO: {len(agg)} Firmen")


if __name__ == "__main__":
    egrid()
    tri()
    osha()
    echo()
