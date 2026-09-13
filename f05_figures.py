"""Grafiken der Fusionsauswertung."""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

F = Path("fusion"); G = Path("fig2"); G.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "sans-serif", "font.size": 9,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": .25, "grid.linewidth": .5,
                     "figure.dpi": 200, "savefig.bbox": "tight"})
INK, ACC, WARN, MUT, OK = "#1f2937", "#2563eb", "#dc2626", "#9ca3af", "#059669"

audit = pd.read_parquet(F / "audit_esi.parquet")
bands = pd.read_parquet(F / "out_rank_bands.parquet")
cond = pd.read_parquet(F / "out_bands_conditional.parquet")
sens = pd.read_parquet(F / "out_sensitivity.parquet")
cov = pd.read_parquet(F / "out_coverage.parquet")
cred = pd.read_parquet(F / "out_credibility.parquet")
port = pd.read_parquet(F / "out_portfolio.parquet")
vint = pd.read_parquet(F / "out_vintage_backtest.parquet")
corr = pd.read_csv(F / "indicator_correlation.csv", index_col=0)
psum = json.loads((F / "out_portfolio_summary.json").read_text())
agg = json.loads((F / "out_aggregation_test.json").read_text())
vsum = json.loads((F / "out_vintage_summary.json").read_text())


def f1_esi():
    d = audit.groupby("typ").mt_2023.sum().reindex(
        ["direkt (E)", "Lieferant (S)", "Injektion (I)"]).fillna(0)
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    colors = [OK, WARN, MUT]
    b = ax.barh(range(3), d.values, color=colors, height=.6)
    ax.set_yticks(range(3))
    ax.set_yticklabels(["Direktemission (E)\nverwendet",
                        "Lieferant (S)\nausgeschlossen",
                        "Injektion (I)\nausgeschlossen"], fontsize=8)
    for i, v in enumerate(d.values):
        ax.text(v + 80, i, f"{v:,.0f} Mt".replace(",", " "), va="center", fontsize=8.5)
    ax.set_xlabel("Mio. t CO2e")
    ax.set_xlim(0, d.max() * 1.22)
    ax.set_title(f"Naive Summe waere Faktor {d.sum()/d.iloc[0]:.2f} zu hoch",
                 fontsize=9.5, loc="left")
    ax.invert_yaxis()
    fig.savefig(G / "f1_esi.png"); plt.close(fig)


def f2_coverage():
    d = cov.sort_values("quote")
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    y = np.arange(len(d))
    col = [ACC if q >= 50 else WARN for q in d.quote]
    ax.barh(y, d.quote, color=col, height=.62)
    ax.set_yticks(y); ax.set_yticklabels(d.index, fontsize=8)
    for i, (q, b, g) in enumerate(zip(d.quote, d.bewertbar, d.gesamt)):
        ax.text(q + 1.5, i, f"{b}/{g}", va="center", fontsize=7.5)
    ax.set_xlabel("Anteil der Indexmitglieder mit Emissionsdaten (%)")
    ax.set_xlim(0, 108)
    ax.set_title("Die Luecke ist nicht zufaellig verteilt", fontsize=9.5, loc="left")
    fig.savefig(G / "f2_coverage.png"); plt.close(fig)


def f3_group_bands(group=None):
    if group is None:
        group = bands.profile_group.value_counts().index[0]
    d = bands[bands.profile_group == group].sort_values("median_pct")
    fig, ax = plt.subplots(figsize=(6.6, max(2.8, .27 * len(d))))
    y = np.arange(len(d))
    ax.hlines(y, d.p10, d.p90, color=MUT, lw=5, alpha=.55)
    ax.plot(d.median_pct, y, "o", color=ACC, ms=5, zorder=3)
    ax.set_yticks(y); ax.set_yticklabels(d.ticker, fontsize=7.5)
    ax.set_xlabel("Perzentil in der Vergleichsgruppe (100 = bester Wert)")
    ax.set_title(f"Profilgruppe {group}: {len(d)} Firmen, Band ueber 768 Konfigurationen",
                 fontsize=9.5, loc="left")
    ax.set_xlim(-3, 103)
    fig.savefig(G / "f3_gruppe.png"); plt.close(fig)


def f4_sensitivity():
    d = sens.sort_values("totaleffekt")
    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    y = np.arange(len(d))
    cols = [MUT if a == "Methode" else "#c7d2fe" for a in d.art]
    main = [ACC if a == "Methode" else OK for a in d.art]
    ax.barh(y, d.totaleffekt, color=cols, height=.62)
    ax.barh(y, d.haupteffekt, color=main, height=.62)
    ax.set_yticks(y); ax.set_yticklabels(d.faktor, fontsize=8)
    ax.set_xlabel("Anteil an der Streuung der Perzentile")
    ax.set_title("Blau = Methodenwahl, gruen = Datenvariante\n"
                 "hell = Totaleffekt mit Wechselwirkungen", fontsize=9, loc="left")
    fig.savefig(G / "f4_sensitivitaet.png"); plt.close(fig)


def f5_corr():
    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    m = corr.values.astype(float)
    im = ax.imshow(m, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr))); ax.set_xticklabels(corr.columns, rotation=45,
                                                        ha="right", fontsize=7)
    ax.set_yticks(range(len(corr))); ax.set_yticklabels(corr.index, fontsize=7)
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{m[i,j]:.2f}", ha="center", va="center",
                    fontsize=6.5, color="white" if abs(m[i, j]) > .55 else INK)
    ax.grid(False)
    ax.set_title("Spearman zwischen den Score-Indikatoren", fontsize=9, loc="left")
    fig.colorbar(im, ax=ax, shrink=.8)
    fig.savefig(G / "f5_korrelation.png"); plt.close(fig)


def f6_vintage():
    fig, ax = plt.subplots(figsize=(4.8, 4.4))
    big = vint.abw_pp > 10
    ax.scatter(vint.pct_2023[~big], vint.pct_2021[~big], s=18, color=ACC, alpha=.7,
               label="Abweichung bis 10 pp", edgecolor="none")
    ax.scatter(vint.pct_2023[big], vint.pct_2021[big], s=22, color=WARN, alpha=.85,
               label="ueber 10 pp", edgecolor="none")
    ax.plot([0, 100], [0, 100], "--", color=INK, lw=.7)
    ax.set_xlabel("Perzentil mit Emissionen 2023")
    ax.set_ylabel("Perzentil mit Emissionen 2021")
    ax.set_title(f"Fortschreibung: rho = {vsum['spearman']:.2f}, "
                 f"{vsum['anteil_ueber_10pp']*100:.0f}% ueber 10 pp",
                 fontsize=9, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    fig.savefig(G / "f6_vintage.png"); plt.close(fig)


def f7_credibility():
    d = bands.merge(cred[["company_id", "flag_count", "band"]], on="company_id")
    colors = {"gut gestuetzt": OK, "unklar": MUT, "schwach gestuetzt": WARN}
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    rng = np.random.default_rng(3)
    for b, g in d.groupby("band"):
        ax.scatter(g.median_pct, g.flag_count + rng.uniform(-.16, .16, len(g)),
                   s=24, alpha=.75, color=colors[b], label=b, edgecolor="none")
    ax.set_xlabel("Score-Perzentil (100 = bester Emissionsverlauf)")
    ax.set_ylabel("Warnflaggen auf Achse B")
    ax.set_title("Zwei Achsen, bewusst nicht verrechnet", fontsize=9.5, loc="left")
    ax.legend(fontsize=7.5, frameon=False)
    fig.savefig(G / "f7_achsen.png"); plt.close(fig)


def f8_portfolio():
    sec = port.groupby("gics_sector")[["benchmark_weight", "weight"]].sum().sort_values("weight")
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.4),
                             gridspec_kw={"width_ratios": [1.3, 1]})
    ax = axes[0]; y = np.arange(len(sec))
    ax.barh(y - .2, sec.benchmark_weight, height=.4, color=MUT, label="Benchmark")
    ax.barh(y + .2, sec.weight, height=.4, color=ACC, label="PAB")
    ax.set_yticks(y); ax.set_yticklabels(sec.index, fontsize=7)
    ax.set_xlabel("Sektorgewicht"); ax.legend(fontsize=7, frameon=False)
    ax.set_title("Kein Sektor untergewichtet", fontsize=9, loc="left")
    ax = axes[1]
    ax.bar([0, 1], [psum["basis_intensitaet"], psum["neue_intensitaet"]],
           color=[MUT, ACC], width=.55)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Benchmark", "PAB"], fontsize=8)
    ax.set_ylabel("t CO2e je Mio. USD Umsatz")
    ax.set_title(f"Intensitaet -{psum['reduktion']*100:.0f} Prozent", fontsize=9, loc="left")
    fig.tight_layout()
    fig.savefig(G / "f8_portfolio.png"); plt.close(fig)


def f9_bandwidths():
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    bins = np.arange(0, 101, 5)
    ax.hist(bands.breite_pp, bins=bins, color=WARN, alpha=.55,
            label=f"alle 768 Konfigurationen (Median {bands.breite_pp.median():.0f} pp)")
    ax.hist(cond.breite_profile_pp, bins=bins, color=ACC, alpha=.75,
            label=f"Gruppenschema fest (Median {cond.breite_profile_pp.median():.0f} pp)")
    ax.set_xlabel("Breite des 80-Prozent-Bands (Perzentilpunkte)")
    ax.set_ylabel("Firmen")
    ax.set_title("Auch nach allen Korrekturen bleibt das Band breit",
                 fontsize=9.5, loc="left")
    ax.legend(fontsize=7.5, frameon=False)
    fig.savefig(G / "f9_bandbreiten.png"); plt.close(fig)


def f10_dimensionen():
    d = pd.read_csv(F / "out_supplement.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.3))
    for ax, (col, lab, n) in zip(axes, [
            ("tri_je_musd", "Giftstoffe (kg je Mio. USD Umsatz)", "TRI"),
            ("unfallrate", "Arbeitsunfaelle je 200 000 Stunden", "OSHA")]):
        sub = d.dropna(subset=[col, "median_pct"])
        ax.scatter(sub.median_pct, sub[col], s=22, color=ACC, alpha=.7, edgecolor="none")
        if col == "tri_je_musd":
            ax.set_yscale("log")
        from scipy.stats import spearmanr
        r = spearmanr(sub.median_pct, sub[col])
        ax.set_xlabel("Umwelt-Score-Perzentil")
        ax.set_ylabel(lab, fontsize=8)
        ax.set_title(f"{n}: n = {len(sub)}, rho = {r.statistic:+.2f} "
                     f"(p = {r.pvalue:.2f})", fontsize=8.5, loc="left")
    fig.tight_layout()
    fig.savefig(G / "f10_dimensionen.png"); plt.close(fig)


if __name__ == "__main__":
    f1_esi(); f2_coverage(); f3_group_bands(); f4_sensitivity(); f5_corr()
    f6_vintage(); f7_credibility(); f8_portfolio(); f9_bandwidths(); f10_dimensionen()
    print("Grafiken:", sorted(p.name for p in G.glob("*.png")))
