"""
Fusionspipeline, Erweiterung: drei neue Dimensionen.

Bisher war jede der sechs Kennzahlen ein Blick auf CO2. Damit war der
Titel "Nachhaltigkeit" nicht gedeckt, und die multiplikative Aggregation
konnte nur zwischen Varianten desselben Themas unterscheiden.

Neu:
  E2  Giftstofffreisetzung (EPA TRI) - Luft, Wasser, Boden, Krebserreger
  E3  Physischer Nenner fuer Stromerzeuger (EIA-923/860): t CO2 je MWh
      statt je Umsatzdollar. Behebt die gemessene Groessenverzerrung.
  S1  Arbeitsunfallrate (OSHA ITA): Faelle je 200 000 Arbeitsstunden
"""
import numpy as np
import pandas as pd
from pathlib import Path
from rapidfuzz import process, fuzz

from build_src import normalize, MANUAL_ALIASES

DATA = Path("data")
F = Path("fusion")
LATEST = 2023


def matcher():
    comp = pd.read_parquet("build/src_companies.parquet")
    comp["name_norm"] = comp.company_name.map(normalize)
    lookup = dict(zip(comp.name_norm, comp.company_id))
    choices = list(lookup)
    alias = {normalize(k): v for k, v in MANUAL_ALIASES.items()}
    n2id = dict(zip(comp.company_name, comp.company_id))

    cache = {}
    def match(raw, threshold=92):
        if not isinstance(raw, str) or not raw.strip():
            return None
        key = (raw, threshold)
        if key in cache:
            return cache[key]
        n = normalize(raw)
        out = None
        if n in alias and alias[n] in n2id:
            out = n2id[alias[n]]
        elif n in lookup:
            out = lookup[n]
        else:
            hit = process.extractOne(n, choices, scorer=fuzz.token_sort_ratio)
            if hit and hit[1] >= threshold:
                out = lookup[hit[0]]
        cache[key] = out
        return out
    return match


# ----------------------------------------------------------------------
def build_tri(match):
    """Giftstofffreisetzung je Firma, aus dem TRI-Nationaldatensatz."""
    df = pd.read_csv("/mnt/user-data/uploads/2023_us.csv", low_memory=False,
                     encoding="latin-1")
    df.columns = [c.split(". ", 1)[-1].strip() for c in df.columns]
    need = ["STANDARD PARENT CO NAME", "PARENT CO NAME", "CHEMICAL",
            "CARCINOGEN", "UNIT OF MEASURE", "TOTAL RELEASES",
            "5.1 - FUGITIVE AIR", "5.2 - STACK AIR", "5.3 - WATER"]
    df = df[[c for c in need if c in df.columns]].copy()

    # Dioxine werden in Gramm gemeldet, alles andere in Pfund
    lbs = df["UNIT OF MEASURE"].astype(str).str.contains("Pound", case=False, na=False)
    for c in ["TOTAL RELEASES", "5.1 - FUGITIVE AIR", "5.2 - STACK AIR", "5.3 - WATER"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        df.loc[~lbs, c] = df.loc[~lbs, c] / 453.592   # Gramm -> Pfund
    df["kg"] = df["TOTAL RELEASES"] * 0.453592
    df["kg_karzinogen"] = np.where(
        df["CARCINOGEN"].astype(str).str.upper().str.startswith("Y"), df["kg"], 0.0)
    df["kg_wasser"] = df["5.3 - WATER"] * 0.453592

    name = df["STANDARD PARENT CO NAME"].fillna(df["PARENT CO NAME"])
    df["company_id"] = [match(n) for n in name]
    df = df.dropna(subset=["company_id"])
    df["company_id"] = df.company_id.astype(int)

    g = df.groupby("company_id").agg(
        tri_kg=("kg", "sum"),
        tri_kg_karzinogen=("kg_karzinogen", "sum"),
        tri_kg_wasser=("kg_wasser", "sum"),
        tri_meldungen=("kg", "size"),
        tri_chemikalien=("CHEMICAL", "nunique")).reset_index()
    g["karzinogen_anteil"] = (g.tri_kg_karzinogen / g.tri_kg.replace(0, np.nan)).fillna(0)
    g.to_parquet(F / "src_tri.parquet", index=False)
    print(f"src_tri: {len(df):,} Meldezeilen -> {len(g)} S&P-Firmen, "
          f"{g.tri_kg.sum()/1e6:.1f} Tsd.\u00a0t freigesetzt, "
          f"median Karzinogenanteil {g.karzinogen_anteil.median():.3f}")
    return g


# ----------------------------------------------------------------------
def build_eia(match):
    """Nettostromerzeugung je Firma ueber ORIS-Codes und EIA-860-Eigentuemer."""
    gen = pd.read_excel(DATA / "eia" / "EIA923_Schedules_2_3_4_5_M_12_2023_Final_Revision.xlsx",
                        sheet_name="Page 1 Generation and Fuel Data", header=5)
    gen.columns = [str(c).replace("\n", " ").strip() for c in gen.columns]
    gcol = [c for c in gen.columns if c.startswith("Net Generation")][0]
    gen["mwh"] = pd.to_numeric(gen[gcol], errors="coerce").fillna(0.0)
    plant = gen.groupby("Plant Id", as_index=False).agg(
        mwh=("mwh", "sum"), operator=("Operator Name", "first"))
    plant = plant[plant.mwh > 0]

    # Eigentuemeranteile aus EIA-860 Schedule 4, sonst Betreiber
    own = pd.read_excel(DATA / "eia" / "4___Owner_Y2023.xlsx", header=1)
    own.columns = [str(c).replace("\n", " ").strip() for c in own.columns]
    pcol = [c for c in own.columns if "Plant Code" in c or c == "Plant Id"][0]
    ocol = [c for c in own.columns if "Owner Name" in c][0]
    scol = [c for c in own.columns if "Percent Owned" in c][0]
    own = own[[pcol, ocol, scol]].rename(columns={pcol: "Plant Id", ocol: "owner",
                                                  scol: "share"})
    own["share"] = pd.to_numeric(own.share, errors="coerce").fillna(1.0).clip(0, 1)

    j = plant.merge(own, on="Plant Id", how="left")
    j["owner"] = j.owner.fillna(j.operator)
    j["share"] = j.share.fillna(1.0)
    j["company_id"] = [match(n) for n in j.owner]
    j = j.dropna(subset=["company_id"])
    j["company_id"] = j.company_id.astype(int)
    j["mwh_attr"] = j.mwh * j.share

    g = j.groupby("company_id", as_index=False).agg(
        mwh=("mwh_attr", "sum"), kraftwerke=("Plant Id", "nunique"))
    g = g[g.mwh > 0]
    g.to_parquet(F / "src_eia_generation.parquet", index=False)
    print(f"src_eia_generation: {len(g)} S&P-Firmen, "
          f"{g.mwh.sum()/1e6:.0f} Mio.\u00a0MWh zugeordnet")
    return g


# ----------------------------------------------------------------------
def build_osha(match):
    """Unfallrate je 200 000 Arbeitsstunden, aggregiert auf Konzernebene."""
    path = next((DATA / "osha").glob("*.csv"))
    use = ["establishment_id", "company_name", "establishment_name",
           "annual_average_employees", "total_hours_worked", "incident_outcome"]
    df = pd.read_csv(path, usecols=use, low_memory=False, encoding="latin-1")

    # Eine Zeile je Fall -> Betriebsstaette entschaerfen: Stunden nur einmal zaehlen
    est = df.groupby("establishment_id").agg(
        faelle=("incident_outcome", "size"),
        stunden=("total_hours_worked", "max"),
        beschaeftigte=("annual_average_employees", "max"),
        firma=("company_name", "first"),
        betrieb=("establishment_name", "first")).reset_index()
    est["stunden"] = pd.to_numeric(est.stunden, errors="coerce")
    est = est[est.stunden > 1000]

    name = est.firma.fillna(est.betrieb)
    est["company_id"] = [match(n) for n in name]
    est = est.dropna(subset=["company_id"])
    est["company_id"] = est.company_id.astype(int)

    g = est.groupby("company_id", as_index=False).agg(
        faelle=("faelle", "sum"), stunden=("stunden", "sum"),
        betriebe=("establishment_id", "nunique"))
    g["unfallrate"] = g.faelle / g.stunden * 200_000
    # Poisson-Fehler auf die Fallzahl
    g["unfallrate_se"] = np.sqrt(g.faelle.clip(lower=1)) / g.stunden * 200_000
    g.to_parquet(F / "src_osha.parquet", index=False)
    print(f"src_osha: {len(est):,} Betriebsstaetten -> {len(g)} S&P-Firmen, "
          f"median Unfallrate {g.unfallrate.median():.2f} je 200k Stunden")
    return g


if __name__ == "__main__":
    m = matcher()
    build_tri(m)
    build_eia(m)
    build_osha(m)
