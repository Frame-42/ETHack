"""Rebuild Dashboard 11's illustrative portfolios from its embedded company data.

The supplied optimizer was not included. This explicit reconstruction uses an
equal-weight benchmark, positive reported CO2 intensity, sector neutrality,
zero weight for at-risk firms, a 6% cap, and a 50% intensity reduction.
Minimize sum((w - benchmark)**2) - tilt * dot(w, axis_percentile / 100).
Missing axis scores receive a neutral 50; ALL averages available axes.
No prices or return covariance are available: te is Euclidean weight deviation.
Run without flags to validate; --write embeds rebuilt data using apply_patch.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard_v11.html"
DATA = re.compile(r'(<script id="data" type="application/json">)(.*?)(</script>)', re.S)
AXES = ("A", "S", "G", "B", "ALL")


def rebuild(data):
    firms = []
    intensities = []
    for firm in data["firms"]:
        intensity = next((row["value"] for row in firm["ledger"]
                          if row["metric"] == "co2_intensity"), None)
        if intensity is not None and np.isfinite(intensity) and intensity > 0:
            firms.append(firm)
            intensities.append(intensity)
    n = len(firms)
    carbon = np.array(intensities)
    benchmark = np.full(n, 1 / n)
    base = float(carbon @ benchmark)
    sectors = sorted({f["sector"] for f in firms})
    matrix = np.array([[f["sector"] == sector for f in firms]
                       for sector in sectors], dtype=float)
    excluded = np.array([f.get("viability", {}).get("level") == "at risk" for f in firms])
    bounds = [(0, 0 if flag else .06) for flag in excluded]
    constraints = [
        {"type": "eq", "fun": lambda w: matrix @ (w - benchmark), "jac": lambda w: matrix},
        {"type": "ineq", "fun": lambda w: .5 - carbon @ w / base,
         "jac": lambda w: -carbon / base},
    ]
    scores = {}
    for axis in AXES:
        values = []
        for firm in firms:
            available = [a["median"] for a in firm["axes"].values() if a is not None]
            value = (np.mean(available) if available else 50) if axis == "ALL" else (
                firm["axes"].get(axis) or {"median": 50})["median"]
            values.append(value / 100)
        scores[axis] = np.array(values)

    def solve(axis, tilt=.03):
        score = scores[axis]
        result = minimize(
            lambda w: np.sum((w - benchmark) ** 2) - tilt * (score @ w),
            benchmark, jac=lambda w: 2 * (w - benchmark) - tilt * score,
            method="SLSQP", bounds=bounds, constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )
        if not result.success:
            raise ValueError(f"{axis}, tilt {tilt}: {result.message}")
        weights = result.x
        weights[weights < 1e-10] = 0
        assert abs(weights.sum() - 1) < 1e-8
        assert weights.min() >= 0 and weights.max() <= .06 + 1e-8
        assert np.max(np.abs(matrix @ (weights - benchmark))) < 1e-8
        assert carbon @ weights <= base * .5 + 1e-6
        assert np.all(weights[excluded] == 0)
        return weights

    weights = {axis: solve(axis) for axis in AXES}
    result = {"universe": n}
    for axis, w in weights.items():
        positions = []
        for i in np.argsort(-w, kind="stable"):
            if w[i] == 0:
                continue
            firm = firms[i]
            sector_median = float(np.median(carbon[matrix[sectors.index(firm["sector"])] == 1]))
            positions.append({
                "ticker": firm["ticker"], "name": firm["name"], "sector": firm["sector"],
                "gewicht": float(w[i]), "benchmark": float(benchmark[i]),
                "intensitaet": float(carbon[i]), "sec_med": sector_median,
                "rel": float(np.log10(carbon[i] / sector_median)),
                "delta": float(w[i] - benchmark[i]),
                "tragfaehigkeit": firm.get("viability", {}).get("level", "not scorable"),
            })
        new = float(carbon @ w)
        result[axis] = {
            "axis": axis, "base": base, "new": new, "red": 1 - new / base,
            "te": float(np.linalg.norm(w - benchmark)), "sector_ok": True,
            "titles": len(positions), "maxw": float(w.max()), "excluded": int(excluded.sum()),
            "positions": positions,
            "sector_alloc": [{"sector": sector, "w": float(mask @ w),
                              "b": float(mask @ benchmark), "n": int(np.sum((w > 0) & (mask == 1)))}
                             for sector, mask in zip(sectors, matrix)],
        }
    overlap = lambda a, b: float(np.minimum(a, b).sum())
    result["overlap"] = {a: {b: overlap(weights[a], weights[b]) for b in AXES} for a in AXES}
    result["tilt_sensitivity"] = []
    for tilt in (0, .03, .1, .3, 1, 3):
        a, g = solve("A", tilt), solve("G", tilt)
        result["tilt_sensitivity"].append({"tilt": tilt, "te": float(np.linalg.norm(a - benchmark)),
                                            "overlap_AG": overlap(a, g)})
    pairs = [overlap(weights[a], weights[b]) for i, a in enumerate(AXES) for b in AXES[i + 1:]]
    result["finding"] = (f"With a tilt strength of 0.03, the rebuilt portfolios overlap by "
                         f"{min(pairs):.0%} to {max(pairs):.0%}. All use the same sector weights, "
                         "6% company cap and 50% intensity reduction. The selected axis changes "
                         "which companies are held and their weights within each sector.")
    start = int(data["generated"][:4])
    result["path"] = [{"year": start + i, "pab": round(result["ALL"]["new"] * .93 ** i, 1),
                       "bench": base} for i in range(16)]
    result["reconstruction"] = {
        "version": 1, "tilt": .03,
        "note": "Rebuilt illustration using the saved company scores. Equal-weight benchmark; "
                "50% lower Scope-1 intensity; sector-neutral weights; 6% company cap; "
                "at-risk companies excluded. Tilt strength: 0.03. Missing axis scores use 50; "
                "all four averages available axes. Active risk measures weight deviation, not return risk.",
        "objective": "sum((weight - benchmark)^2) - 0.03 * sum(weight * axis_percentile / 100)",
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    html = DASHBOARD.read_text()
    match = DATA.search(html)
    data = json.loads(match[2])
    portfolio = rebuild(data)
    for axis in AXES:
        p = portfolio[axis]
        print(f"{axis}: {p['titles']} holdings, {p['red']:.2%} intensity reduction, max weight {p['maxw']:.2%}")
    if args.write:
        data["portfolio"] = portfolio
        new_line = match[1] + json.dumps(data, ensure_ascii=False) + match[3]
        patch = ("*** Begin Patch\n*** Update File: dashboard_v11.html\n@@\n-" + match[0]
                 + "\n+" + new_line + "\n*** End Patch\n")
        subprocess.run(["apply_patch"], input=patch, text=True, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
