"""Assess available evidence separately for E, S, and G.

Group related metrics into evidence families and count each family's largest weight once. Strong evidence requires multiple families and an anchor. Weights and thresholds are explicit design assumptions; family separation does not prove statistical independence. This measures available evidence, not sustainability performance or calibrated certainty."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import OUT

PILLARS = {
    "E": "Environment",
    "S": "Social",
    "G": "Governance",
}


@dataclass(frozen=True)
class Evidence:
    pillar: str
    family: str
    family_label: str
    weight: float
    evidence: str


# Evidence weights range from 1.0 for selected official measurements or findings through 0.8 for reports, 0.5-0.7 for uncertain attribution, 0.3-0.4 for assessments or target validation, to 0.2 for filing status. Consult each entry for its actual weight.
METRIC_EVIDENCE: dict[str, Evidence] = {
    # Environment.
    "campd_co2_t": Evidence("E", "ghg", "Greenhouse gases", 1.0, "Power-sector monitoring (CEMS)"),
    "scope1_t": Evidence("E", "ghg", "Greenhouse gases", 0.8, "Reported to regulator (GHGRP)"),
    "egrid_co2_t": Evidence("E", "generation", "Generation", 0.8, "Reported plant balance (eGRID)"),
    "egrid_mwh": Evidence("E", "generation", "Generation", 0.8, "Reported plant balance (eGRID)"),
    "tri_releases_lbs": Evidence("E", "pollutants", "Pollutant releases", 0.8, "Reported to regulator (TRI)"),
    "tri_carcinogen_lbs": Evidence("E", "pollutants", "Pollutant releases", 0.8, "Reported to regulator (TRI)"),
    "wba_nature": Evidence("E", "nature", "Nature assessment", 0.4, "Assessment of disclosed information (WBA)"),
    "sbti_validated": Evidence("E", "climate_targets", "Climate targets", 0.3, "Company target, externally validated (SBTi)"),
    "sbti_near_term_year": Evidence("E", "climate_targets", "Climate targets", 0.3, "Company target, externally validated (SBTi)"),
    "sbti_net_zero_year": Evidence("E", "climate_targets", "Climate targets", 0.3, "Company target, externally validated (SBTi)"),
    "wba_tpq": Evidence("E", "climate_targets", "Climate targets", 0.3, "Assessment of transition plan (WBA)"),
    "wba_ctt": Evidence("E", "climate_targets", "Climate targets", 0.3, "Assessment of contribution to transition (WBA)"),
    # Social.
    "osha_dafw_cases": Evidence("S", "occupational_safety", "Occupational safety", 1.0, "Mandatory establishment report (OSHA)"),
    "osha_djtr_cases": Evidence("S", "occupational_safety", "Occupational safety", 1.0, "Mandatory establishment report (OSHA)"),
    "osha_deaths": Evidence("S", "occupational_safety", "Occupational safety", 1.0, "Mandatory establishment report (OSHA)"),
    "whd_cases": Evidence("S", "wage_law", "Wage law", 0.7, "Official finding, uncertain name attribution"),
    "whd_backwages_usd": Evidence("S", "wage_law", "Wage law", 0.7, "Official finding, uncertain name attribution"),
    "whd_employees": Evidence("S", "wage_law", "Wage law", 0.7, "Official finding, uncertain name attribution"),
    "wba_social": Evidence("S", "social_assessment", "Social assessment", 0.4, "Assessment of disclosed information (WBA)"),
    "wba_just_transition": Evidence("S", "social_assessment", "Social assessment", 0.4, "Assessment of disclosed information (WBA)"),
    # Governance.
    "echo_penalties_usd": Evidence("G", "compliance", "Environmental compliance", 1.0, "Official finding (ECHO)"),
    "echo_nc_quarters": Evidence("G", "compliance", "Environmental compliance", 1.0, "Official finding (ECHO)"),
    "echo_significant": Evidence("G", "compliance", "Environmental compliance", 1.0, "Official finding (ECHO)"),
    "sbti_commitment_removed": Evidence("G", "commitments", "Handling of commitments", 0.5, "Recorded commitment removal (SBTi)"),
    "sbti_near_term_expired": Evidence("G", "commitments", "Handling of commitments", 0.5, "Target year elapsed (SBTi)"),
    "sbti_net_zero_removed": Evidence("G", "commitments", "Handling of commitments", 0.5, "Recorded commitment removal (SBTi)"),
    "sd_conflict_minerals_filer": Evidence("G", "supply_chain", "Supply-chain filing obligations", 0.2, "Filing status only (Form SD)"),
}

# Pillar thresholds.
ANCHOR_WEIGHT = 0.8     # Minimum anchor weight.
MIN_FAMILIES = 2        # Minimum distinct evidence families.
MIN_SCORE = 1.5         # Minimum sum of family weights.
PARTIAL_SCORE = 1.0     # Partial-evidence score threshold.
MIN_PEERS = 6           # Minimum sector size for comparison.
NARROW_BAND = 20.0      # Descriptive narrow-band cutoff; not statistical certainty.

LEVELS = ["strong", "partial", "thin", "none"]
LEVEL_RULES = {
    "strong": f"at least {MIN_FAMILIES} distinct families, including an anchor (weight >= {ANCHOR_WEIGHT:.1f}), sum >= {MIN_SCORE:.1f}",
    "partial": f"one Anker present_keys oder Summe ≥ {PARTIAL_SCORE:.1f}",
    "thin": "Limited indirect evidence",
    "none": "No evidence for this pillar",
}


def max_score(pillar: str) -> float:
    fam: dict[str, float] = {}
    for e in METRIC_EVIDENCE.values():
        if e.pillar == pillar:
            fam[e.family] = max(fam.get(e.family, 0.0), e.weight)
    return round(sum(fam.values()), 2)


def level(score: float, families: int, anchor: bool) -> str:
    if score <= 0:
        return "none"
    if anchor and families >= MIN_FAMILIES and score >= MIN_SCORE:
        return "strong"
    if anchor or score >= PARTIAL_SCORE:
        return "partial"
    return "thin"


def assess(long: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Return company-level evidence scores, family counts, and levels by pillar."""
    long = long[long["quality_status"] != "error"] if "quality_status" in long else long
    present = long.dropna(subset=["value"]).groupby("ticker")["metric"].apply(set)
    counts = long.dropna(subset=["value"]).groupby("ticker")["metric"].nunique()
    # Ranking bands are derived analysis and are
    # stored separately from observations.
    band_path = OUT / "climate_bands.csv"
    bands = (pd.read_csv(band_path).set_index("ticker")[["p10", "p90"]]
             if band_path.exists() else pd.DataFrame(columns=["p10", "p90"]))
    rows = []
    for r in master.itertuples(index=False):
        have = present.get(r.ticker, set())
        row = {
            "ticker": r.ticker,
            "company": r.company,
            "gics_sector": r.gics_sector,
            "n_values": int(counts.get(r.ticker, 0)),
        }
        for p in PILLARS:
            fam: dict[str, float] = {}
            for m in have:
                e = METRIC_EVIDENCE.get(m)
                if e and e.pillar == p:
                    fam[e.family] = max(fam.get(e.family, 0.0), e.weight)
            score = round(sum(fam.values()), 2)
            anchor = any(w >= ANCHOR_WEIGHT for w in fam.values())
            row[f"{p}_score"] = score
            row[f"{p}_families"] = len(fam)
            row[f"{p}_family_list"] = ", ".join(sorted(fam))
            row[f"{p}_anchor"] = anchor
            row[f"{p}_level"] = level(score, len(fam), anchor)
        if r.ticker in bands.index:
            b = bands.loc[r.ticker]
            row["e_band_width"] = float(b["p90"] - b["p10"]) if b.notna().all() else None
        else:
            row["e_band_width"] = None
        rows.append(row)
    df = pd.DataFrame(rows)
    df["n_reliable"] = sum((df[f"{p}_level"] == "strong").astype(int) for p in PILLARS)
    return df
