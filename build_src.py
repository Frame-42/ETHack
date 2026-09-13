"""
Ebene 1 (src_*): Quelldaten aufbauen, exakt nach UML final_1_quellen.

Erzeugt:
  src_companies.parquet          aus S&P-500-Konstituenten
  src_epa_facility.parquet       Anlage x Jahr, Scope-1-Emissionen (long format)
  src_parent_link.parquet        Anlage -> Konzernname + Eigentumsanteil
  src_entity_resolution.parquet  Konzernname -> company_id inkl. match_score
"""
import re
import numpy as np
import pandas as pd
import openpyxl
from rapidfuzz import process, fuzz
from pathlib import Path

DATA = Path("data")
OUT = Path("build")
OUT.mkdir(exist_ok=True)

YEARS = list(range(2011, 2024))

# ----------------------------------------------------------------------
# src_companies
# ----------------------------------------------------------------------
def build_companies():
    df = pd.read_csv(DATA / "sp500_constituents.csv")
    df = df.rename(columns={
        "Symbol": "ticker",
        "Security": "company_name",
        "GICS Sector": "gics_sector",
        "GICS Sub-Industry": "gics_industry",
        "CIK": "cik",
    })
    df = df[["ticker", "company_name", "gics_sector", "gics_industry", "cik"]].copy()
    df = df.drop_duplicates("ticker").reset_index(drop=True)
    df.insert(0, "company_id", np.arange(1, len(df) + 1))
    df["in_index_flag"] = True
    # Gleichgewichteter Platzhalter-Benchmark; wird durch echte Indexgewichte
    # ersetzt, sobald Marktkapitalisierung vorliegt.
    df["index_weight"] = 1.0 / len(df)
    df["country_hq"] = "US"
    df.to_parquet(OUT / "src_companies.parquet", index=False)
    print(f"src_companies: {len(df)} Firmen, {df.gics_sector.nunique()} Sektoren")
    return df


# ----------------------------------------------------------------------
# src_epa_facility  (aus dem Mehrjahres-Blatt, in Langformat gedreht)
# ----------------------------------------------------------------------
def build_epa_facility():
    path = DATA / "epa_zip" / "ghgp_data_by_year_2023.xlsx"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Direct Point Emitters"]

    rows = ws.iter_rows(min_row=4, values_only=True)
    header = list(next(rows))
    records = [r for r in rows if r[0] is not None]
    wide = pd.DataFrame(records, columns=header)

    ycols = {f"{y} Total reported direct emissions": y for y in YEARS}
    keep = ["Facility Id", "Facility Name", "State", "Primary NAICS Code",
            "Latest Reported Industry Type (sectors)"] + list(ycols)
    wide = wide[[c for c in keep if c in wide.columns]]

    long = wide.melt(
        id_vars=["Facility Id", "Facility Name", "State", "Primary NAICS Code",
                 "Latest Reported Industry Type (sectors)"],
        value_vars=[c for c in ycols if c in wide.columns],
        var_name="ycol", value_name="co2e_tonnes",
    )
    long["reporting_year"] = long["ycol"].map(ycols).astype(int)
    long = long.drop(columns="ycol").rename(columns={
        "Facility Id": "facility_id",
        "Facility Name": "facility_name",
        "State": "state",
        "Primary NAICS Code": "naics_code",
        "Latest Reported Industry Type (sectors)": "epa_sector",
    })
    long["co2e_tonnes"] = pd.to_numeric(long["co2e_tonnes"], errors="coerce")
    long = long.dropna(subset=["co2e_tonnes"])
    long = long[long["co2e_tonnes"] > 0]
    long["facility_id"] = long["facility_id"].astype("int64")

    long.to_parquet(OUT / "src_epa_facility.parquet", index=False)
    print(f"src_epa_facility: {len(long):,} Anlage-Jahr-Zeilen, "
          f"{long.facility_id.nunique():,} Anlagen, "
          f"{long.co2e_tonnes.sum()/1e9:.2f} Mrd. t ueber alle Jahre")
    return long


# ----------------------------------------------------------------------
# src_parent_link
# ----------------------------------------------------------------------
def build_parent_link():
    frames = []
    for year in YEARS:
        try:
            df = pd.read_excel(
                "/mnt/user-data/uploads/ghgp_data_parent_company.xlsb",
                engine="pyxlsb", sheet_name=str(year),
            )
        except Exception as e:
            print(f"  Blatt {year} uebersprungen: {e}")
            continue
        df.columns = [str(c).strip().upper() for c in df.columns]
        need = {"GHGRP FACILITY ID": "facility_id",
                "PARENT COMPANY NAME": "parent_name_raw",
                "PARENT CO. PERCENT OWNERSHIP": "parent_share_pct"}
        if not set(need).issubset(df.columns):
            continue
        sub = df[list(need)].rename(columns=need)
        sub["reporting_year"] = year
        frames.append(sub)

    link = pd.concat(frames, ignore_index=True)
    link["facility_id"] = pd.to_numeric(link["facility_id"], errors="coerce")
    link = link.dropna(subset=["facility_id", "parent_name_raw"])
    link["facility_id"] = link["facility_id"].astype("int64")
    link["parent_share_pct"] = pd.to_numeric(
        link["parent_share_pct"], errors="coerce").fillna(100.0).clip(0, 100)
    link["parent_name_raw"] = link["parent_name_raw"].astype(str).str.strip()

    link.to_parquet(OUT / "src_parent_link.parquet", index=False)
    print(f"src_parent_link: {len(link):,} Zeilen, "
          f"{link.parent_name_raw.nunique():,} eindeutige Konzernnamen")
    return link


# ----------------------------------------------------------------------
# src_entity_resolution
# ----------------------------------------------------------------------
LEGAL_SUFFIXES = [
    "incorporated", "inc", "corporation", "corp", "company", "co", "llc", "l l c",
    "lp", "llp", "plc", "ltd", "limited", "holdings", "holding", "group",
    "the", "usa", "us", "america", "american", "international", "intl",
    "enterprises", "industries", "partners", "sa", "nv", "ag", "gmbh", "trust",
]
MANUAL_ALIASES = {
    # Haeufige Faelle, in denen Konzernname und Boersenname stark auseinanderliegen.
    "alphabet": "Alphabet Inc.", "google": "Alphabet Inc.",
    "meta platforms": "Meta Platforms", "facebook": "Meta Platforms",
    "exxon mobil": "ExxonMobil", "exxonmobil": "ExxonMobil",
    "berkshire hathaway energy": "Berkshire Hathaway",
    "berkshire hathaway": "Berkshire Hathaway",
    "alcoa": "Alcoa", "dow": "Dow Inc.", "dupont": "DuPont",
    "nextera energy": "NextEra Energy", "florida power light": "NextEra Energy",
    "duke energy": "Duke Energy", "southern": "Southern Company",
    "american electric power": "American Electric Power",
    "consolidated edison": "Consolidated Edison",
    "public service enterprise": "Public Service Enterprise Group",
    "dominion energy": "Dominion Energy", "entergy": "Entergy",
    "xcel energy": "Xcel Energy", "wec energy": "WEC Energy Group",
    "dte energy": "DTE Energy", "ameren": "Ameren", "cms energy": "CMS Energy",
    "ppl": "PPL Corporation", "firstenergy": "FirstEnergy",
    "edison international": "Edison International",
    "pg e": "PG&E Corporation", "pacific gas electric": "PG&E Corporation",
    "sempra": "Sempra", "aes": "AES Corporation", "nrg energy": "NRG Energy",
    "vistra": "Vistra", "constellation energy": "Constellation Energy",
    "chevron": "Chevron Corporation", "conocophillips": "ConocoPhillips",
    "marathon petroleum": "Marathon Petroleum", "phillips 66": "Phillips 66",
    "valero energy": "Valero Energy", "occidental petroleum": "Occidental Petroleum",
    "eog resources": "EOG Resources", "devon energy": "Devon Energy",
    "diamondback energy": "Diamondback Energy", "coterra energy": "Coterra",
    "expand energy": "Expand Energy", "eqt": "EQT Corporation",
    "williams": "Williams Companies", "kinder morgan": "Kinder Morgan",
    "oneok": "ONEOK", "targa resources": "Targa Resources",
    "nucor": "Nucor", "steel dynamics": "Steel Dynamics",
    "linde": "Linde plc", "air products chemicals": "Air Products",
    "lyondellbasell": "LyondellBasell", "celanese": "Celanese",
    "eastman chemical": "Eastman Chemical", "ppg industries": "PPG Industries",
    "sherwin williams": "Sherwin-Williams", "mosaic": "Mosaic Company",
    "corteva": "Corteva", "international paper": "International Paper",
    "packaging america": "Packaging Corporation of America",
    "ball": "Ball Corporation", "amcor": "Amcor",
    "general motors": "General Motors", "ford motor": "Ford Motor Company",
    "tesla": "Tesla, Inc.", "boeing": "Boeing", "general electric": "GE Aerospace",
    "honeywell": "Honeywell", "3m": "3M", "caterpillar": "Caterpillar",
    "deere": "Deere & Company", "procter gamble": "Procter & Gamble",
    "pepsico": "PepsiCo", "coca cola": "Coca-Cola Company",
    "general mills": "General Mills", "kraft heinz": "Kraft Heinz",
    "tyson foods": "Tyson Foods", "archer daniels midland": "Archer Daniels Midland",
    "microsoft": "Microsoft", "intel": "Intel", "micron technology": "Micron Technology",
    "texas instruments": "Texas Instruments", "apple": "Apple Inc.",
    "amazon com": "Amazon", "ibm": "IBM",
    "johnson johnson": "Johnson & Johnson", "pfizer": "Pfizer",
    "merck": "Merck & Co.", "eli lilly": "Eli Lilly and Company",
    "abbvie": "AbbVie", "bristol myers squibb": "Bristol Myers Squibb",
    "waste management": "Waste Management", "republic services": "Republic Services",
    "union pacific": "Union Pacific", "csx": "CSX Corporation",
    "norfolk southern": "Norfolk Southern", "fedex": "FedEx",
    "united parcel service": "United Parcel Service",
    "delta air lines": "Delta Air Lines", "united airlines": "United Airlines Holdings",
    "southwest airlines": "Southwest Airlines", "american airlines": "American Airlines Group",
    "martin marietta materials": "Martin Marietta Materials",
    "vulcan materials": "Vulcan Materials", "freeport mcmoran": "Freeport-McMoRan",
    "newmont": "Newmont", "dover": "Dover Corporation",
    "emerson electric": "Emerson Electric", "parker hannifin": "Parker Hannifin",
    "illinois tool works": "Illinois Tool Works", "cummins": "Cummins",
    "paccar": "Paccar", "whirlpool": "Whirlpool Corporation",
    "stanley black decker": "Stanley Black & Decker",
    "smurfit westrock": "Smurfit WestRock", "westrock": "Smurfit WestRock",
    "weyerhaeuser": "Weyerhaeuser", "cf industries": "CF Industries",
    "albemarle": "Albemarle Corporation", "dow chemical": "Dow Inc.",
    "huntsman": "Huntsman Corporation", "axalta": "Axalta",
    "hershey": "Hershey Company", "kellanova": "Kellanova",
    "conagra brands": "Conagra Brands", "campbell soup": "Campbell's Company",
    "molson coors": "Molson Coors Beverage Company",
    "constellation brands": "Constellation Brands",
    "colgate palmolive": "Colgate-Palmolive", "kimberly clark": "Kimberly-Clark",
    "clorox": "Clorox", "church dwight": "Church & Dwight",
    "corning": "Corning Inc.", "applied materials": "Applied Materials",
    "analog devices": "Analog Devices", "nvidia": "Nvidia",
    "broadcom": "Broadcom", "qualcomm": "Qualcomm",
    "lockheed martin": "Lockheed Martin", "rtx": "RTX Corporation",
    "northrop grumman": "Northrop Grumman", "general dynamics": "General Dynamics",
    "l3harris technologies": "L3Harris", "textron": "Textron",
    "howmet aerospace": "Howmet Aerospace", "carrier global": "Carrier Global",
    "trane technologies": "Trane Technologies", "johnson controls": "Johnson Controls",
    "masco": "Masco", "mohawk industries": "Mohawk Industries",
    "sealed air": "Sealed Air", "avery dennison": "Avery Dennison",
    "nisource": "NiSource", "atmos energy": "Atmos Energy",
    "centerpoint energy": "CenterPoint Energy", "evergy": "Evergy",
    "alliant energy": "Alliant Energy", "pinnacle west capital": "Pinnacle West",
    "eversource energy": "Eversource", "exelon": "Exelon",
    "american water works": "American Water Works",
}


def normalize(name: str) -> str:
    s = str(name).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = [t for t in s.split() if t not in LEGAL_SUFFIXES]
    return " ".join(toks) if toks else s


def build_entity_resolution(companies, parent_link, threshold=90):
    parents = (parent_link[["parent_name_raw"]].drop_duplicates()
               .reset_index(drop=True))
    parents["name_norm"] = parents["parent_name_raw"].map(normalize)

    comp = companies[["company_id", "company_name"]].copy()
    comp["name_norm"] = comp["company_name"].map(normalize)
    lookup = dict(zip(comp["name_norm"], comp["company_id"]))
    choices = list(lookup.keys())

    alias_norm = {normalize(k): v for k, v in MANUAL_ALIASES.items()}
    name_to_id = dict(zip(comp["company_name"], comp["company_id"]))

    out = []
    for raw, norm in zip(parents["parent_name_raw"], parents["name_norm"]):
        cid, score, method = None, 0.0, "NoMatch"

        if norm in alias_norm and alias_norm[norm] in name_to_id:
            cid, score, method = name_to_id[alias_norm[norm]], 100.0, "Manual"
        elif norm in lookup:
            cid, score, method = lookup[norm], 100.0, "Exact"
        else:
            hit = process.extractOne(norm, choices, scorer=fuzz.token_sort_ratio)
            if hit and hit[1] >= threshold:
                cid, score, method = lookup[hit[0]], float(hit[1]), "Fuzzy"
            elif hit:
                score = float(hit[1])

        out.append((raw, norm, cid, score, method))

    er = pd.DataFrame(out, columns=[
        "name_raw", "name_norm", "company_id", "match_score", "match_method"])
    er.insert(0, "match_id", np.arange(1, len(er) + 1))
    er["source_system"] = "EPA"
    er["reviewed"] = er["match_method"].isin(["Manual", "Exact"])
    er["match_score"] = er["match_score"] / 100.0

    er.to_parquet(OUT / "src_entity_resolution.parquet", index=False)
    matched = er["company_id"].notna().sum()
    print(f"src_entity_resolution: {len(er):,} Konzernnamen, "
          f"{matched:,} zugeordnet ({matched/len(er)*100:.1f}%), "
          f"{er.company_id.nunique()} verschiedene S&P-Firmen getroffen")
    print(er["match_method"].value_counts().to_string())
    return er


if __name__ == "__main__":
    companies = build_companies()
    facilities = build_epa_facility()
    links = build_parent_link()
    er = build_entity_resolution(companies, links)
