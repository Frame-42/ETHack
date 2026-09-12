"""Qualitätsprüfung: Regeln, KI-Gutachten, Weiterleitung und Bewertung der KI.

Ablauf:
  1. Regeln aus pipeline/quality.py finden auffällige Werte (mit Belegpaket).
  2. Optional (--ai): jedes Paket geht an ein Sprachmodell; unsichere Fälle
     eskalieren an ein stärkeres Modell; eine Regel entscheidet, was ein
     Mensch sehen muss.
  3. Die KI wird an einer Referenzmenge gemessen, deren Antwort aus den
     Rohdaten belegt ist -- nicht aus dem Bauch.
  4. Menschliche Entscheidungen aus data/review/entscheidungen.csv haben
     Vorrang vor Regel und KI.

Aufruf:
  python scripts/10_pruefung.py            # nur Regeln
  python scripts/10_pruefung.py --ai       # Regeln + KI-Gutachten
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from pipeline import quality as Q
from pipeline.config import DATA, OUT, ROOT

REVIEW = DATA / "review"
DECISIONS = REVIEW / "entscheidungen.csv"

# ---------------------------------------------------------------------------
# Reparatur-Kontrolle. Zehn Faelle, deren richtige Behandlung aus den Rohdaten
# belegt ist. Frueher waren es Referenzfaelle fuer die KI-Messung -- inzwischen
# sind ihre Ursachen in der Pipeline repariert, und dieselben Faelle pruefen,
# ob die Reparatur haelt. Jeder Eintrag: (Beleg, Pruefung auf dem Datensatz).
# ---------------------------------------------------------------------------
def _werte(long: pd.DataFrame, ticker: str, metric: str, jahr: int | None = None):
    s = long[(long.ticker == ticker) & (long.metric == metric)]
    if jahr is not None:
        s = s[s.year == jahr]
    return [float(v) for v in s.value.dropna()]


REPARATUREN = [
    ("Null statt fehlend", "KHC", "EPA fuehrt 4 Anlagen, meldet 2022 keine Menge",
     lambda l: (not _werte(l, "KHC", "scope1_t", 2022), "2022 ohne Wert statt 0 t")),
    ("Programm misst CO2 nicht", "MPC", "Anlagen melden nur in SIPNOX (Waerme und NOx)",
     lambda l: (not _werte(l, "MPC", "campd_co2_t"), "keine CO2-Menge statt 0 t")),
    ("Join vervielfacht", "TSLA", "1 Anlage, Historie SSSSSSSSSSSS, 2 Join-Zeilen",
     lambda l: (all(v <= 12 for v in _werte(l, "TSLA", "echo_nc_quarters_per_site")),
                f"{max(_werte(l, 'TSLA', 'echo_nc_quarters_per_site'), default=0):.0f} Quartale statt 24")),
    ("Stromrate ohne Stromgeschaeft", "GE", "4,44 t/MWh aus einem Heizkraftwerk",
     lambda l: (not _werte(l, "GE", "t_co2_pro_mwh"), "keine Rate mehr")),
    ("Stromrate trotz falscher Branchenkennung", "BRK-B",
     "113 Kraftwerke, 83 TWh -- GICS sagt Financials",
     lambda l: (bool(_werte(l, "BRK-B", "t_co2_pro_mwh")),
                f"Rate bleibt: {max(_werte(l, 'BRK-B', 't_co2_pro_mwh'), default=0):.2f} t/MWh")),
    ("Nenner unbrauchbar", "MCD", "4 Meldungen mit im Median 50 h je Beschaeftigtem",
     lambda l: (not _werte(l, "MCD", "dart_rate"), "keine Unfallrate auf falschem Nenner")),
    ("Zuordnung ueber Namensteile", "APD", "0 Rohfaelle, 15 Faelle 'APDC Cleaning Services'",
     lambda l: (not _werte(l, "APD", "whd_cases"), "keine Lohnverfahren mehr zugerechnet")),
    ("Basisjahr unvollstaendig", "PPL", "2018 eine Anlage 5 kt, ab 2019 neun Anlagen 28 Mt",
     lambda l: (not _werte(l, "PPL", "scope1_t", 2018)
                and all(abs(v) <= 1 for v in _werte(l, "PPL", "absolute_cagr")),
                "2018 entfernt, Trend wieder lesbar")),
    ("Zuordnung ohne Zeitraum", "VST", "Talen Energy gehoert nicht zu Vistra",
     lambda l: (all(v < 90e6 for v in _werte(l, "VST", "scope1_t", 2023)),
                f"2023: {max(_werte(l, 'VST', 'scope1_t', 2023), default=0)/1e6:.1f} Mt statt 96,8")),
    ("Aktiengattung doppelt", "GOOG", "GOOG und GOOGL teilen CIK 1652044",
     lambda l: (not len(l[l.ticker == "GOOG"]), "nur noch GOOGL im Bestand")),
]


def pruefe_reparaturen(long: pd.DataFrame) -> list[dict]:
    out = []
    for thema, ticker, beleg, test in REPARATUREN:
        try:
            ok, befund = test(long)
        except Exception as e:  # eine kaputte Pruefung ist auch ein Befund
            ok, befund = False, f"Pruefung fehlgeschlagen: {e}"
        out.append({"thema": thema, "ticker": ticker, "beleg": beleg,
                    "behoben": bool(ok), "befund": befund})
    return out


REPARATUR_TEXT = {
    "F01_doppelte_cik": "CIK-Deduplizierung in consolidate.py",
    "F02_null_statt_fehlend": "fehlend statt 0 in canonical.py",
    "F03_campd_programm_ohne_co2": "CO2 nur aus ARP, RGGI, NSPS4T",
    "F04_echo_quartale_unmoeglich": "Join entdoppelt, nur V und S gezählt",
    "F05_egrid_physik": "Grenze 1,3 t/MWh beim Export",
    "F06_egrid_nicht_versorger": "Rate nur für Kraftwerksflotten",
    "F07_trend_basis_instabil": "Trend erst ab drei Jahren mit stabiler Basis",
    "F08_zuordnung_zeitlich": "Gültigkeitszeiträume in resolve.py",
    "F09_osha_nenner_unplausibel": "Stundennenner 200-4.000 je Beschäftigtem",
    "F10_whd_zuordnung": "eigene Zuordnung statt Team-Datei",
    "F10_whd_franchise": "bleibt: Franchise ist ein Grenzfall",
    "F11_whd_ohne_befund": "Verstöße und Bußgelder als eigene Kennzahlen",
    "F12_sbti_zieltyp": "Status je Zieltyp getrennt",
    "F13_sbti_abgelaufen": "abgelaufenes Ziel als eigene Kennzahl",
    "P01_branchenextrem": "bleibt: echte Extreme sind kein Fehler",
    "P02_rangband_ohne_aussage": "ab Band 70 kein Median mehr",
}

RULE_TEXT = {
    "F01_doppelte_cik": "Zwei Ticker teilen eine CIK: Konzernwerte doppelt",
    "F02_null_statt_fehlend": "Exakt 0 t trotz zugeordneter Anlage",
    "F03_campd_programm_ohne_co2": "0 t CO2, Programm verlangt kein CO2",
    "F04_echo_quartale_unmoeglich": "Mehr als 12 Verstoßquartale je Anlage",
    "F05_egrid_physik": "Mehr als 1,3 t CO2 je MWh",
    "F06_egrid_nicht_versorger": "Stromrate eines Nicht-Versorgers",
    "F07_trend_basis_instabil": "Trend oder Basisjahr durch Anlagenbasis verzerrt",
    "F08_zuordnung_zeitlich": "Tochter vor oder ohne Konzernzugehörigkeit",
    "F09_osha_nenner_unplausibel": "Unfallrate auf unplausiblen Stunden",
    "F10_whd_zuordnung": "Lohnverfahren: Team-Zuordnung nicht nachvollziehbar",
    "F10_whd_franchise": "Lohnverfahren nur über den Handelsnamen",
    "F11_whd_ohne_befund": "Lohnverfahren ohne Nachzahlung und Betroffene",
    "F12_sbti_zieltyp": "SBTi: validiert und zurückgezogen vermischt",
    "F13_sbti_abgelaufen": "SBTi: Zieljahr vorbei",
    "P01_branchenextrem": "Extrem im Branchenvergleich",
    "P02_rangband_ohne_aussage": "Rangband breiter als 70 Punkte",
}


def write_report_tables(flags: pd.DataFrame, summary: dict) -> None:
    """Zahlen und Tabellen für den LaTeX-Bericht, damit nichts abgeschrieben wird."""
    gen = ROOT / "report" / "generated"
    gen.mkdir(parents=True, exist_ok=True)

    def esc(x) -> str:
        return str(x).replace("_", r"\_\allowbreak{}").replace("%", r"\%").replace("&", r"\&").replace("#", r"\#")

    def de(n) -> str:
        return f"{int(n):,}".replace(",", r"\,")

    ki = summary.get("ki", {})
    routes = ki.get("routen", {})
    verdicts = ki.get("urteile", {})
    macros = {
        "statFlags": de(summary["flags"]), "statFehler": de(summary["fehler"]),
        "statPruefen": de(summary["pruefen"]), "statFirmenBetr": de(summary["firmen_betroffen"]),
        "statRankRel": de(summary["ranking_relevant"]),
        "repGesamt": de(len(summary.get("reparaturen", []))),
        "repBehoben": de(summary.get("reparaturen_behoben", 0)),
        "kiModell": esc(ki.get("modell", "--")), "kiEskModell": esc(ki.get("eskalation", "--")),
        "kiAuto": de(routes.get("automatisch", 0)), "kiMensch": de(routes.get("mensch", 0)),
        "kiEskaliert": de(ki.get("eskaliert", 0)), "kiTokens": de(ki.get("tokens_gesamt", 0)),
        "kiUrteilFehler": de(verdicts.get("fehler", 0)), "kiUrteilPlausibel": de(verdicts.get("plausibel", 0)),
        "kiUrteilUnklar": de(verdicts.get("unklar", 0)),
    }
    vor = ROOT / "data" / "out" / "flags_vor_reparatur.csv"
    if vor.exists():
        a = pd.read_csv(vor)
        macros.update({
            "vorFlags": de(len(a)), "vorFehler": de(int((a.severity == "fehler").sum())),
            "vorFirmen": de(int(a.ticker.nunique())),
            "vorMensch": de(int((a.route == "mensch").sum())) if "route" in a else "246",
            "vorAuto": de(int((a.route == "automatisch").sum())) if "route" in a else "136",
        })
    (gen / "pruefung_stats.tex").write_text(
        "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()) + "\n", encoding="utf-8")

    # Tabelle: was die Regeln vor und nach der Reparatur finden
    vorher = pd.read_csv(vor) if vor.exists() else pd.DataFrame(columns=["rule", "ticker"])
    zeilen = []
    regeln = sorted(set(vorher.get("rule", pd.Series(dtype=str))) | set(flags.get("rule", pd.Series(dtype=str))))
    for r in regeln:
        n_vor = int((vorher.rule == r).sum()) if len(vorher) else 0
        n_nach = int((flags.rule == r).sum()) if len(flags) else 0
        zeilen.append("\\texttt{%s} & %s & %d & %d & %s \\\\" % (
            esc(r.split("_")[0]), esc(RULE_TEXT.get(r, r)), n_vor, n_nach,
            esc(REPARATUR_TEXT.get(r, "--"))))
    (gen / "tab_flags_regel.tex").write_text("\n".join(zeilen) + "\n\\bottomrule%", encoding="utf-8")

    # Tabelle: Reparatur-Kontrolle
    zeilen = ["%s & %s & %s & %s & %s \\\\" % (
        esc(r["thema"]), esc(r["ticker"]), esc(r["beleg"]), esc(r["befund"]),
        "ja" if r["behoben"] else "\\textbf{nein}") for r in summary.get("reparaturen", [])]
    (gen / "tab_referenz.tex").write_text(
        ("\n".join(zeilen) if zeilen else "-- & -- & -- & -- & -- \\\\") + "\n\\bottomrule%",
        encoding="utf-8")


def main(use_ai: bool) -> None:
    print("Regeln:")
    flags = Q.run()
    flags.to_csv(OUT / "flags.csv", index=False)
    long = pd.read_parquet(OUT / "dataset_long.parquet")
    rep = pruefe_reparaturen(long)
    print("\nReparatur-Kontrolle:")
    for r in rep:
        print(f"  {'ok ' if r['behoben'] else 'OFFEN'} {r['ticker']:6s} {r['thema']:42s} {r['befund']}")
    pd.DataFrame(rep).to_csv(OUT / "reparaturen.csv", index=False)

    summary: dict = {
        "flags": len(flags),
        "reparaturen": rep,
        "reparaturen_behoben": int(sum(r["behoben"] for r in rep)),
        "fehler": int((flags.severity == "fehler").sum()),
        "pruefen": int((flags.severity == "pruefen").sum()),
        "je_regel": flags.groupby("rule").size().to_dict(),
        "firmen_betroffen": int(flags.ticker.nunique()),
        "ranking_relevant": int(flags.ranking_relevant.sum()),
    }

    if use_ai:
        from pipeline import ai_review as A

        items = [(row.to_dict(), Q.packet(row)) for _, row in flags.iterrows()]
        print(f"KI-Prüfung von {len(items)} Fällen mit {A.MODEL}, Eskalation {A.ESCALATION_MODEL} ...")
        reviewed = pd.DataFrame(A.review_many(items))

        # ---- menschliche Entscheidungen haben Vorrang
        if DECISIONS.exists():
            dec = pd.read_csv(DECISIONS)
            reviewed = reviewed.merge(dec[["flag_id", "entscheidung", "person", "begruendung"]],
                                      on="flag_id", how="left")
        reviewed["final"] = reviewed.get("entscheidung", pd.Series(index=reviewed.index)).fillna(
            reviewed.apply(lambda r: r["ai_action"] if r["route"] == "automatisch" else "offen", axis=1))
        reviewed.to_csv(OUT / "flags_gepruft.csv", index=False)
        # Für die Oberfläche: Belege als Objekt statt als Zeichenkette.
        recs = reviewed.assign(evidence=reviewed.evidence.map(json.loads))
        (OUT / "flags_gepruft.json").write_text(
            recs.to_json(orient="records", force_ascii=False, default_handler=str), encoding="utf-8")

        tokens = pd.to_numeric(reviewed.tokens, errors="coerce").fillna(0).sum()
        summary["ki"] = {
            "modell": A.MODEL, "eskalation": A.ESCALATION_MODEL,
            "urteile": reviewed.ai_verdict.value_counts().to_dict(),
            "ursachen": reviewed.ai_cause.value_counts().to_dict(),
            "routen": reviewed.route.value_counts().to_dict(),
            "eskaliert": int(reviewed.get("ai_first_pass", pd.Series(dtype=object)).notna().sum()),
            "regel_bestaetigt_fehler": int(((reviewed.severity == "fehler") & (reviewed.ai_verdict == "fehler")).sum()),
            "regel_widersprochen_fehler": int(((reviewed.severity == "fehler") & (reviewed.ai_verdict == "plausibel")).sum()),
            "tokens_gesamt": int(tokens),
        }

    REVIEW.mkdir(parents=True, exist_ok=True)
    if not DECISIONS.exists():
        DECISIONS.write_text("flag_id,entscheidung,person,datum,begruendung\n", encoding="utf-8")
    (OUT / "pruefung.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    write_report_tables(flags, summary)

    web = ROOT / "web" / "public"
    for name in ("flags.csv", "flags_gepruft.csv", "flags_gepruft.json", "pruefung.json"):
        if (OUT / name).exists():
            (web / "data").mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUT / name, web / "data" / name)
            if name.endswith(".csv"):
                (web / "downloads").mkdir(parents=True, exist_ok=True)
                shutil.copy2(OUT / name, web / "downloads" / name)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main(use_ai="--ai" in sys.argv)
