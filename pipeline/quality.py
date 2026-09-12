"""Regelprüfung: findet auffällige Werte und legt zu jedem ein Belegpaket an.

Drei Arten von Regeln, in dieser Reihenfolge der Beweiskraft:

1. **Harte Grenzen.** Werte, die es nicht geben kann: mehr als 12
   Verstoßquartale in drei Jahren, mehr CO2 je MWh als Braunkohle, zwei
   Ticker mit derselben CIK.
2. **Mechanismen.** Werte, die durch einen bekannten Fehlweg entstehen:
   0 statt fehlend, ein Programm, das die Größe nicht misst, ein Nenner aus
   unplausiblen Stunden, eine Zuordnung vor dem Konzernereignis.
3. **Statistik.** Werte, die im Branchenvergleich extrem sind. Die sind nicht
   falsch, nur prüfenswert -- echte Extreme gibt es.

Jede Regel liefert ``fehler`` (nicht verrechnen) oder ``pruefen`` (Beleg
nötig) und ein Belegpaket für die KI-Prüfung. Die Schwere setzt die Regel,
nicht das Modell.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .config import OUT, RAW
from .resolve import OVERRIDES, master_prefix, normalize, override_prefix, resolve_owners

CURRENT_YEAR = 2026
CO2_PROGRAMS = {"ARP", "RGGI", "NSPS4T"}  # laut CAMD Power Sector Emissions Data Guide melden nur diese CO2; SIPNOX nur NOx
CORE_METRICS = {"scope1_t", "co2_intensity", "intensity_cagr", "absolute_cagr"}


@dataclass
class Flag:
    rule: str
    severity: str           # fehler | pruefen
    ticker: str
    metric: str
    year: int | None
    value: float | None
    message: str
    impact_t: float = 0.0
    ranking_relevant: bool = False
    evidence: dict = field(default_factory=dict)


class Context:
    """Lädt alles einmal, damit die Regeln nur noch nachschlagen."""

    def __init__(self) -> None:
        self.long = pd.read_parquet(OUT / "dataset_long.parquet")
        self.master = pd.read_parquet(RAW / "sp500_master.parquet")
        self.names = self.master.set_index("ticker")[["company", "gics_sector"]]
        self.cy = pd.read_csv(OUT / "company_year.csv")
        self.bands = pd.read_csv(OUT / "rangbaender_periode_a.csv")
        self.ranked = set(self.bands["ticker"])
        self.lookup = {normalize(r.company): r.ticker for r in self.master.itertuples()}
        fac = pd.read_parquet(RAW / "epa_facility.parquet")
        emi = pd.read_parquet(RAW / "epa_emission.parquet")
        self.fac_year = fac.merge(emi, on=["facility_id", "year"], how="left")
        own = resolve_owners(self.fac_year[["facility_id", "year", "parent_company"]], self.master)
        self.attrib = self.fac_year.merge(own, on=["facility_id", "year"])
        self.attrib["att_t"] = self.attrib["scope1_t"] * self.attrib["share"]

    def to_ticker(self, name) -> str | None:
        k = normalize(name)
        if not k:
            return None
        if k in self.lookup:
            return self.lookup[k]
        if k in OVERRIDES:
            return OVERRIDES[k]
        return override_prefix(k) or master_prefix(k, self.lookup)

    def series(self, ticker: str, metric: str) -> dict:
        s = self.long[(self.long.ticker == ticker) & (self.long.metric == metric)]
        return {int(y): round(float(v), 4) for y, v in zip(s.year, s.value)}

    def sector_stats(self, ticker: str, metric: str) -> dict:
        sector = self.names.gics_sector.get(ticker)
        s = self.long[(self.long.metric == metric) & (self.long.gics_sector == sector)]
        s = s.sort_values("year").groupby("ticker").value.last()
        if s.empty:
            return {}
        return {"branche": sector, "n": int(len(s)), "median": float(s.median()),
                "p90": float(s.quantile(0.9)), "max": float(s.max())}


# ---------------------------------------------------------------------------
# Regeln
# ---------------------------------------------------------------------------

def r_duplicate_cik(c: Context) -> list[Flag]:
    """Aktiengattungen derselben CIG doppelt im *Bestand*.

    Die Indexliste führt beide Gattungen bewusst; ein Fehler ist es erst,
    wenn beide mit Werten im Datensatz stehen. ``dedupe_cik`` in
    ``consolidate.py`` führt sie zusammen -- diese Regel ist die Kontrolle.
    """
    out = []
    im_bestand = set(c.long.ticker)
    for cik, g in c.master.groupby("cik"):
        if len(g) < 2:
            continue
        dabei = sorted(set(g.ticker) & im_bestand)
        if len(dabei) < 2:
            continue
        keep, *dups = dabei
        for t in dups:
            out.append(Flag("F01_doppelte_cik", "fehler", t, "*", None, None,
                            f"Teilt CIK {cik} mit {keep}: alle Konzernwerte stehen doppelt im Bestand.",
                            evidence={"cik": int(cik), "aktiengattungen": sorted(g.ticker)}))
    return out


def r_zero_emissions(c: Context) -> list[Flag]:
    out = []
    z = c.cy[c.cy.scope1_t == 0]
    for r in z.itertuples(index=False):
        rows = c.attrib[(c.attrib.ticker == r.ticker) & (c.attrib.year == r.year)]
        supplied = float(rows.supplied_t.fillna(0).sum())
        prev = c.cy[(c.cy.ticker == r.ticker) & (c.cy.year < r.year)].sort_values("year").tail(1)
        prev_t = float(prev.scope1_t.iloc[0]) if len(prev) else None
        kind = ("reiner Lieferant (Kraftstoff geliefert, nicht selbst emittiert)" if supplied > 0
                else "Anlage gemeldet, aber keine Emissionsmenge -- möglich nach Off-Ramp 40 CFR 98.2(i)")
        out.append(Flag("F02_null_statt_fehlend", "fehler", r.ticker, "scope1_t", int(r.year), 0.0,
                        f"Exakt 0 t trotz zugeordneter Anlage: {kind}. 0 bedeutet hier 'nicht gemessen', nicht 'emissionsfrei'.",
                        impact_t=prev_t or 0.0, ranking_relevant=r.ticker in c.ranked,
                        evidence={"anlagen": int(rows.facility_id.nunique()),
                                  "anlagentypen": sorted(set(rows.facility_types.dropna()))[:4],
                                  "geliefert_t": supplied, "vorjahr_t": prev_t,
                                  "zeitreihe_scope1": c.series(r.ticker, "scope1_t")}))
    return out


def r_campd_program(c: Context) -> list[Flag]:
    out = []
    ep, fp = RAW / "campd_emission.parquet", RAW / "campd_facility.parquet"
    if not (ep.exists() and fp.exists()):
        return out
    emi, fac = pd.read_parquet(ep), pd.read_parquet(fp)
    if "programCodeInfo" not in fac.columns:
        return out
    from .sources.epa_campd import split_owner_operator
    link = []
    for fid, yr, raw, prog, name in fac[["facilityId", "year", "ownerOperator", "programCodeInfo", "facilityName"]].itertuples(index=False):
        for nm, role in split_owner_operator(raw):
            t = c.to_ticker(nm) if role == "owner" else None
            if t:
                link.append((fid, yr, t, str(prog or ""), name))
    L = pd.DataFrame(link, columns=["facilityId", "year", "ticker", "programs", "facilityName"]).drop_duplicates()
    j = L.merge(emi, on=["facilityId", "year"], how="left")
    # Der Programmfilter in consolidate.py nimmt Anlagen ohne CO2-Pflicht
    # heraus; ihre Null steht gar nicht mehr im Datensatz. Geprüft wird
    # deshalb nur, was exportiert wurde.
    exportiert = c.long[c.long.metric == "campd_co2_t"]
    vorhanden = {(r.ticker, int(r.year)) for r in exportiert.itertuples(index=False)}
    for (t, yr), g in j.groupby(["ticker", "year"]):
        if g.co2_t.fillna(0).sum() > 0 or (t, int(yr)) not in vorhanden:
            continue
        progs = sorted({p.strip() for s in g.programs for p in s.split(",") if p.strip()})
        measures = bool(set(progs) & CO2_PROGRAMS)
        out.append(Flag("F03_campd_programm_ohne_co2", "pruefen" if measures else "fehler", t, "campd_co2_t", int(yr), 0.0,
                        ("0 t CO2 bei Anlagen, deren Programm CO2 verlangt -- Stilllegung, Biomasse oder Fehlzuordnung prüfen."
                         if measures else
                         f"0 t CO2, weil die Anlagen nur in Programmen ohne CO2-Pflicht melden ({', '.join(progs)}). Die Größe wird nicht gemessen."),
                        ranking_relevant=False,
                        evidence={"anlagen": sorted(set(g.facilityName))[:5], "programme": progs,
                                  "last_mwh": float(g.gross_load_mwh.fillna(0).sum())}))
    return out


def r_echo_quarters(c: Context) -> list[Flag]:
    out = []
    p = OUT / "echo_je_firma.csv"
    if not p.exists():
        return out
    e = pd.read_csv(p)
    col = "verstossquartale_je_anlage" if "verstossquartale_je_anlage" in e.columns else "vq_je_anlage"
    for r in e[e[col] > 12].itertuples(index=False):
        out.append(Flag("F04_echo_quartale_unmoeglich", "fehler", r.ticker, "echo_nc_quarters_per_site", 2025, float(getattr(r, col)),
                        "Mehr als 12 Verstoßquartale je Anlage sind in einem 3-Jahres-Fenster unmöglich. Ursache: Anlage beim "
                        "Verbinden mit den EPA-Anlagen mehrfach gezählt (mehrere Schreibweisen des Konzernnamens).",
                        evidence={"anlagen": int(r.anlagen), "verstossquartale_summe": float(r.verstossquartale),
                                  "hinweis": "Historie: 12 Zeichen, _ ok, V Verstoß, S schwer, U ungeklärt"}))
    return out


def r_egrid(c: Context) -> list[Flag]:
    """Stromrate: nur geprüft, was im Datensatz steht.

    Nicht-Versorger und physikalisch unmögliche Raten filtert
    ``scripts/05b_firmenaggregate.py`` inzwischen heraus.
    """
    out = []
    p = OUT / "egrid_je_firma.csv"
    if not p.exists():
        return out
    e = pd.read_csv(p)
    behalten = set(c.long[c.long.metric == "t_co2_pro_mwh"].ticker)
    e = e[e.ticker.isin(behalten) & e.t_co2_pro_mwh.notna()]
    for r in e.itertuples(index=False):
        sector = c.names.gics_sector.get(r.ticker)
        if r.t_co2_pro_mwh > 1.3:
            out.append(Flag("F05_egrid_physik", "fehler", r.ticker, "t_co2_pro_mwh", 2023, float(r.t_co2_pro_mwh),
                            "Über 1,3 t CO2 je MWh liegt jenseits jeder Kraftwerkstechnik (Braunkohle rund 1,1). "
                            "Typisch: Heizkraftwerk mit Wärmeauskopplung, Strom nur Nebenprodukt.",
                            evidence={"kraftwerke": int(r.kraftwerke), "mwh": float(r.mwh), "co2_t": float(r.co2_t), "branche": sector}))
        elif sector != "Utilities":
            out.append(Flag("F06_egrid_nicht_versorger", "pruefen", r.ticker, "t_co2_pro_mwh", 2023, float(r.t_co2_pro_mwh),
                            "Stromrate eines Nicht-Versorgers: beschreibt Eigenanlagen, nicht das Geschäftsmodell.",
                            evidence={"kraftwerke": int(r.kraftwerke), "mwh": float(r.mwh), "branche": sector}))
    return out


def r_trend_base(c: Context) -> list[Flag]:
    out = []
    panel = pd.read_csv(OUT / "panel_periode_a.csv")
    for r in panel.itertuples(index=False):
        bad_trend = pd.notna(r.absolute_cagr) and abs(r.absolute_cagr) > 1.0
        bad_base = pd.notna(r.base_year_ratio) and not (0.2 <= r.base_year_ratio <= 5.0)
        if not (bad_trend or bad_base):
            continue
        facs = c.attrib[c.attrib.ticker == r.ticker].groupby("year").facility_id.nunique().to_dict()
        out.append(Flag("F07_trend_basis_instabil", "fehler", r.ticker, "absolute_cagr", int(r.year_last),
                        float(r.absolute_cagr) if pd.notna(r.absolute_cagr) else None,
                        "Trend oder Basisjahr-Quote unplausibel: Die Anlagenbasis ändert sich über die Jahre "
                        "(Zuordnung, Abspaltung, Zukauf), nicht die Emissionen.",
                        ranking_relevant=r.ticker in c.ranked,
                        evidence={"absolute_cagr": r.absolute_cagr, "base_year_ratio": r.base_year_ratio,
                                  "scope1_je_jahr": c.series(r.ticker, "scope1_t"),
                                  "anlagen_je_jahr": {int(k): int(v) for k, v in facs.items()}}))
    return out


TEMPORAL = {
    # Schlüssel der Tochtertabelle: (Ticker, gültig ab Jahr, gültig bis Jahr, Begründung)
    "talen energy": ("VST", None, None, "Talen ist eigenständig, gehört nicht zu Vistra"),
    "westrock": ("SW", 2024, None, "Fusion zu Smurfit Westrock im Juli 2024"),
    "pioneer natural resources": ("XOM", 2024, None, "Übernahme durch ExxonMobil im Mai 2024"),
    "calpine": ("CEG", 2026, None, "Übernahme durch Constellation nach 2023"),
    "exelon generation": ("EXC", None, 2021, "seit Februar 2022 Constellation Energy"),
    "anadarko petroleum": ("OXY", 2019, None, "Übernahme durch Occidental im August 2019"),
}


def r_temporal(c: Context) -> list[Flag]:
    out = []
    a = c.attrib.copy()
    a["key"] = a.parent_company.astype(str).str.split(";").str[0].str.replace(r"\([^)]*\)", "", regex=True).map(normalize)
    for key, (t, start, end, why) in TEMPORAL.items():
        rows = a[a.key.str.startswith(key) & (a.ticker == t)]
        for yr, g in rows.groupby("year"):
            wrong = (start is None and end is None) or (start is not None and yr < start) or (end is not None and yr > end)
            if not wrong or g.att_t.sum() <= 0:
                continue
            out.append(Flag("F08_zuordnung_zeitlich", "fehler", t, "scope1_t", int(yr), float(g.att_t.sum()),
                            f"'{key}' ist {t} zugeordnet, gilt aber für {yr} nicht: {why}.",
                            impact_t=float(g.att_t.sum()), ranking_relevant=t in c.ranked,
                            evidence={"eigentuemer_roh": sorted(set(g.parent_company))[:3],
                                      "anlagen": int(g.facility_id.nunique())}))
    return out


def r_osha_denominator(c: Context) -> list[Flag]:
    out = []
    o = pd.read_parquet(RAW / "osha_ita.parquet")
    o["ticker"] = o.company_name.map(c.to_ticker)
    o = o.dropna(subset=["ticker"])
    o["hours"] = pd.to_numeric(o.total_hours_worked, errors="coerce")
    o["emp"] = pd.to_numeric(o.annual_average_employees, errors="coerce")
    o["hpe"] = o.hours / o.emp
    # Unbrauchbare Meldungen fliessen seit der Reparatur nicht mehr in die
    # Rate ein (05b_firmenaggregate.py). Geprüft wird der Rest.
    o = o[o.hpe.between(200, 4000)]
    genutzt = set(c.long[c.long.metric == "dart_rate"].ticker)
    for t, g in o.groupby("ticker"):
        if t not in genutzt:
            continue
        med = float(g.hpe.median())
        implaus = float(((g.hpe < 200) | (g.hpe > 4000)).mean())
        if not (med < 500 or med > 3500 or implaus > 0.3):
            continue
        dart = c.series(t, "dart_rate")
        out.append(Flag("F09_osha_nenner_unplausibel", "fehler", t, "dart_rate", 2025,
                        list(dart.values())[-1] if dart else None,
                        f"Unfallrate beruht auf unplausiblen Stunden: Median {med:,.0f} h je Beschäftigtem "
                        f"(normal rund 1.500-2.100), {implaus:.0%} der Meldungen außerhalb 200-4.000 h. OSHA prüft diese Angaben nicht.",
                        evidence={"meldungen": int(len(g)), "stunden_je_beschaeftigtem_median": med,
                                  "anteil_unplausibel": implaus, "firmennamen": g.company_name.value_counts().head(3).to_dict()}))
    return out


def r_whd(c: Context) -> list[Flag]:
    """Lohnverfahren, die über den Handelsnamen zugeordnet wurden.

    Die Verfahren tragen keine Firmenkennung. Ein Treffer über den
    *Rechtsnamen* ist belastbar; ein Treffer nur über den *Handelsnamen*
    kann ein Franchisebetrieb sein, der unter der Marke firmiert, aber
    eigenständiger Arbeitgeber ist (McDonald's: alle 64 Verfahren laufen
    über den Handelsnamen). Ob die Verfahren dem Konzern zuzurechnen sind,
    entscheidet die Franchise-Offenlegung -- ein Grenzfall für Menschen.
    Die frühere Regel prüfte die Team-Datei; deren Zahlen sind seit der
    eigenen Zuordnung aus den Rohdaten nicht mehr im Datensatz.
    """
    out = []
    w = pd.read_parquet(RAW / "dol_whd.parquet")
    w["t_legal"] = w.legal_name.map(c.to_ticker)
    w["t_trade"] = w.trade_nm.map(c.to_ticker)
    w["t"] = w.t_legal.fillna(w.t_trade)
    hit = w.dropna(subset=["t"])
    im_bestand = set(c.long[c.long.metric == "whd_cases"].ticker)
    for t, g in hit.groupby("t"):
        if t not in im_bestand:
            continue
        faelle = int(g.case_id.nunique())
        nur_handel = int(g.t_legal.isna().sum())
        anteil = nur_handel / max(len(g), 1)
        if faelle < 5 or anteil < 0.5:
            continue
        out.append(Flag("F10_whd_franchise", "pruefen", t, "whd_cases", 2024, float(faelle),
                        f"{faelle} Verfahren, davon {nur_handel} nur über den Handelsnamen zugeordnet "
                        f"({anteil:.0%}). Franchisebetriebe sind eigene Arbeitgeber -- ohne "
                        "Franchise-Offenlegung nicht entscheidbar.",
                        evidence={"faelle": faelle, "nur_handelsname": nur_handel,
                                  "rechtsnamen": g.legal_name.value_counts().head(4).to_dict(),
                                  "handelsnamen": g.trade_nm.value_counts().head(4).to_dict(),
                                  "nachzahlung_usd": float(g.bw_atp_amt.fillna(0).sum())}))
    return out


def r_sbti(c: Context) -> list[Flag]:
    out = []
    val = c.long[c.long.metric == "sbti_validated"].set_index("ticker").value
    rem = c.long[c.long.metric == "sbti_commitment_removed"].set_index("ticker").value
    for t in set(val.index) & set(rem.index):
        if val[t] == 1 and rem[t] == 1:
            out.append(Flag("F12_sbti_zieltyp", "fehler", t, "sbti_commitment_removed", CURRENT_YEAR, 1.0,
                            "Validiert und zurückgezogen zugleich: Die Status gehören zu verschiedenen Zieltypen "
                            "(Nahziel gesetzt, Netto-null-Zusage zurückgezogen). Die Kennzahl vermischt beides.",
                            evidence={"regel": "Commitment removed = Ziel nicht binnen 24 Monaten eingereicht"}))
    # Abgelaufene Nahziele sind seit der Reparatur eine eigene Kennzahl
    # (sbti_near_term_expired) und gelten nicht mehr als geprüftes Ziel --
    # deshalb hier keine Flag mehr.
    return out


def r_extremes(c: Context) -> list[Flag]:
    """Robuster Z-Wert je Branche. Nur Prüfhinweis -- echte Extreme gibt es."""
    out = []
    latest = c.long.sort_values("year").groupby(["ticker", "metric"]).last().reset_index()
    for m in ["co2_intensity", "tri_releases_lbs", "dart_rate", "echo_penalties_usd", "whd_backwages_usd"]:
        s = latest[latest.metric == m]
        for sector, g in s.groupby("gics_sector"):
            v = g.value[g.value > 0]
            if len(v) < 6:
                continue
            lv = np.log10(v)
            med, mad = lv.median(), (lv - lv.median()).abs().median() or 1e-9
            z = (lv - med) / (1.4826 * mad)
            for idx in z[z > 3.5].index:
                r = g.loc[idx]
                out.append(Flag("P01_branchenextrem", "pruefen", r.ticker, m, int(r.year), float(r.value),
                                f"Im Branchenvergleich extrem (robuster z-Wert {z[idx]:.1f} auf log-Skala). Kann real sein.",
                                ranking_relevant=r.ticker in c.ranked and m in CORE_METRICS,
                                evidence={**c.sector_stats(r.ticker, m), "zeitreihe": c.series(r.ticker, m)}))
    return out


def r_wide_bands(c: Context) -> list[Flag]:
    """Breite Bänder ohne Aussage -- geprüft wird, was im Datensatz steht.

    ``consolidate.py`` zeigt ab 70 Perzentilpunkten keinen Median mehr.
    """
    out = []
    gezeigt = set(c.long[c.long.metric == "rank_p50"].ticker)
    breit = c.bands[(c.bands.band_width >= 70) & c.bands.ticker.isin(gezeigt)]
    for r in breit.itertuples(index=False):
        out.append(Flag("P02_rangband_ohne_aussage", "pruefen", r.ticker, "rank_p50", 2023, float(r.p50),
                        f"Rangband {r.p10:.0f}-{r.p90:.0f}: Der Median suggeriert eine Einordnung, die es nicht gibt.",
                        ranking_relevant=True, evidence={"p10": r.p10, "p90": r.p90}))
    return out


RULES = [r_duplicate_cik, r_zero_emissions, r_campd_program, r_echo_quarters, r_egrid, r_trend_base,
         r_temporal, r_osha_denominator, r_whd, r_sbti, r_extremes, r_wide_bands]


def run() -> pd.DataFrame:
    c = Context()
    flags: list[Flag] = []
    for rule in RULES:
        got = rule(c)
        print(f"  {rule.__name__:24s} {len(got):4d}")
        flags.extend(got)
    df = pd.DataFrame([asdict(f) for f in flags])
    df.insert(0, "flag_id", [f"Q{i:04d}" for i in range(1, len(df) + 1)])
    df["company"] = df.ticker.map(c.names.company)
    df["gics_sector"] = df.ticker.map(c.names.gics_sector)
    df["evidence"] = df.evidence.map(lambda e: json.dumps(e, ensure_ascii=False, default=str))
    return df


def packet(row: pd.Series) -> dict:
    """Belegpaket für die KI-Prüfung. Enthält nur, was aus den Daten stammt."""
    return {
        "fall": f"Regel {row['rule']} ({row['severity']}): {row['message']}",
        "firma": {"ticker": row["ticker"], "name": row.get("company"), "branche": row.get("gics_sector")},
        "kennzahl": {"id": row["metric"], "jahr": row["year"], "wert": row["value"]},
        "belege": json.loads(row["evidence"]),
        "aufgabe": "Beurteile, ob die Regel recht hat und welche Ursache die Belege stützen.",
    }
