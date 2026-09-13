"""Grafiken fuer den Bericht."""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

B = Path("build"); FIG = Path("figures"); FIG.mkdir(exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "figure.dpi": 200, "savefig.bbox": "tight",
})
INK = "#1f2937"; ACC = "#2563eb"; WARN = "#dc2626"; MUT = "#9ca3af"

uncond = pd.read_parquet(B / "out_rank_distribution.parquet")
cond = pd.read_parquet(B / "out_rank_conditional.parquet")
sens = pd.read_parquet(B / "out_sensitivity.parquet")
cred = pd.read_parquet(B / "out_credibility_axis.parquet")
port = pd.read_parquet(B / "out_portfolio.parquet")
panel = pd.read_parquet(B / "int_indicator_panel.parquet")
psum = json.loads((B / "portfolio_summary.json").read_text())


# 1 ---------------------------------------------------------------- Rangbaender
def fig_rank_bands():
    d = cond.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.0, 5.4))
    y = np.arange(len(d))
    ax.hlines(y, d.rank_p05, d.rank_p95, color=MUT, lw=5, alpha=.55)
    ax.plot(d.median_rank, y, "o", color=ACC, ms=5, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{t}  ({s[:12]})" for t, s in zip(d.ticker, d.gics_sector)],
                       fontsize=7.5)
    ax.set_xlabel("Globaler Rang (1 = bester Emissionsverlauf), 115 Firmen")
    ax.set_title("Die 20 bestplatzierten Firmen mit 90-Prozent-Rangband\n"
                 "Balken = Bandbreite ueber 72 Methoden x 200 Datenziehungen",
                 fontsize=9.5, loc="left")
    ax.invert_xaxis()
    fig.savefig(FIG / "01_rangbaender.png"); plt.close(fig)


# 2 ---------------------------------------------------------------- Sobol
def fig_sensitivity():
    d = sens.sort_values("sobol_total")
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    y = np.arange(len(d))
    ax.barh(y, d.sobol_total, color=MUT, height=.62, label="Totaleffekt (mit Wechselwirkungen)")
    ax.barh(y, d.sobol_first_order, color=ACC, height=.62, label="Haupteffekt")
    ax.set_yticks(y); ax.set_yticklabels(d.factor, fontsize=8.5)
    ax.set_xlabel("Anteil an der Rang-Streuung")
    ax.set_title("Woher kommt die Unsicherheit in der Rangliste?", fontsize=9.5, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    fig.savefig(FIG / "02_sensitivitaet.png"); plt.close(fig)


# 3 -------------------------------------------------- unbedingt vs. bedingt
def fig_width_compare():
    a = (uncond.rank_p95 - uncond.rank_p05)
    b = (cond.rank_p95 - cond.rank_p05)
    c = (cond.sector_rank_p95 - cond.sector_rank_p05)
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bins = np.arange(0, 116, 5)
    ax.hist(a, bins=bins, color=WARN, alpha=.55, label=f"alle 216 Methoden, globaler Rang (Median {int(a.median())})")
    ax.hist(b, bins=bins, color=MUT, alpha=.65, label=f"Sektorebene fix, globaler Rang (Median {int(b.median())})")
    ax.hist(c, bins=bins, color=ACC, alpha=.85, label=f"Sektorebene fix, Rang im Sektor (Median {int(c.median())})")
    ax.set_xlabel("Breite des 90-Prozent-Rangbands (Raenge)")
    ax.set_ylabel("Anzahl Firmen")
    ax.set_title("Eine einzige Festlegung entscheidet ueber die Aussagekraft",
                 fontsize=9.5, loc="left")
    ax.legend(fontsize=7.2, frameon=False)
    fig.savefig(FIG / "03_bandbreiten.png"); plt.close(fig)


# 4 ---------------------------------------------------------------- Sektor
def fig_pledge_gap():
    """Versprechen gegen Realitaet - nur Firmen mit auswertbarem SBTi-Ziel."""
    d = cred[cred.pledge_gap.notna()].copy()
    d = d.sort_values("pledge_gap")
    fig, ax = plt.subplots(figsize=(6.8, max(3.0, .26 * len(d))))
    y = np.arange(len(d))
    ax.hlines(y, d.required_cagr * 100, d.cagr_long * 100, color=MUT, lw=1.6, alpha=.8)
    ax.plot(d.required_cagr * 100, y, "o", color=ACC, ms=4.5, label="laut SBTi-Ziel noetig")
    ax.plot(d.cagr_long * 100, y, "o", color=WARN, ms=4.5, label="tatsaechlich erreicht")
    ax.axvline(0, color=INK, lw=.6)
    ax.set_yticks(y); ax.set_yticklabels(d.ticker, fontsize=7)
    ax.set_xlabel("Jaehrliche Veraenderung der Scope-1-Emissionen (Prozent)")
    ax.set_title(f"Versprechen gegen Realitaet ({len(d)} Firmen mit auswertbarem Ziel)",
                 fontsize=9.5, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    fig.savefig(FIG / "08_zielluecke.png"); plt.close(fig)


def fig_sector_detail(sector="Utilities"):
    d = cond[cond.gics_sector == sector].sort_values("sector_median_rank").iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.6, max(2.6, .28 * len(d))))
    y = np.arange(len(d))
    ax.hlines(y, d.sector_rank_p05, d.sector_rank_p95, color=MUT, lw=5, alpha=.55)
    ax.plot(d.sector_median_rank, y, "o", color=ACC, ms=5, zorder=3)
    ax.set_yticks(y); ax.set_yticklabels(d.ticker, fontsize=7.5)
    ax.set_xlabel(f"Rang innerhalb des Sektors ({len(d)} Firmen)")
    ax.set_title(f"Sektor {sector}: hier traegt die Rangfolge", fontsize=9.5, loc="left")
    ax.invert_xaxis()
    fig.savefig(FIG / "04_sektor_utilities.png"); plt.close(fig)


# 5 ---------------------------------------------------------------- Indikatoren
def fig_indicator_uncertainty():
    codes = sorted(panel.indicator_code.unique())
    fig, axes = plt.subplots(2, 3, figsize=(7.4, 4.2))
    for ax, c in zip(axes.ravel(), codes):
        d = panel[panel.indicator_code == c]
        ax.errorbar(d.raw_value, np.arange(len(d)), xerr=d.value_se,
                    fmt="o", ms=1.6, lw=.4, color=ACC, ecolor=MUT, alpha=.7)
        ax.set_title(c, fontsize=8)
        ax.set_yticks([])
        ax.tick_params(labelsize=6.5)
    fig.suptitle("Jeder Indikator mit seinem Standardfehler (115 Firmen)",
                 fontsize=9.5, x=.02, ha="left")
    fig.tight_layout()
    fig.savefig(FIG / "05_indikatoren.png"); plt.close(fig)


# 6 ---------------------------------------------------------------- Portfolio
def fig_portfolio():
    sec = port.groupby("gics_sector")[["benchmark_weight", "weight"]].sum().sort_values("weight")
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.4),
                             gridspec_kw={"width_ratios": [1.25, 1]})
    ax = axes[0]
    y = np.arange(len(sec))
    ax.barh(y - .2, sec.benchmark_weight, height=.4, color=MUT, label="Benchmark")
    ax.barh(y + .2, sec.weight, height=.4, color=ACC, label="PAB-Portfolio")
    ax.set_yticks(y); ax.set_yticklabels(sec.index, fontsize=7)
    ax.set_xlabel("Sektorgewicht")
    ax.legend(fontsize=7, frameon=False)
    ax.set_title("Kein Sektor wird untergewichtet", fontsize=9, loc="left")

    ax = axes[1]
    ax.bar([0, 1], [psum["base_carbon"], psum["new_carbon"]],
           color=[MUT, ACC], width=.55)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Benchmark", "PAB"], fontsize=8)
    ax.set_ylabel("Gewichtete Scope-1-Emissionen (t)")
    ax.set_title(f"Reduktion {psum['reduction']*100:.0f} Prozent", fontsize=9, loc="left")
    fig.tight_layout()
    fig.savefig(FIG / "06_portfolio.png"); plt.close(fig)


# 7 ---------------------------------------------------------------- Achsen
def fig_two_axes():
    d = cond.merge(cred[["company_id", "flag_count", "credibility_band"]], on="company_id")
    colors = {"Gut gestuetzt": ACC, "Unklar": MUT, "Schwach gestuetzt": WARN}
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for band, grp in d.groupby("credibility_band"):
        ax.scatter(grp.median_rank, grp.flag_count + np.random.default_rng(0)
                   .uniform(-.16, .16, len(grp)),
                   s=22, alpha=.75, color=colors[band], label=band, edgecolor="none")
    ax.set_xlabel("Score-Rang (1 = bester Emissionsverlauf)")
    ax.set_ylabel("Anzahl Datenqualitaets-Flaggen")
    ax.set_title("Zwei Achsen, bewusst nicht verrechnet", fontsize=9.5, loc="left")
    ax.legend(fontsize=7.5, frameon=False)
    fig.savefig(FIG / "07_zwei_achsen.png"); plt.close(fig)


if __name__ == "__main__":
    fig_rank_bands(); fig_sensitivity(); fig_width_compare()
    fig_sector_detail(); fig_indicator_uncertainty()
    fig_portfolio(); fig_two_axes(); fig_pledge_gap()
    print("Grafiken:", sorted(p.name for p in FIG.glob("*.png")))
