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

# Referenzmenge: Fälle, deren richtige Einordnung aus den Rohdaten belegt ist.
# Schlüssel (Regel, Ticker, Kennzahl, Jahr oder None) -> (erwartetes Urteil, erwartete Ursache, Beleg)
GOLD = {
    ("F04_echo_quartale_unmoeglich", "TSLA", "echo_nc_quarters_per_site", None):
        ("fehler", "doppelzaehlung", "1 Anlage, Historie SSSSSSSSSSSS, 2 Join-Zeilen durch 2 Namensschreibweisen"),
    ("F05_egrid_physik", "GE", "t_co2_pro_mwh", None):
        ("fehler", "definition_oder_einheit", "4,44 t/MWh, ein Heizkraftwerk, physikalisch unmöglich als Stromrate"),
    ("F10_whd_zuordnung", "APD", "whd_cases", None):
        ("fehler", "zuordnung_falsch", "0 Rohfälle für Air Products, 15 Fälle 'APDC Cleaning Services'"),
    ("F09_osha_nenner_unplausibel", "MCD", "dart_rate", None):
        ("fehler", "meldefehler_quelle", "4 Meldungen, Median 50 h je Beschäftigtem"),
    ("F02_null_statt_fehlend", "KHC", "scope1_t", 2022):
        ("fehler", "null_statt_fehlend", "4 Anlagen gemeldet, keine Emissionszeile mit Menge"),
    ("F03_campd_programm_ohne_co2", "MPC", "campd_co2_t", 2023):
        ("fehler", "programm_misst_groesse_nicht", "Programm SIPNOX, CO2 nicht meldepflichtig"),
    ("F07_trend_basis_instabil", "PPL", "absolute_cagr", None):
        ("fehler", "zuordnung_falsch", "2018 1 Anlage 5 kt, ab 2019 9 Anlagen 28 Mt"),
    ("F08_zuordnung_zeitlich", "VST", "scope1_t", 2023):
        ("fehler", "zuordnung_falsch", "Talen Energy ist nicht Teil von Vistra"),
    ("F01_doppelte_cik", "GOOGL", "*", None):
        ("fehler", "doppelzaehlung", "GOOG und GOOGL teilen CIK 1652044"),
    ("F06_egrid_nicht_versorger", "BRK-B", "t_co2_pro_mwh", None):
        ("plausibel", "branchenstruktur_real", "Berkshire Hathaway Energy betreibt echte Versorger; nur GICS sagt Financials"),
}


def gold_key(row: pd.Series):
    for (rule, t, m, y), val in GOLD.items():
        if row["rule"] == rule and row["ticker"] == t and row["metric"] == m and (y is None or row["year"] == y):
            return (rule, t, m, y)
    return None


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
    ref = ki.get("referenz", {})
    routes = ki.get("routen", {})
    verdicts = ki.get("urteile", {})
    macros = {
        "statFlags": de(summary["flags"]), "statFehler": de(summary["fehler"]),
        "statPruefen": de(summary["pruefen"]), "statFirmenBetr": de(summary["firmen_betroffen"]),
        "statRankRel": de(summary["ranking_relevant"]),
        "kiModell": esc(ki.get("modell", "--")), "kiEskModell": esc(ki.get("eskalation", "--")),
        "kiBestaetigt": de(ki.get("regel_bestaetigt_fehler", 0)),
        "kiWiderspricht": de(ki.get("regel_widersprochen_fehler", 0)),
        "kiAuto": de(routes.get("automatisch", 0)), "kiMensch": de(routes.get("mensch", 0)),
        "kiEskaliert": de(ki.get("eskaliert", 0)), "kiTokens": de(ki.get("tokens_gesamt", 0)),
        "kiUrteilFehler": de(verdicts.get("fehler", 0)), "kiUrteilPlausibel": de(verdicts.get("plausibel", 0)),
        "kiUrteilUnklar": de(verdicts.get("unklar", 0)),
        "refN": de(ref.get("faelle", 0)), "refUrteil": de(ref.get("urteil_richtig", 0)),
        "refUrsache": de(ref.get("ursache_richtig", 0)),
    }
    v1 = ROOT / "data" / "out" / "flags_gepruft_v1.csv"
    if "ai_verdict" not in flags and (OUT / "flags_gepruft.csv").exists():
        flags = pd.read_csv(OUT / "flags_gepruft.csv")
    if v1.exists() and "ai_verdict" in flags:
        a = pd.read_csv(v1)
        contra1 = a[(a.severity == "fehler") & (a.ai_verdict == "plausibel")]
        auto1 = contra1[contra1.route == "automatisch"]
        contra2 = flags[(flags.severity == "fehler") & (flags.ai_verdict == "plausibel")]
        auto2 = contra2[contra2.route == "automatisch"]
        r1 = pd.read_csv(ROOT / "data" / "out" / "ki_bewertung_referenz_v1.csv")
        macros.update({
            "vEinsWiderspruch": de(len(contra1)), "vEinsAutoFrei": de(len(auto1)),
            "vZweiWiderspruch": de(len(contra2)), "vZweiAutoFrei": de(len(auto2)),
            "vEinsRefUrteil": de(r1.urteil_richtig.sum()), "vEinsRefUrsache": de(r1.ursache_richtig.sum()),
            "vEinsFehler": de((a.ai_verdict == "fehler").sum()), "vEinsPlausibel": de((a.ai_verdict == "plausibel").sum()),
            "vEinsUnklar": de((a.ai_verdict == "unklar").sum()),
        })
    (gen / "pruefung_stats.tex").write_text(
        "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()) + "\n", encoding="utf-8")

    rows = []
    for rule, g in flags.groupby("rule"):
        sev = g.severity.iloc[0]
        ex = ", ".join(sorted(g.ticker.unique())[:6])
        rows.append((rule, sev, len(g), g.ticker.nunique(), ex))
    lines = ["\\texttt{%s} & %s & %s & %d & %d & %s \\\\" % (
        esc(r.split("_")[0]), esc(RULE_TEXT.get(r, r)), sev, n, f, esc(ex)) for r, sev, n, f, ex in rows]
    (gen / "tab_flags_regel.tex").write_text("\n".join(lines) + "\n\\bottomrule%", encoding="utf-8")

    lines = []
    for r in summary.get("referenz_faelle", []):
        ok = lambda b: "ja" if b else "\\textbf{nein}"
        lines.append("%s & %s & %s & %s & %s & %.2f & %s \\\\" % (
            esc(r["ticker"]), esc(r["beleg"]), esc(r["erwartet"]), f"{esc(r['ki_urteil'])} ({ok(r['urteil_richtig'])})",
            f"{esc(r['ki_ursache'])} ({ok(r['ursache_richtig'])})", float(r["konfidenz"]), esc(r["route"])))
    (gen / "tab_referenz.tex").write_text(("\n".join(lines) if lines else "-- & -- & -- & -- & -- & 0 & -- \\\\") + "\n\\bottomrule%", encoding="utf-8")


def main(use_ai: bool) -> None:
    print("Regeln:")
    flags = Q.run()
    flags.to_csv(OUT / "flags.csv", index=False)
    summary: dict = {
        "flags": len(flags),
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
        reviewed["gold"] = reviewed.apply(gold_key, axis=1)

        # ---- Bewertung an der Referenzmenge
        g = reviewed.dropna(subset=["gold"]).drop_duplicates("gold")
        rows = []
        for _, r in g.iterrows():
            exp_verdict, exp_cause, beleg = GOLD[r["gold"]]
            rows.append({"regel": r["rule"], "ticker": r["ticker"], "erwartet": exp_verdict,
                         "ki_urteil": r["ai_verdict"], "urteil_richtig": r["ai_verdict"] == exp_verdict,
                         "erwartete_ursache": exp_cause, "ki_ursache": r["ai_cause"],
                         "ursache_richtig": r["ai_cause"] == exp_cause, "konfidenz": r["ai_confidence"],
                         "route": r["route"], "beleg": beleg})
        eval_df = pd.DataFrame(rows)
        eval_df.to_csv(OUT / "ki_bewertung_referenz.csv", index=False)
        summary["referenz_faelle"] = eval_df.to_dict("records")

        # ---- menschliche Entscheidungen haben Vorrang
        if DECISIONS.exists():
            dec = pd.read_csv(DECISIONS)
            reviewed = reviewed.merge(dec[["flag_id", "entscheidung", "person", "begruendung"]],
                                      on="flag_id", how="left")
        reviewed["final"] = reviewed.get("entscheidung", pd.Series(index=reviewed.index)).fillna(
            reviewed.apply(lambda r: r["ai_action"] if r["route"] == "automatisch" else "offen", axis=1))
        reviewed.drop(columns=["gold"]).to_csv(OUT / "flags_gepruft.csv", index=False)
        # Für die Oberfläche: Belege als Objekt statt als Zeichenkette.
        recs = reviewed.drop(columns=["gold"]).assign(evidence=reviewed.evidence.map(json.loads))
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
            "referenz": {
                "faelle": int(len(eval_df)),
                "urteil_richtig": int(eval_df.urteil_richtig.sum()) if len(eval_df) else 0,
                "ursache_richtig": int(eval_df.ursache_richtig.sum()) if len(eval_df) else 0,
            },
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
