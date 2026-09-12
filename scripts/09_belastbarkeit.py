"""Bewertet, wie belastbar die Daten je Firma und Bereich sind.

Schreibt:
  data/out/belastbarkeit.csv            eine Zeile je Firma
  data/out/belastbarkeit.json           Kennzahlen und Verteilungen für den Browser
  report/generated/tab_belastbarkeit.tex   Gewichtstabelle für den Katalog
und kopiert beides in die Web-App (public/data und public/downloads).
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from pipeline import reliability as R
from pipeline.config import OUT, RAW, REPORT, ROOT


def tex(s: str) -> str:
    for a, b in {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "≥": r"$\geq$"}.items():
        s = s.replace(a, b)
    return s


def sauber(x):
    """NaN und Inf durch None ersetzen, rekursiv."""
    if isinstance(x, dict):
        return {k: sauber(v) for k, v in x.items()}
    if isinstance(x, list):
        return [sauber(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def main() -> None:
    long = pd.read_parquet(OUT / "dataset_long.parquet")
    master = pd.read_parquet(RAW / "sp500_master.parquet")
    df = R.assess(long, master)
    df.to_csv(OUT / "belastbarkeit.csv", index=False)

    total = len(df)
    # ------------------------------------------------ Verteilung Werte je Firma
    value_hist = Counter(df["n_values"])
    values = [{"n": n, "companies": value_hist.get(n, 0)} for n in range(0, int(df["n_values"].max()) + 1)]

    # ------------------------------------------------------------ je Bereich
    pillars = []
    for p, name in R.PILLARS.items():
        mx = R.max_score(p)
        bins = [round(x * 0.25, 2) for x in range(0, int(mx / 0.25) + 2)]
        score_hist = []
        for lo in bins:
            hi = lo + 0.25
            n = int(((df[f"{p}_score"] >= lo) & (df[f"{p}_score"] < hi)).sum())
            score_hist.append({"from": lo, "to": round(hi, 2), "companies": n})
        fam_def: dict[str, dict] = {}
        for mid, e in R.METRIC_EVIDENCE.items():
            if e.pillar != p:
                continue
            f = fam_def.setdefault(e.family, {"id": e.family, "label": e.family_label, "weight": 0.0, "metrics": []})
            f["weight"] = max(f["weight"], e.weight)
            f["metrics"].append({"id": mid, "weight": e.weight, "evidence": e.evidence})
        fam_counts = Counter(x for s in df[f"{p}_family_list"] for x in s.split(", ") if x)
        for f in fam_def.values():
            f["companies"] = int(fam_counts.get(f["id"], 0))
        pillars.append({
            "id": p,
            "name": name,
            "maxScore": mx,
            "levels": {lv: int((df[f"{p}_level"] == lv).sum()) for lv in R.LEVELS},
            "scoreHist": score_hist,
            "families": sorted(fam_def.values(), key=lambda f: -f["weight"]),
        })

    # --------------------------------------------------- alle drei zusammen
    all3 = df[df["n_reliable"] == 3]
    sector_rows = []
    for sector, g in df.groupby("gics_sector"):
        a = g[g["n_reliable"] == 3]
        sector_rows.append({
            "sector": sector,
            "companies": len(g),
            **{p: int((g[f"{p}_level"] == "belastbar").sum()) for p in R.PILLARS},
            "all3": len(a),
            "rankable": len(a) if len(a) >= R.MIN_PEERS else 0,
        })
    sectors = pd.DataFrame(sector_rows).sort_values("all3", ascending=False)
    rankable_sectors = set(sectors.loc[sectors["rankable"] > 0, "sector"])
    in_peer = all3[all3["gics_sector"].isin(rankable_sectors)]
    narrow = in_peer[in_peer["e_band_width"].notna() & (in_peer["e_band_width"] <= R.NARROW_BAND)]

    combos = Counter(
        "".join(p if lv == "belastbar" else "·" for p, lv in zip(R.PILLARS, row))
        for row in df[[f"{p}_level" for p in R.PILLARS]].itertuples(index=False)
    )

    funnel = [
        {"label": "Indexmitglieder", "companies": total},
        {"label": "mit mindestens einem Wert", "companies": int((df["n_values"] > 0).sum())},
        {"label": "in mindestens einem Bereich belastbar", "companies": int((df["n_reliable"] >= 1).sum())},
        {"label": "in mindestens zwei Bereichen belastbar", "companies": int((df["n_reliable"] >= 2).sum())},
        {"label": "in allen drei Bereichen belastbar", "companies": len(all3)},
        {"label": f"… und in einer Branche mit mindestens {R.MIN_PEERS} solchen Firmen", "companies": len(in_peer)},
        {"label": f"… und Umwelt-Rangband höchstens {R.NARROW_BAND:.0f} Perzentilpunkte breit", "companies": len(narrow)},
    ]

    payload = {
        "total": total,
        "rules": {
            "anchorWeight": R.ANCHOR_WEIGHT,
            "minFamilies": R.MIN_FAMILIES,
            "minScore": R.MIN_SCORE,
            "partialScore": R.PARTIAL_SCORE,
            "minPeers": R.MIN_PEERS,
            "narrowBand": R.NARROW_BAND,
            "levels": R.LEVEL_RULES,
        },
        "values": values,
        "valuesMedian": float(df["n_values"].median()),
        "pillars": pillars,
        "combos": [{"pattern": k, "companies": v} for k, v in sorted(combos.items(), key=lambda x: -x[1])],
        "sectors": sectors.to_dict("records"),
        "funnel": funnel,
        "rankableList": in_peer.sort_values(["gics_sector", "company"])[
            ["ticker", "company", "gics_sector", "E_score", "S_score", "G_score", "e_band_width"]
        ].to_dict("records"),
    }
    (OUT / "belastbarkeit.json").write_text(
        # NaN ist in JSON kein gueltiger Wert -- der Browser bricht daran ab.
        json.dumps(sauber(payload), indent=2, ensure_ascii=False, default=lambda x: None),
        encoding="utf-8",
    )

    # --------------------------------------------------- Katalog-Tabelle
    lines = []
    for p in pillars:
        lines.append(r"\textbf{%s -- %s} & & & \\" % (p["id"], tex(p["name"])))
        for f in p["families"]:
            ev = "; ".join(sorted({m["evidence"] for m in f["metrics"]}))
            lines.append("\\quad %s & %s & %d & %s \\\\" % (
                tex(f["label"]), f"{f['weight']:.1f}".replace(".", "{,}"), f["companies"], tex(ev)))
    (REPORT / "generated" / "tab_belastbarkeit.tex").write_text("\n".join(lines) + "\n\\bottomrule%", encoding="utf-8")

    # --------------------------------------------------- in die Web-App
    web = ROOT / "web" / "public"
    for sub in ("data", "downloads"):
        (web / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT / "belastbarkeit.json", web / "data" / "belastbarkeit.json")
    shutil.copy2(OUT / "belastbarkeit.csv", web / "downloads" / "belastbarkeit.csv")

    print(f"Werte je Firma: Median {payload['valuesMedian']:.0f}")
    for p in pillars:
        print(f"{p['id']}: " + " | ".join(f"{k} {v}" for k, v in p["levels"].items()))
    for f in funnel:
        print(f"  {f['companies']:4d}  {f['label']}")
    print("Muster:", payload["combos"][:6])


if __name__ == "__main__":
    main()
