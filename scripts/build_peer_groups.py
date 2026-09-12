#!/usr/bin/env python3
"""Ordnet die S&P-500-Konstituenten den Vergleichsgruppen zu.

Erzeugt:
  data/out/peer_groups.csv        -- Zuordnung je Firma inkl. Begruendung
  data/out/peer_group_sizes.csv   -- Gruppengroessen
  report/generated/*.tex          -- Tabellen fuer den Bericht

Aufruf: python scripts/build_peer_groups.py [--constituents PFAD.csv]
Standardquelle ist die im Repo liegende constituents.csv; mit --refresh wird
die Liste stattdessen frisch von Wikipedia geladen.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import peers  # noqa: E402

OUT = ROOT / "data" / "out"
GEN = ROOT / "report" / "generated"
CONSTITUENTS = ROOT / "constituents.csv"
WIKI = (
    "https://en.wikipedia.org/w/api.php?action=parse"
    "&page=List_of_S%26P_500_companies&prop=text&format=json"
)


def load_constituents(path: Path | None, refresh: bool) -> pd.DataFrame:
    """Laedt die Konstituenten aus CSV (Standard) oder von Wikipedia."""
    if not refresh:
        df = pd.read_csv(path or CONSTITUENTS)
    else:
        import requests

        r = requests.get(
            WIKI,
            headers={"User-Agent": "ETHack S&P500 Sustainability Research"},
            timeout=60,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.json()["parse"]["text"]["*"]))
        df = next(t for t in tables if "CIK" in t.columns and "Symbol" in t.columns)
    return df.rename(
        columns={
            "Symbol": "ticker",
            "Security": "company",
            "GICS Sector": "gics_sector",
            "GICS Sub-Industry": "gics_sub_industry",
        }
    )[["ticker", "company", "gics_sector", "gics_sub_industry"]]


def tex_escape(s: str) -> str:
    """Maskiert die Zeichen, die LaTeX in Fliesstext nicht vertraegt."""
    for a, b in [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]:
        s = s.replace(a, b)
    return s


def write_overview(sizes: pd.Series) -> None:
    """Tabelle: Gruppe, Archetyp, Groesse, Bezugsgroesse, Datenlage."""
    rows = []
    for g in peers.GROUPS:
        rows.append(
            " & ".join(
                [
                    g.key,
                    tex_escape(g.label),
                    g.archetype,
                    str(int(sizes.get(g.key, 0))),
                    tex_escape(g.level),
                ]
            )
            + r" \\"
        )
    body = "\n".join(rows)
    (GEN / "groups_overview.tex").write_text(
        "\\begin{tabularx}{\\linewidth}{@{}l X c r l@{}}\n"
        "\\toprule\n"
        "ID & Vergleichsgruppe & Arch. & $n$ & Scope-1-Datenlage \\\\\n"
        "\\midrule\n" + body + "\n\\bottomrule\n\\end{tabularx}\n",
        encoding="utf-8",
    )


def write_archetypes(assigned: pd.DataFrame) -> None:
    """Tabelle: die sechs Archetypen mit Wirkungsort und Konsequenz."""
    counts = assigned["archetype"].value_counts()
    rows = []
    for a in peers.ARCHETYPES.values():
        members = ", ".join(g.key for g in peers.GROUPS if g.archetype == a.key)
        rows.append(
            " & ".join(
                [
                    a.key,
                    tex_escape(a.label),
                    tex_escape(a.locus),
                    f"{int(counts.get(a.key, 0))}",
                    members,
                ]
            )
            + r" \\"
        )
    (GEN / "archetypes.tex").write_text(
        "\\begin{tabularx}{\\linewidth}{@{}l l X r P{2.3cm}@{}}\n"
        "\\toprule\n"
        "ID & Archetyp & Wirkungsort des dominanten Fußabdrucks & $n$ & Gruppen \\\\\n"
        "\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabularx}\n",
        encoding="utf-8",
    )


def write_group_details(assigned: pd.DataFrame) -> None:
    """Je Gruppe ein Block: Begruendung, Kennzahlen, Bezugsgroesse, Mitglieder."""
    parts = []
    for g in peers.GROUPS:
        members = assigned[assigned["peer_group"] == g.key].sort_values("ticker")
        tickers = ", ".join(tex_escape(t) for t in members["ticker"])
        metrics = "\n".join(f"  \\item {tex_escape(m)}" for m in g.material)
        parts.append(
            f"\\subsection*{{{g.key} -- {tex_escape(g.label)} "
            f"\\normalfont\\small ({len(members)} Firmen, Archetyp {g.archetype})}}\n"
            f"\\noindent {tex_escape(g.rationale)}\n\n"
            f"\\noindent\\textbf{{Materielle Kennzahlen}}\n"
            f"\\begin{{itemize}}[nosep,leftmargin=1.2em]\n{metrics}\n\\end{{itemize}}\n"
            f"\\noindent\\textbf{{Bezugsgröße:}} {tex_escape(g.denominator)}\\\\\n"
            f"\\textbf{{Datenlage:}} {tex_escape(g.coverage)}\\\\\n"
            f"\\textbf{{Untergruppen (Ebene C):}} "
            f"{tex_escape(', '.join(g.tiers))}\\\\\n"
            f"\\textbf{{Mitglieder:}} "
            f"{{\\raggedright\\small\\ttfamily {tickers}\\par}}\n"
        )
    (GEN / "group_details.tex").write_text("\n\\medskip\n".join(parts), encoding="utf-8")


def write_overrides(assigned: pd.DataFrame) -> None:
    """Tabelle der Ticker-Ausnahmen: von GICS-Gruppe zu Zielgruppe mit Grund."""
    by_ticker = assigned.set_index("ticker")
    rows = []
    for ticker, (target, reason) in sorted(peers.TICKER_OVERRIDES.items()):
        if ticker not in by_ticker.index:
            continue
        sub = by_ticker.loc[ticker, "gics_sub_industry"]
        default = peers.SUB_INDUSTRY_MAP.get(sub, "--")
        rows.append(
            " & ".join(
                [
                    f"\\texttt{{{tex_escape(ticker)}}}",
                    default,
                    target,
                    tex_escape(reason),
                ]
            )
            + r" \\"
        )
    (GEN / "overrides.tex").write_text(
        "\\begin{tabularx}{\\linewidth}{@{}l c c X@{}}\n"
        "\\toprule\n"
        "Ticker & GICS-Standard & zugeordnet & Begründung \\\\\n"
        "\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabularx}\n",
        encoding="utf-8",
    )


def write_contested() -> None:
    """Tabelle der strittigen Zuordnungen fuer die Sensitivitaetsanalyse."""
    rows = []
    for ticker, (alts, note) in sorted(peers.CONTESTED.items()):
        rows.append(
            f"\\texttt{{{tex_escape(ticker)}}} & {', '.join(alts)} "
            f"& {tex_escape(note)} \\\\"
        )
    (GEN / "contested.tex").write_text(
        "\\begin{tabularx}{\\linewidth}{@{}l l X@{}}\n"
        "\\toprule\n"
        "Ticker & Gruppen im Sensitivitätslauf & Worin der Streit besteht \\\\\n"
        "\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabularx}\n",
        encoding="utf-8",
    )


def write_sector_crosswalk(assigned: pd.DataFrame) -> None:
    """Zeigt, wie stark die Gruppen die GICS-Sektoren aufbrechen."""
    ct = pd.crosstab(assigned["gics_sector"], assigned["peer_group"])
    rows = []
    for sector, row in ct.iterrows():
        hits = [(k, int(v)) for k, v in row.items() if v > 0]
        hits.sort(key=lambda kv: -kv[1])
        cell = ", ".join(f"{k} ({n})" for k, n in hits)
        rows.append(
            f"{tex_escape(str(sector))} & {int(row.sum())} & {len(hits)} "
            f"& {{\\small {cell}}} \\\\"
        )
    (GEN / "crosswalk.tex").write_text(
        "\\begin{tabularx}{\\linewidth}{@{}l r c X@{}}\n"
        "\\toprule\n"
        "GICS-Sektor & $n$ & Gruppen & Aufteilung \\\\\n"
        "\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabularx}\n",
        encoding="utf-8",
    )


def write_stats(assigned: pd.DataFrame, sizes: pd.Series) -> None:
    """Einzelwerte, die im Text als Makro auftauchen -- keine Zahl doppelt pflegen."""
    lines = [
        f"\\newcommand{{\\NFirms}}{{{len(assigned)}}}",
        f"\\newcommand{{\\NGroups}}{{{len(peers.GROUPS)}}}",
        f"\\newcommand{{\\NArchetypes}}{{{len(peers.ARCHETYPES)}}}",
        f"\\newcommand{{\\NSubIndustries}}{{{assigned['gics_sub_industry'].nunique()}}}",
        f"\\newcommand{{\\NSectors}}{{{assigned['gics_sector'].nunique()}}}",
        f"\\newcommand{{\\MinGroup}}{{{int(sizes.min())}}}",
        f"\\newcommand{{\\MaxGroup}}{{{int(sizes.max())}}}",
        f"\\newcommand{{\\MedGroup}}{{{int(sizes.median())}}}",
        f"\\newcommand{{\\NOverrides}}{{{len(peers.TICKER_OVERRIDES)}}}",
        f"\\newcommand{{\\NContested}}{{{len(peers.CONTESTED)}}}",
        f"\\newcommand{{\\MinSize}}{{{peers.MIN_GROUP_SIZE}}}",
    ]
    (GEN / "stats.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--constituents", type=Path, default=None)
    ap.add_argument("--refresh", action="store_true",
                    help="Konstituentenliste von Wikipedia neu laden")
    args = ap.parse_args()

    df = load_constituents(args.constituents, args.refresh)
    assigned = peers.assign(df)
    problems = peers.validate(assigned)

    GEN.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    sizes = assigned["peer_group"].value_counts()

    assigned.sort_values(["peer_group", "ticker"]).to_csv(
        OUT / "peer_groups.csv", index=False
    )
    size_table = (
        sizes.rename("n")
        .rename_axis("peer_group")
        .reset_index()
        .assign(
            label=lambda d: d["peer_group"].map(lambda k: peers.GROUPS_BY_KEY[k].label),
            archetype=lambda d: d["peer_group"].map(
                lambda k: peers.GROUPS_BY_KEY[k].archetype
            ),
        )
        .sort_values("peer_group")
    )
    size_table.to_csv(OUT / "peer_group_sizes.csv", index=False)

    write_overview(sizes)
    write_archetypes(assigned)
    write_group_details(assigned)
    write_overrides(assigned)
    write_contested()
    write_sector_crosswalk(assigned)
    write_stats(assigned, sizes)

    print(f"{len(assigned)} Firmen, {len(peers.GROUPS)} Gruppen, "
          f"{assigned['gics_sub_industry'].nunique()} Sub-Industries")
    print(size_table.to_string(index=False))
    print(f"\nGroesse: min {sizes.min()}, median {int(sizes.median())}, "
          f"max {sizes.max()}")
    if problems:
        print("\nBEFUNDE:")
        for p in problems:
            print("  -", p)
        return 1
    print("\nValidierung sauber: vollstaendig zugeordnet, alle Gruppen "
          f"mindestens {peers.MIN_GROUP_SIZE} Mitglieder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
