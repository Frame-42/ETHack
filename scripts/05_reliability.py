"""Assess evidence availability by company and pillar and export the results and summary distributions."""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from pipeline import reliability as R
from pipeline.universe import primary_master
from pipeline.config import OUT, RAW, ROOT


def json_safe(x):
    """Recursively replace non-finite numbers with None for valid JSON."""
    if isinstance(x, dict):
        return {k: json_safe(v) for k, v in x.items()}
    if isinstance(x, list):
        return [json_safe(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def main() -> None:
    long = pd.read_csv(OUT / "dataset_long.csv")
    master = primary_master()
    df = R.assess(long, master)
    df.to_csv(OUT / "reliability.csv", index=False)

    total = len(df)
    # Distribution of metrics per company.
    value_hist = Counter(df["n_values"])
    values = [{"n": n, "companies": value_hist.get(n, 0)} for n in range(0, int(df["n_values"].max()) + 1)]

    # Pillar summaries.
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

    # Combined evidence across pillars.
    all3 = df[df["n_reliable"] == 3]
    sector_rows = []
    for sector, g in df.groupby("gics_sector"):
        a = g[g["n_reliable"] == 3]
        sector_rows.append({
            "sector": sector,
            "companies": len(g),
            **{p: int((g[f"{p}_level"] == "strong").sum()) for p in R.PILLARS},
            "all3": len(a),
            "rankable": len(a) if len(a) >= R.MIN_PEERS else 0,
        })
    sectors = pd.DataFrame(sector_rows).sort_values("all3", ascending=False)
    rankable_sectors = set(sectors.loc[sectors["rankable"] > 0, "sector"])
    in_peer = all3[all3["gics_sector"].isin(rankable_sectors)]
    narrow = in_peer[in_peer["e_band_width"].notna() & (in_peer["e_band_width"] <= R.NARROW_BAND)]

    combos = Counter(
        "".join(p if lv == "strong" else "·" for p, lv in zip(R.PILLARS, row))
        for row in df[[f"{p}_level" for p in R.PILLARS]].itertuples(index=False)
    )

    funnel = [
        {"label": "Index members", "companies": total},
        {"label": "With at least one observation", "companies": int((df["n_values"] > 0).sum())},
        {"label": "Strong evidence in at least one pillar", "companies": int((df["n_reliable"] >= 1).sum())},
        {"label": "Strong evidence in at least two pillars", "companies": int((df["n_reliable"] >= 2).sum())},
        {"label": "Strong evidence in all three pillars", "companies": len(all3)},
        {"label": f"... and in a sector with at least {R.MIN_PEERS} such companies", "companies": len(in_peer)},
        {"label": f"... and climate band at most {R.NARROW_BAND:.0f} percentile points wide", "companies": len(narrow)},
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
    (OUT / "reliability.json").write_text(
        # JSON must use null for non-finite values.
        json.dumps(json_safe(payload), indent=2, ensure_ascii=False, default=lambda x: None),
        encoding="utf-8",
    )

    print(f"Metrics per company: median {payload['valuesMedian']:.0f}")
    for p in pillars:
        print(f"{p['id']}: " + " | ".join(f"{k} {v}" for k, v in p["levels"].items()))
    for f in funnel:
        print(f"  {f['companies']:4d}  {f['label']}")
    print("Patterns:", payload["combos"][:6])


if __name__ == "__main__":
    main()
