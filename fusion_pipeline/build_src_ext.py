"""
Ebene 1, Erweiterung: Umsatz, Brennstoffmix und SBTi-Ziele.

Erzeugt:
  src_financials.parquet    Umsatz je Firma (TTM)
  src_fuel_mix.parquet      Kohle-/Gas-/Oel-Anteil der Verbrennungsemissionen
  src_sbti_target.parquet   Validierte Klimaziele inkl. geparster Zielrate
"""
import re
import numpy as np
import pandas as pd
from pathlib import Path
from rapidfuzz import process, fuzz
from build_src import normalize, MANUAL_ALIASES

DATA = Path("data")
B = Path("build")
LATEST = 2023


# ----------------------------------------------------------------------
def build_financials():
    comp = pd.read_parquet(B / "src_companies.parquet")
    rev = pd.read_csv(DATA / "revenue.csv").drop_duplicates("ticker")
    df = comp[["company_id", "ticker"]].merge(rev, on="ticker", how="inner")
    df["fiscal_year"] = LATEST
    df["revenue_usd"] = df["revenue_busd"] * 1e9
    # Quelle ist ein TTM-Wert; als Stichtagsgroesse mit 12% relativer
    # Unsicherheit angesetzt (Geschaeftsjahresversatz + Waehrungs-/Abgrenzungseffekte)
    df["revenue_se_rel"] = 0.12
    df = df[["company_id", "ticker", "fiscal_year", "revenue_usd", "revenue_se_rel"]]
    df.to_parquet(B / "src_financials.parquet", index=False)
    print(f"src_financials: {len(df)} Firmen mit Umsatz")
    return df


# ----------------------------------------------------------------------
COAL_PAT = re.compile(r"coal|lignite|anthracite|coke|petroleum coke", re.I)
GAS_PAT = re.compile(r"natural gas|methane|propane|lpg|landfill gas|blast furnace gas|coke oven gas", re.I)
OIL_PAT = re.compile(r"petroleum|diesel|fuel oil|kerosene|gasoline|residual|naphtha|asphalt", re.I)
BIO_PAT = re.compile(r"biomass|wood|biogenic|ethanol|biodiesel|agricultural", re.I)


def classify_fuel(general, specific):
    s = f"{general} {specific}"
    if BIO_PAT.search(s):
        return "Biomasse"
    if COAL_PAT.search(s):
        return "Kohle"
    if GAS_PAT.search(s):
        return "Gas"
    if OIL_PAT.search(s):
        return "Oel"
    return "Sonstige"


def build_fuel_mix():
    path = DATA / "unitfuel" / "emissions_by_unit_and_fuel_type_c_d_aa.xlsb"
    df = pd.read_excel(path, sheet_name="FUEL_DATA", engine="pyxlsb", header=6)
    df.columns = [str(c) for c in df.columns]
    cols = list(df.columns)
    # Spalten nach Position: 0 Facility Id, 6 Reporting Year,
    # 10 General Fuel Type, 11 Specific Fuel Type, letzte = CO2-Emissionen
    df = df.rename(columns={cols[0]: "facility_id", cols[6]: "reporting_year",
                            cols[10]: "fuel_general", cols[11]: "fuel_specific",
                            cols[-1]: "co2_tonnes"})
    df = df[["facility_id", "reporting_year", "fuel_general", "fuel_specific", "co2_tonnes"]]
    df["facility_id"] = pd.to_numeric(df["facility_id"], errors="coerce")
    df["reporting_year"] = pd.to_numeric(df["reporting_year"], errors="coerce")
    df["co2_tonnes"] = pd.to_numeric(df["co2_tonnes"], errors="coerce")
    df = df.dropna(subset=["facility_id", "reporting_year", "co2_tonnes"])
    df = df[(df.reporting_year == LATEST) & (df.co2_tonnes > 0)]
    df["facility_id"] = df["facility_id"].astype("int64")

    df["fuel_class"] = [classify_fuel(g, s) for g, s
                        in zip(df.fuel_general.astype(str), df.fuel_specific.astype(str))]

    # Auf Firmenebene hochrechnen
    link = pd.read_parquet(B / "src_parent_link.parquet")
    er = pd.read_parquet(B / "src_entity_resolution.parquet").dropna(subset=["company_id"])
    er["company_id"] = er["company_id"].astype(int)
    l = link[link.reporting_year == LATEST]

    m = (df.merge(l[["facility_id", "parent_name_raw", "parent_share_pct"]], on="facility_id")
           .merge(er[["name_raw", "company_id"]], left_on="parent_name_raw", right_on="name_raw"))
    m["attr"] = m.co2_tonnes * m.parent_share_pct / 100.0

    piv = (m.pivot_table(index="company_id", columns="fuel_class",
                         values="attr", aggfunc="sum", fill_value=0.0))
    for c in ["Kohle", "Gas", "Oel", "Biomasse", "Sonstige"]:
        if c not in piv.columns:
            piv[c] = 0.0
    fossil = piv[["Kohle", "Gas", "Oel"]].sum(axis=1)
    out = pd.DataFrame({
        "company_id": piv.index,
        "combustion_total": piv.sum(axis=1).values,
        "fossil_total": fossil.values,
        "coal_share": np.where(fossil > 0, piv["Kohle"] / fossil.replace(0, np.nan), np.nan),
        "gas_share": np.where(fossil > 0, piv["Gas"] / fossil.replace(0, np.nan), np.nan),
        "n_fuel_rows": m.groupby("company_id").size().reindex(piv.index).values,
    })
    out["coal_share"] = out["coal_share"].fillna(0.0).clip(0, 1)
    out["gas_share"] = out["gas_share"].fillna(0.0).clip(0, 1)
    # Unsicherheit des Anteils naeherungsweise binomial
    n = out["n_fuel_rows"].clip(lower=2)
    out["coal_share_se"] = np.sqrt(out.coal_share * (1 - out.coal_share) / n).clip(0.005, 0.25)

    out.to_parquet(B / "src_fuel_mix.parquet", index=False)
    print(f"src_fuel_mix: {len(out)} Firmen, "
          f"{(out.coal_share > 0.5).sum()} davon ueberwiegend Kohle, "
          f"median Kohleanteil {out.coal_share.median():.3f}")
    return out


# ----------------------------------------------------------------------
TARGET_PAT = re.compile(
    r"reduce\s+(?:absolute\s+)?(?:scope\s*1\s*and\s*(?:scope\s*)?2\s+)?"
    r"(?:GHG\s+)?emissions\s+([\d.]+)\s*%\s+by\s+(\d{4})\s+from\s+a\s+(\d{4})\s+base\s*year",
    re.I)


def parse_target(text):
    """Zielrate aus dem Zieltext der SBTi ziehen."""
    if not isinstance(text, str):
        return np.nan, np.nan, np.nan
    m = TARGET_PAT.search(text)
    if not m:
        return np.nan, np.nan, np.nan
    pct, ty, by = float(m.group(1)), int(m.group(2)), int(m.group(3))
    if ty <= by or pct <= 0 or pct >= 100:
        return np.nan, np.nan, np.nan
    # geforderte jaehrliche log-Rate
    req = np.log(1 - pct / 100.0) / (ty - by)
    return req, by, ty


def build_sbti():
    df = pd.read_excel("/mnt/user-data/uploads/companies-excel.xlsx", sheet_name="Data")
    df = df[df.organization_type.astype(str).str.contains("Corporate|Financial", case=False, na=False, regex=True)
            | df.organization_type.isna()]

    comp = pd.read_parquet(B / "src_companies.parquet")
    comp["name_norm"] = comp.company_name.map(normalize)
    lookup = dict(zip(comp.name_norm, comp.company_id))
    choices = list(lookup)
    alias_norm = {normalize(k): v for k, v in MANUAL_ALIASES.items()}
    name_to_id = dict(zip(comp.company_name, comp.company_id))

    rows = []
    for r in df.itertuples():
        raw = str(r.company_name)
        norm = normalize(raw)
        cid, score = None, 0.0
        if norm in alias_norm and alias_norm[norm] in name_to_id:
            cid, score = name_to_id[alias_norm[norm]], 1.0
        elif norm in lookup:
            cid, score = lookup[norm], 1.0
        else:
            hit = process.extractOne(norm, choices, scorer=fuzz.token_sort_ratio)
            if hit and hit[1] >= 93:
                cid, score = lookup[hit[0]], hit[1] / 100.0
        if cid is None:
            continue
        req, by, ty = parse_target(getattr(r, "full_target_language", None))
        rows.append({
            "company_id": cid, "match_score": score,
            "company_name_raw": raw,
            "near_term_status": r.near_term_status,
            "net_zero_status": r.net_zero_status,
            "net_zero_year": getattr(r, "net_zero_year", np.nan),
            "required_cagr": req, "base_year": by, "target_year": ty,
        })

    out = pd.DataFrame(rows)
    # Pro Firma die Zeile mit dem besten Match und geparstem Ziel behalten
    out["has_target"] = out.required_cagr.notna()
    out = (out.sort_values(["company_id", "has_target", "match_score"],
                           ascending=[True, False, False])
              .drop_duplicates("company_id"))
    out["net_zero_year"] = pd.to_numeric(out["net_zero_year"], errors="coerce")
    out["sbti_validated"] = out.near_term_status.astype(str).str.contains("Targets set", na=False)
    out.to_parquet(B / "src_sbti_target.parquet", index=False)
    print(f"src_sbti_target: {len(out)} S&P-Firmen zugeordnet, "
          f"{out.sbti_validated.sum()} mit validiertem Nahziel, "
          f"{out.required_cagr.notna().sum()} mit auswertbarer Zielrate "
          f"(median {out.required_cagr.median()*100:.2f}%/a)")
    return out


if __name__ == "__main__":
    build_financials()
    build_fuel_mix()
    build_sbti()
