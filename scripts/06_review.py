"""Run deterministic quality checks, repair regressions, and optional paid model advice. Human review decisions take precedence. Use --ai only when model review is wanted; deterministic rules do not require API credentials."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from pipeline import quality as Q
from pipeline.config import DATA, OUT, ROOT

REVIEW = DATA / "review"
DECISIONS = REVIEW / "decisions.csv"

# Regression checks for previously repaired
# data mechanisms. Each case records source
# evidence and a check on the exported
# observations; passing these checks does not
# independently re-audit the source.
def _values(long: pd.DataFrame, ticker: str, metric: str, year: int | None = None):
    s = long[(long.ticker == ticker) & (long.metric == metric)]
    if year is not None:
        s = s[s.year == year]
    return [float(v) for v in s.value.dropna()]


REPAIRS = [
    ("Zero instead of missing", "KHC", "EPA lists four facilities but no 2022 quantity",
     lambda l: (not _values(l, "KHC", "scope1_t", 2022), "No 2022 value rather than zero tonnes")),
    ("Program does not measure CO2", "MPC", "Facilities report only in SIPNOX (heat input and NOx)",
     lambda l: (not _values(l, "MPC", "campd_co2_t"), "No CO2 quantity rather than zero tonnes")),
    ("Join multiplication", "TSLA", "One facility, history SSSSSSSSSSSS, two join rows",
     lambda l: (max(_values(l, "TSLA", "echo_nc_quarters"), default=0)
                <= 12 * max(_values(l, "TSLA", "echo_facilities"), default=1),
                f"{max(_values(l, 'TSLA', 'echo_nc_quarters'), default=0):.0f} quarters across "
                f"{max(_values(l, 'TSLA', 'echo_facilities'), default=0):.0f} facilities, rather than 24 quarters")),
    ("Derived ratio kept separate", "GE", "4.44 t/MWh was our derived rate, not a source observation",
     lambda l: (not _values(l, "GE", "t_co2_pro_mwh") and "t_co2_pro_mwh" not in set(l.metric),
                "Only reported quantities and generation, no derived rate")),
    ("Numerator and denominator retained", "BRK-B", "113 plants and 83 TWh in a Financials issuer",
     lambda l: (bool(_values(l, "BRK-B", "egrid_mwh")) and bool(_values(l, "BRK-B", "egrid_co2_t")),
                f"{max(_values(l, 'BRK-B', 'egrid_mwh'), default=0)/1e6:.1f} TWh and "
                f"{max(_values(l, 'BRK-B', 'egrid_co2_t'), default=0)/1e6:.1f} Mt reported")),
    ("No injury rate from an unchecked denominator", "MCD",
     "Four reports with median 50 hours per employee",
     lambda l: ("dart_rate" not in set(l.metric) and bool(_values(l, "MCD", "osha_hours")),
                "Reported hours and cases retained separately")),
    ("Substring attribution", "APD", "No matching raw cases; 15 APDC Cleaning Services cases in the earlier check",
     lambda l: (not _values(l, "APD", "whd_cases"), "none Lohnverfahren mehr zugerechnet")),
    ("Derived trend kept separate", "PPL", "One facility and 5 kt in 2018; nine facilities and 28 Mt from 2019",
     lambda l: ({"absolute_cagr", "intensity_cagr", "co2_intensity"} & set(l.metric) == set()
                and bool(_values(l, "PPL", "n_facilities")),
                "Derived trends and intensities kept separate; facility counts retained")),
    ("Attribution without a validity window", "VST", "Talen Energy is not part of Vistra",
     lambda l: (all(v < 90e6 for v in _values(l, "VST", "scope1_t", 2023)),
                f"2023: {max(_values(l, 'VST', 'scope1_t', 2023), default=0)/1e6:.1f} Mt rather than 96.8")),
    ("Duplicate share class", "GOOG", "GOOG and GOOGL share CIK 1652044",
     lambda l: (not len(l[l.ticker == "GOOG"]), "Only primary ticker GOOGL retained")),
    ("All observations carry provenance", "all", "Each observation is source-reported or aggregated from source records",
     lambda l: (set(l.value_type.dropna()) <= {"reported", "aggregated"} and not l.value_type.isna().any(),
                f"{l.value_type.value_counts().to_dict()}")),
]


def check_repairs(long: pd.DataFrame) -> list[dict]:
    out = []
    for topic, ticker, evidence, test in REPAIRS:
        try:
            ok, finding = test(long)
        except Exception as e:  # A failed check is itself a finding.
            ok, finding = False, f"Check failed: {e}"
        out.append({"topic": topic, "ticker": ticker, "evidence": evidence,
                    "resolved": bool(ok), "finding": finding})
    return out


def main(use_ai: bool) -> None:
    print("Rules:")
    flags = Q.run()
    flags.to_csv(OUT / "flags.csv", index=False)
    long = pd.read_parquet(OUT / "dataset_long.parquet")
    rep = check_repairs(long)
    print("\nRepair regression checks:")
    for r in rep:
        print(f"  {'ok ' if r['resolved'] else 'PENDING'} {r['ticker']:6s} {r['topic']:42s} {r['finding']}")
    pd.DataFrame(rep).to_csv(OUT / "repairs.csv", index=False)

    summary: dict = {
        "flags": len(flags),
        "repairs": rep,
        "repairs_passed": int(sum(r["resolved"] for r in rep)),
        "error": int((flags.severity == "error").sum()),
        "review": int((flags.severity == "review").sum()),
        "by_rule": flags.groupby("rule").size().to_dict(),
        "companies_affected": int(flags.ticker.nunique()),
        "ranking_relevant": int(flags.ranking_relevant.sum()),
    }

    if use_ai:
        from pipeline import ai_review as A

        items = [(row.to_dict(), Q.packet(row)) for _, row in flags.iterrows()]
        print(f"AI review of {len(items)} cases using {A.MODEL}, escalation {A.ESCALATION_MODEL} ...")
        reviewed = pd.DataFrame(A.review_many(items))

        tokens = pd.to_numeric(reviewed.tokens, errors="coerce").fillna(0).sum()
        summary["ai"] = {
            "model": A.MODEL, "escalation": A.ESCALATION_MODEL,
            "verdicts": reviewed.ai_verdict.value_counts().to_dict(),
            "causes": reviewed.ai_cause.value_counts().to_dict(),
            "routes": reviewed.route.value_counts().to_dict(),
            "escalated": int(reviewed.get("ai_first_pass", pd.Series(dtype=object)).notna().sum()),
            "rule_error_confirmed": int(((reviewed.severity == "error") & (reviewed.ai_verdict == "error")).sum()),
            "rule_error_disputed": int(((reviewed.severity == "error") & (reviewed.ai_verdict == "plausible")).sum()),
            "total_tokens": int(tokens),
        }

    else:
        reviewed = flags.copy()

    REVIEW.mkdir(parents=True, exist_ok=True)
    if not DECISIONS.exists():
        DECISIONS.write_text("flag_id,decision,person,date,reason\n", encoding="utf-8")
    decisions = pd.read_csv(DECISIONS, dtype=str)
    if decisions.flag_id.duplicated().any():
        raise ValueError("Duplicate human decisions for a flag_id")
    reviewed = reviewed.merge(decisions[["flag_id", "decision", "person", "reason"]], on="flag_id", how="left")
    from pipeline.flag_apply import status_of, apply as apply_flags
    reviewed["final"] = pd.Series([status_of(row) for _, row in reviewed.iterrows()], index=reviewed.index, dtype="str")
    reviewed.to_csv(OUT / "reviewed_flags.csv", index=False)
    records = reviewed.assign(evidence=reviewed.evidence.map(json.loads))
    (OUT / "reviewed_flags.json").write_text(records.to_json(orient="records", force_ascii=False), encoding="utf-8")
    long = apply_flags(long)
    long.to_csv(OUT / "dataset_long.csv", index=False)
    long.to_parquet(OUT / "dataset_long.parquet", index=False)
    (OUT / "quality_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main(use_ai="--ai" in sys.argv)
