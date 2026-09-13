"""Resolve EPA parent-company text to S&P 500 issuers.

Parse owners and percentages, normalize legal names, then match exact names, known subsidiaries, and finally fuzzy names. Missing ownership shares are allocated equally among named owners. Carry the matching method and confidence into diagnostics. Ownership attribution is a major source of model error."""
from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process

# Remove legal suffixes and generic words that add no matching information.
_SUFFIXES = [
    "incorporated", "inc", "corporation", "corp", "company", "companies", "co",
    "limited", "ltd", "llc", "lllp", "llp", "lp", "plc", "holdings", "holding",
    "group", "the", "and", "&", "na", "usa", "us", "america", "american",
    "international", "intl", "worldwide", "global", "enterprises", "industries",
    "partners", "partnership", "trust", "reit", "class",
]
_SUFFIX_RE = re.compile(r"\b(" + "|".join(map(re.escape, _SUFFIXES)) + r")\b")
_SHARE_RE = re.compile(r"\(([\d.]+)\s*%\)")


def normalize(name: str) -> str:
    """Normalize a company name for matching."""
    s = str(name).lower()
    s = re.sub(r"\([^)]*\)", " ", s)          # Remove parenthesized ownership shares.
    s = re.sub(r"[^a-z0-9\s]", " ", s)        # Remove punctuation.
    s = _SUFFIX_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_owners(raw: str) -> list[tuple[str, float]]:
    """Parse owner text into (owner, share) pairs. Allocate equally when shares are absent and normalize totals above 100%."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    owners: list[tuple[str, float]] = []
    for part in parts:
        m = _SHARE_RE.search(part)
        share = float(m.group(1)) / 100.0 if m else None
        name = _SHARE_RE.sub("", part).strip(" ,.")
        if name:
            owners.append((name, share))
    if not owners:
        return []
    missing = [i for i, (_, s) in enumerate(owners) if s is None]
    if missing:
        known = sum(s for _, s in owners if s is not None)
        rest = max(0.0, 1.0 - known) / len(missing)
        owners = [(n, rest if s is None else s) for n, s in owners]
    total = sum(s for _, s in owners)
    if total > 1.01:  # Normalize reported ownership shares when their sum exceeds 100%.
        owners = [(n, s / total) for n, s in owners]
    return owners


# Subsidiary-to-parent mapping, reviewed
# against the team snapshot on 2026-09-12.
# Corrections addressed National Grid/Avangrid
# attributed to Eversource, Idaho Power to
# Ameren, and Tampa Electric to Sempra.
# Facilities often report operating
# subsidiaries rather than listed parents.
OVERRIDES: dict[str, str] = {
    # Utilities.
    "georgia power": "SO", "alabama power": "SO", "mississippi power": "SO",
    "southern power": "SO", "southern electric generating": "SO",
    "florida power light": "NEE", "nextera energy resources": "NEE",
    "gulf power": "NEE",
    "duke energy carolinas": "DUK", "duke energy progress": "DUK",
    "duke energy florida": "DUK", "duke energy indiana": "DUK",
    "duke energy ohio": "DUK", "duke energy kentucky": "DUK",
    "virginia electric power": "D", "dominion energy south carolina": "D",
    "commonwealth edison": "EXC", "peco energy": "EXC", "baltimore gas electric": "EXC",
    "potomac electric power": "EXC", "delmarva power light": "EXC",
    "atlantic city electric": "EXC", "exelon generation": "EXC",
    "pacific gas electric": "PCG",
    "southern california edison": "EIX",
    "san diego gas electric": "SRE", "southern california gas": "SRE",
    "oncor electric delivery": "SRE",
    "consumers energy": "CMS",
    "dte electric": "DTE", "dte gas": "DTE",
    "appalachian power": "AEP", "ohio power": "AEP", "indiana michigan power": "AEP",
    "public service oklahoma": "AEP", "southwestern electric power": "AEP",
    "aep texas": "AEP", "aep generating": "AEP", "kentucky power": "AEP",
    "wisconsin electric power": "WEC", "wisconsin power light": "WEC",
    "wisconsin public service": "WEC", "we power": "WEC",
    "northern states power": "XEL", "public service colorado": "XEL",
    "southwestern public service": "XEL",
    "arizona public service": "PNW",
    "nevada power": "BRK-B", "sierra pacific power": "BRK-B",
    "midamerican energy": "BRK-B", "pacificorp": "BRK-B",
    "berkshire hathaway energy": "BRK-B", "berkshire hathaway": "BRK-B",
    "kern river gas transmission": "BRK-B", "northern natural gas": "BRK-B",
    "burlington northern santa fe": "BRK-B",
    "union electric": "AEE", "ameren illinois": "AEE", "ameren missouri": "AEE",
    "kansas city power light": "EVRG", "westar energy": "EVRG",
    "evergy metro": "EVRG", "evergy kansas central": "EVRG",
    "oklahoma gas electric": "OGE",
    "entergy arkansas": "ETR", "entergy louisiana": "ETR", "entergy mississippi": "ETR",
    "entergy texas": "ETR", "entergy new orleans": "ETR", "system energy resources": "ETR",
    "pplelectric utilities": "PPL", "louisville gas electric": "PPL",
    "kentucky utilities": "PPL", "ppl electric utilities": "PPL",
    "public service electric gas": "PEG", "pseg power": "PEG", "pseg fossil": "PEG",
    "firstenergy generation": "FE", "ohio edison": "FE", "cleveland electric illuminating": "FE",
    "toledo edison": "FE", "jersey central power light": "FE", "monongahela power": "FE",
    "west penn power": "FE", "potomac edison": "FE",
    "alliant energy": "LNT", "interstate power light": "LNT",
    "cenerpoint energy": "CNP", "centerpoint energy": "CNP",
    "nrg energy": "NRG", "nrg texas power": "NRG", "midwest generation": "NRG",
    "vistra": "VST", "luminant generation": "VST", "vistra energy": "VST",
    "dynegy": "VST", "illinois power generating": "VST",
    "talen energy": "VST",
    "constellation energy generation": "CEG", "constellation power": "CEG",
    "calpine": "CEG",
    "atmos energy": "ATO",
    "nisource": "NI", "northern indiana public service": "NI",
    "consolidated edison": "ED", "orange rockland utilities": "ED",
    "eversource energy": "ES", "connecticut light power": "ES",
    "pinnacle west capital": "PNW",
    "portland general electric": "POR",
    # Oil and gas.
    "exxon mobil": "XOM", "exxonmobil": "XOM", "mobil": "XOM",
    "exxonmobil oil": "XOM", "exxonmobil pipeline": "XOM",
    "chevron usa": "CVX", "chevron phillips chemical": "CVX", "chevron": "CVX",
    "conocophillips": "COP", "conocophillips alaska": "COP",
    "phillips 66": "PSX", "phillips 66 pipeline": "PSX", "wrb refining": "PSX",
    "marathon petroleum": "MPC", "marathon oil": "MPC", "andeavor": "MPC",
    "mplx": "MPC", "speedway": "MPC",
    "valero energy": "VLO", "valero refining": "VLO", "premcor refining": "VLO",
    "occidental petroleum": "OXY", "oxy usa": "OXY", "anadarko petroleum": "OXY",
    "occidental chemical": "OXY", "western midstream": "OXY",
    "eog resources": "EOG",
    "devon energy": "DVN", "wpx energy": "DVN",
    "diamondback energy": "FANG", "energen": "FANG", "endeavor energy resources": "FANG",
    "coterra energy": "CTRA", "cabot oil gas": "CTRA", "cimarex energy": "CTRA",
    "apache": "APA", "apa": "APA",
    "hess": "HES",
    "pioneer natural resources": "XOM",
    "kinder morgan": "KMI", "el paso natural gas": "KMI", "tennessee gas pipeline": "KMI",
    "colorado interstate gas": "KMI", "southern natural gas": "KMI",
    "williams": "WMB", "transcontinental gas pipe line": "WMB", "northwest pipeline": "WMB",
    "oneok": "OKE", "oneok partners": "OKE", "magellan midstream": "OKE",
    "targa resources": "TRGP",
    "baker hughes": "BKR", "halliburton": "HAL", "schlumberger": "SLB",
    "expand energy": "EXE", "chesapeake energy": "EXE", "southwestern energy": "EXE",
    "eqt": "EQT", "eqt production": "EQT", "equitrans midstream": "EQT",
    "texas pacific land": "TPL",
    # Chemicals and materials.
    "dow chemical": "DOW", "dow silicones": "DOW", "union carbide": "DOW",
    "dupont": "DD", "e i du pont de nemours": "DD", "corteva": "CTVA",
    "linde": "LIN", "praxair": "LIN",
    "air products chemicals": "APD", "air products": "APD",
    "eastman chemical": "EMN",
    "celanese": "CE", "ppg industries": "PPG", "sherwin williams": "SHW",
    "lyondellbasell": "LYB", "equistar chemicals": "LYB", "houston refining": "LYB",
    "ecolab": "ECL", "nalco": "ECL",
    "albemarle": "ALB", "fmc": "FMC", "mosaic": "MOS", "cf industries": "CF",
    "nucor": "NUE", "nucor steel": "NUE",
    "steel dynamics": "STLD",
    "newmont": "NEM", "freeport mcmoran": "FCX", "freeport minerals": "FCX",
    "international paper": "IP", "weyerhaeuser": "WY", "packaging america": "PKG",
    "ball": "BALL", "ball metal beverage container": "BALL",
    "amcor": "AMCR", "avery dennison": "AVY", "sealed air": "SEE",
    "vulcan materials": "VMC", "martin marietta materials": "MLM",
    "smurfit westrock": "SW", "westrock": "SW", "smurfit kappa": "SW",
    "lennox": "LII",
    # Industry and transport.
    "general electric": "GE", "ge aerospace": "GE", "ge vernova": "GEV",
    "boeing": "BA", "lockheed martin": "LMT", "rtx": "RTX", "raytheon": "RTX",
    "northrop grumman": "NOC", "general dynamics": "GD", "l3harris": "LHX",
    "honeywell": "HON", "honeywell intl": "HON",
    "caterpillar": "CAT", "deere": "DE", "cummins": "CMI", "paccar": "PCAR",
    "emerson electric": "EMR", "eaton": "ETN", "parker hannifin": "PH",
    "illinois tool works": "ITW", "3m": "MMM", "dover": "DOV",
    "union pacific": "UNP", "union pacific railroad": "UNP",
    "csx": "CSX", "csx transportation": "CSX",
    "norfolk southern": "NSC", "norfolk southern railway": "NSC",
    "united parcel service": "UPS", "fedex": "FDX",
    "delta air lines": "DAL", "united airlines": "UAL", "american airlines": "AAL",
    "southwest airlines": "LUV",
    "ford motor": "F", "general motors": "GM", "tesla": "TSLA",
    "whirlpool": "WHR", "carrier": "CARR", "trane technologies": "TT",
    "otis worldwide": "OTIS", "johnson controls": "JCI",
    "masco": "MAS", "mohawk industries": "MHK", "builders firstsource": "BLDR",
    "stanley black decker": "SWK",
    "waste management": "WM", "republic services": "RSG",
    # Consumer businesses and health care.
    "procter gamble": "PG", "colgate palmolive": "CL", "kimberly clark": "KMB",
    "coca cola": "KO", "pepsico": "PEP", "frito lay": "PEP",
    "mondelez": "MDLZ", "kraft heinz": "KHC", "general mills": "GIS",
    "kellanova": "K", "conagra brands": "CAG", "hormel foods": "HRL",
    "tyson foods": "TSN", "archer daniels midland": "ADM", "bunge": "BG",
    "hershey": "HSY", "mccormick": "MKC", "campbell soup": "CPB",
    "altria": "MO", "philip morris": "PM", "constellation brands": "STZ",
    "molson coors": "TAP", "brown forman": "BF-B", "keurig dr pepper": "KDP",
    "estee lauder": "EL", "church dwight": "CHD", "clorox": "CLX",
    "sysco": "SYY", "kroger": "KR", "walmart": "WMT", "costco": "COST",
    "target": "TGT", "home depot": "HD", "lowes": "LOW",
    "johnson johnson": "JNJ", "pfizer": "PFE", "merck": "MRK", "merck sharp dohme": "MRK",
    "abbvie": "ABBV", "abbott laboratories": "ABT", "eli lilly": "LLY",
    "bristol myers squibb": "BMY", "amgen": "AMGN", "gilead sciences": "GILD",
    "regeneron pharmaceuticals": "REGN", "vertex pharmaceuticals": "VRTX",
    "biogen": "BIIB", "moderna": "MRNA", "thermo fisher scientific": "TMO",
    "danaher": "DHR", "becton dickinson": "BDX", "baxter": "BAX",
    "corning": "GLW", "zoetis": "ZTS", "viatris": "VTRS", "organon": "OGN",
    # Technology.
    "intel": "INTC", "micron technology": "MU", "texas instruments": "TXN",
    "analog devices": "ADI", "nvidia": "NVDA", "advanced micro devices": "AMD",
    "applied materials": "AMAT", "lam research": "LRCX", "kla": "KLAC",
    "on semiconductor": "ON", "microchip technology": "MCHP",
    "globalfoundries": "INTC",
    "international business machines": "IBM", "ibm": "IBM",
    "hewlett packard enterprise": "HPE", "hp": "HPQ",
    "microsoft": "MSFT", "alphabet": "GOOGL", "google": "GOOGL",
    "meta platforms": "META", "facebook": "META",
    "amazon": "AMZN", "amazon web services": "AMZN", "amazon com": "AMZN",
    "apple": "AAPL", "seagate technology": "STX", "western digital": "WDC",
    "jabil": "JBL", "flex": "JBL", "amphenol": "APH", "te connectivity": "TEL",
    "keysight technologies": "KEYS", "agilent technologies": "A",
    "coherent": "COHR", "teledyne technologies": "TDY",
}


# Allow only one generic suffix after the
# parent name. Southern California Gas must not
# match Southern Company merely through the
# word Southern.
GENERIC_TAIL = {
    "energy", "resources", "power", "holdings", "financial", "technologies",
    "systems", "brands", "services", "communications", "entertainment",
    "materials", "chemical", "chemicals", "pharmaceuticals", "petroleum",
}


# Selected historical ownership windows.
# Reporting years are inclusive; None means an
# open endpoint. These corrections reduce
# retroactive attribution after acquisitions
# and spin-offs, but are not a complete
# historical ownership database.
VALIDITY: dict[tuple[str, str], tuple[int | None, int | None]] = {
    # Exclude Talen-to-Vistra parent attribution; the historical transaction concerned selected plants rather than acquisition of Talen itself.
    ("talen energy", "VST"): (None, None),
    # Apply the Smurfit Westrock mapping from the configured 2024 merger year.
    ("westrock", "SW"): (2024, None),
    ("smurfit kappa", "SW"): (2024, None),
    # Apply the Pioneer-to-ExxonMobil mapping from 2024.
    ("pioneer natural resources", "XOM"): (2024, None),
    # Apply the Calpine-to-Constellation mapping from 2026.
    ("calpine", "CEG"): (2026, None),
    # Map Exelon generation assets before the 2022
    # Constellation separation.
    ("exelon generation", "EXC"): (None, 2021),
    ("exelon generation", "CEG"): (2022, None),
    # Apply the Anadarko-to-Occidental mapping from 2019.
    ("anadarko petroleum", "OXY"): (2019, None),
}


def owner_valid(key: str, ticker: str, year: int | float | None) -> bool:
    """Check the selected ownership validity window; unmapped cases have no time restriction."""
    rule = VALIDITY.get((key, ticker))
    if rule is None:
        return True
    since, until = rule
    if since is None and until is None:
        return False
    try:
        y = int(year)
    except (TypeError, ValueError):
        return True
    return (since is None or y >= since) and (until is None or y <= until)


def override_prefix(key: str) -> str | None:
    """Match subsidiary prefixes only at word boundaries. This prevents Linde from matching Linden and KLA from matching unrelated names that merely start with the same letters."""
    if not key:
        return None
    for k, t in OVERRIDES.items():
        if key == k or key.startswith(k + " "):
            return t
    return None


def master_prefix(key: str, lookup: dict[str, str]) -> str | None:
    """Accept a company name followed by one permitted generic word, such as Sempra Energy."""
    head, _, tail = key.rpartition(" ")
    if head and tail in GENERIC_TAIL and " " not in tail:
        return lookup.get(head)
    return None


def build_lookup(master: pd.DataFrame) -> dict[str, str]:
    """Map normalized company names to tickers from the index universe."""
    lookup: dict[str, str] = {}
    for _, row in master.iterrows():
        lookup[normalize(row["company"])] = row["ticker"]
    return lookup


def resolve_owners(
    facilities: pd.DataFrame,
    master: pd.DataFrame,
    fuzzy_threshold: int = 92,
) -> pd.DataFrame:
    """Return one row per facility, year, and ticker with share, match_method, and match_confidence."""
    lookup = build_lookup(master)
    choices = list(lookup.keys())

    # Cache repeated owner-name lookups.
    cache: dict[str, tuple[str | None, str, float]] = {}

    def match_one(raw_name: str) -> tuple[str | None, str, float]:
        key = normalize(raw_name)
        if key in cache:
            return cache[key]
        result: tuple[str | None, str, float]
        if not key:
            result = (None, "empty", 0.0)
        elif key in lookup:
            result = (lookup[key], "exact", 1.0)
        elif key in OVERRIDES:
            result = (OVERRIDES[key], "override", 0.95)
        else:
            # Check subsidiary prefixes with word boundaries, including suffixes such as services.
            hit = override_prefix(key)
            if hit:
                result = (hit, "override-praefix", 0.90)
            elif master_prefix(key, lookup):
                result = (master_prefix(key, lookup), "konzern-praefix", 0.85)
            else:
                # Use token_sort instead of token_set: a subset can otherwise receive a perfect match, incorrectly linking US Steel to Steel Dynamics after normalization.
                m = process.extractOne(key, choices, scorer=fuzz.token_sort_ratio)
                if m and m[1] >= fuzzy_threshold:
                    result = (lookup[m[0]], "fuzzy", m[1] / 100.0)
                else:
                    result = (None, "unmatched", 0.0)
        cache[key] = result
        return result

    rows: list[dict] = []
    for fid, year, raw in facilities[
        ["facility_id", "year", "parent_company"]
    ].itertuples(index=False):
        for owner, share in parse_owners(raw):
            ticker, method, conf = match_one(owner)
            if ticker is None:
                continue
            if not owner_valid(normalize(owner), ticker, year):
                continue
            rows.append(
                {
                    "facility_id": fid,
                    "year": year,
                    "ticker": ticker,
                    "share": share,
                    "match_method": method,
                    "match_confidence": conf,
                    "owner_raw": owner,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Combine owner rows resolving to the same ticker.
    agg = (
        out.groupby(["facility_id", "year", "ticker"], as_index=False)
        .agg(
            share=("share", "sum"),
            match_confidence=("match_confidence", "min"),
            match_method=("match_method", "first"),
        )
    )
    agg["share"] = agg["share"].clip(upper=1.0)
    return agg
