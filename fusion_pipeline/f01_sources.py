"""
Fusionspipeline, Stufe 1: Quellen.

Behebt gegenueber der Vorversion:
  K1  Alle sechs Direktemittenten-Blaetter statt nur einem.
      Lieferanten und CO2-Injektion bleiben ausdruecklich draussen.
  K2  Zuordnungsunsicherheit wird gemessen statt gesetzt:
      vier Matching-Schwellen (85/90/92/95) als eigene Datenvariante.
  K3  Zurechnungsregel als Dimension: Equity-Share und operative Kontrolle.
  K4  Messqualitaet je Firma aus dem EPA-Feld Unit Reporting Method (CEMS).
"""
import re
import numpy as np
import pandas as pd
import openpyxl
from pathlib import Path
from rapidfuzz import process, fuzz

from build_src import normalize, MANUAL_ALIASES

DATA = Path("data")
F = Path("fusion"); F.mkdir(exist_ok=True)
YEARS = list(range(2011, 2024))
LATEST = 2023
THRESHOLDS = [85, 90, 92, 95]

WB = DATA / "epa_zip" / "ghgp_data_by_year_2023.xlsx"

# Blaetter mit DIREKTEN Emissionen. Suppliers (verkaufter Kohlenstoff) und
# CO2 Injection / Geologic Sequestration sind bewusst NICHT dabei:
# Lieferantenmengen sind die Scope-1-Emissionen der Kunden und wuerden
# dieselbe Tonne ein zweites Mal zaehlen (GHG-Protokoll, Doppelzaehlungsverbot).
DIRECT_SHEETS = {
    "Direct Point Emitters": "direct",
    "Onshore Oil & Gas Prod.": "onshore_og",
    "Gathering & Boosting": "gathering",
    "Transmission Pipelines": "pipelines",
    "LDC - Direct Emissions": "ldc",
    "SF6 from Elec. Equip.": "sf6",
}
EXCLUDED_SHEETS = ["Suppliers", "CO2 Injection", "Geologic Sequestration of CO2"]


# ----------------------------------------------------------------------
def _read_sheet(wb, sheet):
    ws = wb[sheet]
    rows = ws.iter_rows(min_row=4, values_only=True)
    header = list(next(rows))
    recs = [r for r in rows if r and r[0] is not None]
    return pd.DataFrame(recs, columns=header)


def build_facilities():
    wb = openpyxl.load_workbook(WB, read_only=True, data_only=True)
    frames, audit = [], []

    for sheet, tag in DIRECT_SHEETS.items():
        df = _read_sheet(wb, sheet)
        ycols = {}
        for c in df.columns:
            m = re.match(r"^(\d{4})\s", str(c))
            if m and int(m.group(1)) in YEARS and "emission" in str(c).lower():
                ycols[c] = int(m.group(1))
        if not ycols:
            continue
        idv = [c for c in ["Facility Id", "Facility Name", "State",
                           "Primary NAICS Code"] if c in df.columns]
        long = df[idv + list(ycols)].melt(id_vars=idv, value_vars=list(ycols),
                                          var_name="ycol", value_name="co2e_tonnes")
        long["reporting_year"] = long["ycol"].map(ycols).astype(int)
        long = long.drop(columns="ycol").rename(columns={
            "Facility Id": "facility_id", "Facility Name": "facility_name",
            "State": "state", "Primary NAICS Code": "naics_code"})
        long["co2e_tonnes"] = pd.to_numeric(long.co2e_tonnes, errors="coerce")
        long = long.dropna(subset=["co2e_tonnes", "facility_id"])
        long = long[long.co2e_tonnes > 0]
        long["facility_id"] = pd.to_numeric(long.facility_id, errors="coerce")
        long = long.dropna(subset=["facility_id"])
        long["facility_id"] = long.facility_id.astype("int64")
        long["source_sheet"] = tag
        frames.append(long)
        t23 = long[long.reporting_year == LATEST].co2e_tonnes.sum()
        audit.append({"blatt": sheet, "typ": "direkt (E)", "mt_2023": t23 / 1e6,
                      "anlagen": long[long.reporting_year == LATEST].facility_id.nunique()})

    # Ausgeschlossene Blaetter nur zur Dokumentation der Groessenordnung
    for sheet in EXCLUDED_SHEETS:
        df = _read_sheet(wb, sheet)
        # Fuer Lieferanten ist 2023 im Arbeitsblatt unvollstaendig (nur eine
        # Kategorie hat eine 2023-Spalte); die Groessenordnung zeigt 2022.
        ref = 2022 if sheet == "Suppliers" else LATEST
        cols = [c for c in df.columns if str(ref) in str(c)]
        tot = float(pd.to_numeric(
            df[cols].apply(pd.to_numeric, errors="coerce").sum(axis=1), errors="coerce"
        ).sum()) if cols else 0.0
        typ = "Lieferant (S)" if sheet == "Suppliers" else "Injektion (I)"
        audit.append({"blatt": f"{sheet} ({ref})", "typ": typ, "mt_2023": tot / 1e6,
                      "anlagen": len(df)})

    fac = pd.concat(frames, ignore_index=True)
    # Eine Anlage kann in mehreren Blaettern stehen; Summe je Anlage-Jahr
    fac = (fac.groupby(["facility_id", "reporting_year"], as_index=False)
              .agg(co2e_tonnes=("co2e_tonnes", "sum"),
                   facility_name=("facility_name", "first"),
                   state=("state", "first"),
                   naics_code=("naics_code", "first"),
                   source_sheet=("source_sheet", "first")))
    fac.to_parquet(F / "src_epa_facility.parquet", index=False)

    ad = pd.DataFrame(audit)
    ad.to_parquet(F / "audit_esi.parquet", index=False)
    d = ad[ad.typ == "direkt (E)"].mt_2023.sum()
    s = ad[ad.typ == "Lieferant (S)"].mt_2023.sum()
    i = ad[ad.typ == "Injektion (I)"].mt_2023.sum()
    print(f"src_epa_facility: {len(fac):,} Anlage-Jahr-Zeilen, "
          f"{fac.facility_id.nunique():,} Anlagen")
    print(f"  2023 direkt (E):    {d:8.1f} Mt   <- verwendet")
    print(f"  2023 Lieferant (S): {s:8.1f} Mt   <- ausgeschlossen (Doppelzaehlung)")
    print(f"  2023 Injektion (I): {i:8.1f} Mt   <- ausgeschlossen (nicht ausgestossen)")
    print(f"  naive Summe waere:  {d+s+i:8.1f} Mt = Faktor {(d+s+i)/d:.2f}")
    return fac


# ----------------------------------------------------------------------
def build_entity_resolution():
    """Vier Matching-Schwellen. Die Streuung zwischen ihnen ist gemessene
    Zuordnungsunsicherheit und ersetzt einen Teil des gesetzten Rauschens."""
    link = pd.read_parquet("build/src_parent_link.parquet")
    comp = pd.read_parquet("build/src_companies.parquet")
    comp["name_norm"] = comp.company_name.map(normalize)
    lookup = dict(zip(comp.name_norm, comp.company_id))
    choices = list(lookup)
    alias_norm = {normalize(k): v for k, v in MANUAL_ALIASES.items()}
    name_to_id = dict(zip(comp.company_name, comp.company_id))

    parents = link[["parent_name_raw"]].drop_duplicates().reset_index(drop=True)
    parents["name_norm"] = parents.parent_name_raw.map(normalize)

    best = []
    for raw, norm in zip(parents.parent_name_raw, parents.name_norm):
        if norm in alias_norm and alias_norm[norm] in name_to_id:
            best.append((raw, name_to_id[alias_norm[norm]], 100.0, "Manual"))
            continue
        if norm in lookup:
            best.append((raw, lookup[norm], 100.0, "Exact"))
            continue
        hit = process.extractOne(norm, choices, scorer=fuzz.token_sort_ratio)
        if hit:
            best.append((raw, lookup[hit[0]], float(hit[1]), "Fuzzy"))
        else:
            best.append((raw, None, 0.0, "NoMatch"))

    er = pd.DataFrame(best, columns=["name_raw", "company_id", "score", "method"])
    out = []
    for th in THRESHOLDS:
        sub = er.copy()
        sub.loc[sub.score < th, "company_id"] = np.nan
        sub["threshold"] = th
        out.append(sub)
    allth = pd.concat(out, ignore_index=True)
    allth["match_score"] = allth.score / 100.0
    allth.to_parquet(F / "src_entity_resolution.parquet", index=False)

    for th in THRESHOLDS:
        s = allth[allth.threshold == th]
        print(f"  Schwelle {th}: {s.company_id.notna().sum():5,} Namen zugeordnet, "
              f"{s.company_id.nunique():3} Firmen getroffen")
    return allth


# ----------------------------------------------------------------------
def build_company_emissions(er, fac):
    """Zwei Zurechnungsregeln x vier Schwellen = acht Datenvarianten."""
    link = pd.read_parquet("build/src_parent_link.parquet")
    base = link.merge(fac[["facility_id", "reporting_year", "co2e_tonnes"]],
                      on=["facility_id", "reporting_year"], how="inner")

    # Operative Kontrolle: der groesste Eigentuemer traegt 100 Prozent
    idx = base.groupby(["facility_id", "reporting_year"])["parent_share_pct"].idxmax()
    control = base.loc[idx].copy()
    control["weight"] = 1.0
    equity = base.copy()
    equity["weight"] = equity.parent_share_pct / 100.0

    frames = []
    for rule, df in [("Equity", equity), ("Control", control)]:
        for th in THRESHOLDS:
            m = er[(er.threshold == th) & er.company_id.notna()]
            j = df.merge(m[["name_raw", "company_id", "match_score"]],
                         left_on="parent_name_raw", right_on="name_raw", how="inner")
            j["attr"] = j.co2e_tonnes * j.weight
            g = (j.groupby(["company_id", "reporting_year"], as_index=False)
                   .agg(scope1_tonnes=("attr", "sum"),
                        asset_count=("facility_id", "nunique"),
                        match_score_min=("match_score", "min")))
            g["attribution"] = rule
            g["threshold"] = th
            frames.append(g)

    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"reporting_year": "year"})
    out["company_id"] = out.company_id.astype(int)
    out.to_parquet(F / "ana_company_emissions.parquet", index=False)

    piv = (out[out.year == LATEST].groupby(["attribution", "threshold"])
             .agg(firmen=("company_id", "nunique"),
                  mt=("scope1_tonnes", lambda x: x.sum() / 1e6)).round(1))
    print("ana_company_emissions, acht Datenvarianten (Jahr 2023):")
    print(piv.to_string())
    return out


# ----------------------------------------------------------------------
def build_cems_quality():
    """Anteil der Emissionen aus kontinuierlich gemessenen Anlagen.

    Das EPA-Feld Unit Reporting Method unterscheidet Berechnung nach
    Tier 1-3 von direkter Messung (Tier 4 / CEMS). Ein hoher CEMS-Anteil
    heisst: die gemeldete Zahl ist gemessen, nicht geschaetzt.
    """
    df = pd.read_excel(DATA / "unitfuel" / "emissions_by_unit_and_fuel_type_c_d_aa.xlsb",
                       sheet_name="UNIT_DATA", engine="pyxlsb", header=6)
    cols = list(df.columns)
    df = df.rename(columns={cols[0]: "facility_id", cols[6]: "year",
                            cols[11]: "method", cols[13]: "co2"})
    df = df[["facility_id", "year", "method", "co2"]]
    for c in ["facility_id", "year", "co2"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["facility_id", "year", "co2"])
    df = df[(df.year == LATEST) & (df.co2 > 0)]
    df["is_cems"] = df.method.astype(str).str.contains("Tier4|CEMS|P75", case=False, na=False)

    fa = (df.groupby("facility_id")
            .apply(lambda g: pd.Series({
                "co2_total": g.co2.sum(),
                "co2_cems": g.loc[g.is_cems, "co2"].sum()}), include_groups=False)
            .reset_index())
    fa.to_parquet(F / "src_cems_facility.parquet", index=False)
    print(f"src_cems_facility: {len(fa):,} Anlagen, "
          f"CEMS-Anteil gesamt {fa.co2_cems.sum()/fa.co2_total.sum():.1%}")
    return fa


if __name__ == "__main__":
    fac = build_facilities()
    er = build_entity_resolution()
    build_company_emissions(er, fac)
    build_cems_quality()
