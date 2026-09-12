"""Stufe 03: EPA-Konzernnamen auf S&P-500-Ticker aufloesen.

Das Feld ``parent_company`` der EPA ist Freitext und sieht real so aus::

    Empeco IV, LLC and USPF II Ferndale Holdings, LLC (74.33298%);
    Diamond Generating Corporation (14.00002%); Tenaska Energy, Inc. ... (11.667%)

Drei Dinge passieren hier:

1. **Parsen.** Der String wird in Eigentuemer plus Beteiligungsquote zerlegt.
   Die Quote wird spaeter zur Zurechnung der Emissionen benutzt -- eine Anlage,
   die zu 74 % einer Firma gehoert, zaehlt ihr auch nur zu 74 %
   (Equity-Share-Ansatz des GHG-Protokolls).
2. **Normalisieren.** Rechtsformzusaetze und Interpunktion fliegen raus.
3. **Zuordnen.** Erst exakt, dann ueber eine handgepflegte Tochter-Konzern-Tabelle,
   dann unscharf. Jede Zuordnung traegt ``match_confidence`` und
   ``match_method`` mit -- bis in die Oberflaeche.

Der dritte Schritt ist die groesste Fehlerquelle der ganzen Pipeline. Ein
falsch zugeordnetes Kraftwerk verschiebt eine Firma um Dutzende Raenge.
"""
from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process

# Rechtsformen und Fuellwoerter, die fuer den Abgleich nichts beitragen.
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
    """Vergleichsform eines Firmennamens."""
    s = str(name).lower()
    s = re.sub(r"\([^)]*\)", " ", s)          # Klammerinhalte (Quoten) weg
    s = re.sub(r"[^a-z0-9\s]", " ", s)        # Interpunktion weg
    s = _SUFFIX_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_owners(raw: str) -> list[tuple[str, float]]:
    """Zerlegt das Freitextfeld in ``[(Eigentuemer, Anteil), ...]``.

    Ohne Quotenangabe wird gleichmaessig auf die genannten Eigentuemer verteilt.
    """
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
    if total > 1.01:  # gelegentlich summieren die Quoten auf >100 %
        owners = [(n, s / total) for n, s in owners]
    return owners


# ---------------------------------------------------------------------------
# Tochter -> Konzern. Ohne diese Tabelle verliert man die halbe Energiebranche,
# weil die EPA operative Gesellschaften meldet, nicht die boersennotierte Mutter.
# ---------------------------------------------------------------------------
OVERRIDES: dict[str, str] = {
    # Versorger
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
    "tampa electric": "SRE",
    "union electric": "AEE", "ameren illinois": "AEE", "ameren missouri": "AEE",
    "kansas city power light": "EVRG", "westar energy": "EVRG",
    "evergy metro": "EVRG", "evergy kansas central": "EVRG",
    "oklahoma gas electric": "OGE",
    "idaho power": "AEE",
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
    "national grid": "ES",
    "pinnacle west capital": "PNW",
    "portland general electric": "POR",
    "avangrid": "ES",
    # Oel und Gas
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
    # Chemie und Grundstoffe
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
    # Industrie und Transport
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
    # Konsum und Gesundheit
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
    # Technologie
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


def build_lookup(master: pd.DataFrame) -> dict[str, str]:
    """Normalisierter Firmenname -> Ticker, aus der Konstituentenliste."""
    lookup: dict[str, str] = {}
    for _, row in master.iterrows():
        lookup[normalize(row["company"])] = row["ticker"]
    return lookup


def resolve_owners(
    facilities: pd.DataFrame,
    master: pd.DataFrame,
    fuzzy_threshold: int = 92,
) -> pd.DataFrame:
    """Loest jede Anlage/Jahr-Zeile in Eigentuemeranteile je Ticker auf.

    Rueckgabe: eine Zeile je (facility_id, year, ticker) mit ``share``,
    ``match_method`` und ``match_confidence``.
    """
    lookup = build_lookup(master)
    choices = list(lookup.keys())

    # Cache, damit derselbe Konzernname nur einmal aufgeloest wird.
    cache: dict[str, tuple[str | None, str, float]] = {}

    def match_one(raw_name: str) -> tuple[str | None, str, float]:
        key = normalize(raw_name)
        if key in cache:
            return cache[key]
        result: tuple[str | None, str, float]
        if not key:
            result = (None, "leer", 0.0)
        elif key in lookup:
            result = (lookup[key], "exakt", 1.0)
        elif key in OVERRIDES:
            result = (OVERRIDES[key], "override", 0.95)
        else:
            # Override-Tabelle auch als Praefix pruefen: "georgia power" faengt
            # "georgia power services" mit ab.
            hit = next((t for k, t in OVERRIDES.items() if key.startswith(k)), None)
            if hit:
                result = (hit, "override-praefix", 0.90)
            else:
                m = process.extractOne(key, choices, scorer=fuzz.token_set_ratio)
                if m and m[1] >= fuzzy_threshold:
                    result = (lookup[m[0]], "fuzzy", m[1] / 100.0)
                else:
                    result = (None, "kein-treffer", 0.0)
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
    # Mehrere Eigentuemerzeilen auf denselben Ticker zusammenfassen.
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
