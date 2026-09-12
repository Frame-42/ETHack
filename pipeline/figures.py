"""Grafiken fuer den Bericht.

Jede Funktion beantwortet genau eine Frage. Gemeinsame Regeln: eine Achse,
zurueckhaltendes Raster, duenne Marken, Direktbeschriftung statt Zahlen an
jedem Punkt, kategoriale Farben in fester Reihenfolge.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
from scipy import stats

from .config import FIGURES

# Kategoriale Farben in fester Reihenfolge (geprueft auf Farbsehschwaeche).
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
C4, C8 = "#eda100", "#e34948"
INK = "#17181a"
INK_SOFT = "#6b7076"
GRID = "#dfe2e5"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8.5,
        "axes.edgecolor": INK_SOFT,
        "axes.labelcolor": INK,
        "axes.titlesize": 9.5,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlepad": 9,
        "text.color": INK,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    }
)


def _clean(ax, grid: str = "x") -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)


def _save(fig, name: str) -> str:
    path = FIGURES / f"{name}.pdf"
    fig.savefig(path)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------


def fig_coverage(cov: pd.DataFrame) -> str:
    """Welche Branchen bekommen ueberhaupt Emissionsdaten?"""
    d = cov.sort_values("abdeckung_pct")
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    colors = [C8 if v == 0 else (C4 if v < 25 else C1) for v in d["abdeckung_pct"]]
    ax.barh(d["gics_sector"], d["abdeckung_pct"], color=colors, height=0.66, zorder=3)
    for y, (pct, n, tot) in enumerate(
        zip(d["abdeckung_pct"], d["firmen_mit_daten"], d["firmen_gesamt"])
    ):
        ax.text(
            pct + 1.5, y, f"{n}/{int(tot)}", va="center", fontsize=7.5, color=INK_SOFT
        )
    ax.set_xlabel("Anteil der Firmen mit EPA-Emissionsdaten (%)")
    ax.set_xlim(0, 105)
    ax.set_title("Abdeckung bricht weg, wo der Index sein Gewicht hat")
    _clean(ax)
    return _save(fig, "abdeckung_sektor")


def fig_bands(bands: pd.DataFrame, sector: str, n: int = 18) -> str:
    """Rangbaender statt Platzziffern -- die Signaturgrafik."""
    d = bands[bands["gics_sector"] == sector].sort_values("p50")
    if len(d) > n:
        d = pd.concat([d.head(n // 2), d.tail(n - n // 2)])
    fig, ax = plt.subplots(figsize=(5.6, max(2.6, 0.23 * len(d) + 1.1)))
    y = np.arange(len(d))
    ax.hlines(y, d["p10"], d["p90"], color=C1, alpha=0.32, linewidth=6, zorder=3)
    ax.plot(d["p50"], y, "o", color=C1, markersize=5.5, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels(
        [c if len(c) <= 26 else c[:24] + "..." for c in d["company"]], fontsize=7.5
    )
    ax.set_xlim(0, 100)
    ax.set_xlabel("Perzentil in der Vergleichsgruppe (100 = bester Wert)")
    ax.set_title(f"{sector}: das Band ist das Ergebnis")
    ax.text(
        0.99, -0.135, "Balken: 10.-90. Perzentil ueber 1500 Methodenkombinationen",
        transform=ax.transAxes, ha="right", fontsize=7, color=INK_SOFT,
    )
    _clean(ax)
    return _save(fig, "rangbaender")


def fig_band_width(bands: pd.DataFrame) -> str:
    """Wie breit sind die Baender -- und was heisst das fuer Einzelplaetze?"""
    fig, ax = plt.subplots(figsize=(5.6, 2.7))
    ax.hist(
        bands["band_width"].dropna(), bins=24, color=C1, alpha=0.85, zorder=3,
        edgecolor="white", linewidth=0.6,
    )
    med = bands["band_width"].median()
    ax.axvline(med, color=C2, linewidth=1.8, zorder=4)
    ax.annotate(
        f"Median {med:.0f} Perzentilpunkte",
        xy=(med, ax.get_ylim()[1] * 0.88),
        xytext=(med + 4, ax.get_ylim()[1] * 0.88),
        color=C2, fontsize=8, va="center",
    )
    ax.set_xlabel("Bandbreite p10 bis p90 (Perzentilpunkte)")
    ax.set_ylabel("Firmen")
    ax.set_title("Wie viel Rang die Methodenwahl verschiebt")
    _clean(ax, grid="y")
    return _save(fig, "bandbreiten")


def fig_vs_commercial(bands: pd.DataFrame, esg: pd.DataFrame) -> str:
    """Physisch gemessen gegen gekauft."""
    m = bands.merge(esg[["ticker", "esg_risk_total"]], on="ticker", how="inner").dropna(
        subset=["p50", "esg_risk_total"]
    )
    rho, p = stats.spearmanr(m["p50"], -m["esg_risk_total"])
    fig, ax = plt.subplots(figsize=(5.6, 3.5))
    ax.scatter(
        m["p50"], m["esg_risk_total"], s=26, color=C1, alpha=0.72,
        edgecolor="white", linewidth=0.7, zorder=3,
    )
    ax.set_xlabel("eigenes Perzentil (physisch gemessen, hoeher = besser)")
    ax.set_ylabel("kommerzielles ESG-Risiko\n(hoeher = schlechter)")
    ax.set_title("Zwei Messungen, kaum ein Zusammenhang")
    ax.text(
        0.02, 0.04,
        f"Spearman $\\rho$ = {rho:.2f}   (n = {len(m)}, p = {p:.2f})",
        transform=ax.transAxes, fontsize=8.5, color=INK,
    )
    _clean(ax, grid="both")
    return _save(fig, "vergleich_kommerziell")


def fig_sensitivity(sens: pd.DataFrame) -> str:
    """Welche Methodenentscheidung bewegt das Ergebnis am staerksten?"""
    labels = {
        "normalizer": "Normalisierung",
        "weighter": "Gewichtung",
        "aggregator": "Aggregation",
        "peer_level": "Ebene der Vergleichsgruppe",
        "winsor": "Trimmstufe",
    }
    d = sens.copy()
    d["label"] = d["dimension"].map(labels).fillna(d["dimension"])
    d = d.sort_values("mittlere_spannweite_perzentil")
    fig, ax = plt.subplots(figsize=(5.6, 2.6))
    ax.barh(d["label"], d["mittlere_spannweite_perzentil"], color=C1, height=0.6, zorder=3)
    for y, v in enumerate(d["mittlere_spannweite_perzentil"]):
        ax.text(v + 0.25, y, f"{v:.1f}", va="center", fontsize=7.5, color=INK_SOFT)
    ax.set_xlabel("mittlere Perzentilverschiebung zwischen den Auspraegungen")
    ax.set_title("Nicht die Gewichtung entscheidet")
    _clean(ax)
    return _save(fig, "methoden_sensitivitaet")


def fig_aggregation(agg: pd.DataFrame) -> str:
    """Was Kompensierbarkeit konkret kostet."""
    d = agg.dropna(subset=["geometrisch", "additiv"])
    big = d["differenz"].abs() > 10
    fig, ax = plt.subplots(figsize=(5.6, 3.5))
    ax.plot([0, 100], [0, 100], color=INK_SOFT, linewidth=0.9, linestyle="--", zorder=2)
    ax.scatter(
        d.loc[~big, "additiv"], d.loc[~big, "geometrisch"], s=22, color=C1,
        alpha=0.6, edgecolor="white", linewidth=0.6, zorder=3, label="Abweichung bis 10 Punkte",
    )
    ax.scatter(
        d.loc[big, "additiv"], d.loc[big, "geometrisch"], s=30, color=C2,
        alpha=0.9, edgecolor="white", linewidth=0.6, zorder=4, label="Abweichung ueber 10 Punkte",
    )
    ax.set_xlabel("Perzentil bei additiver Aggregation")
    ax.set_ylabel("Perzentil bei geometrischer\nAggregation")
    ax.set_title("Additiv rechnen heisst zurueckkaufen lassen")
    ax.legend(loc="upper left", fontsize=7.5)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    _clean(ax, grid="both")
    return _save(fig, "aggregation_vergleich")


def fig_staleness(detail: pd.DataFrame, rho: float, median_dev: float) -> str:
    """Der Preis der Datenluecke nach 2023."""
    fig, ax = plt.subplots(figsize=(5.6, 3.5))
    ax.plot([0, 100], [0, 100], color=INK_SOFT, linewidth=0.9, linestyle="--", zorder=2)
    dev = (detail["percentile_wahr"] - detail["percentile_veraltet"]).abs()
    ax.scatter(
        detail["percentile_wahr"], detail["percentile_veraltet"],
        s=26, c=np.where(dev > 10, C2, C1), alpha=0.72,
        edgecolor="white", linewidth=0.6, zorder=3,
    )
    ax.set_xlabel("Perzentil mit aktuellen Emissionsdaten")
    ax.set_ylabel("Perzentil mit zwei Jahre alten\nEmissionsdaten")
    ax.set_title("Fortgeschriebene Daten: die Ordnung haelt")
    ax.text(
        0.02, 0.92,
        f"Spearman $\\rho$ = {rho:.2f}\nMedian-Abweichung {median_dev:.1f} Perzentilpunkte",
        transform=ax.transAxes, fontsize=8.5, color=INK, va="top",
    )
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    _clean(ax, grid="both")
    return _save(fig, "staleness_backtest")


def fig_availability(last_epa: int, last_sec: int, esg_asof: int) -> str:
    """Zeitliche Verfuegbarkeit der Quellen -- die Begruendung der Periodenteilung."""
    rows = [
        ("SEC-Umsaetze (XBRL)", 2016, last_sec, C3),
        ("EPA GHGRP (Scope 1)", 2016, last_epa, C1),
        ("kommerzieller ESG-Snapshot", esg_asof, esg_asof, C2),
    ]
    fig, ax = plt.subplots(figsize=(5.6, 2.4))
    for i, (label, start, end, color) in enumerate(rows):
        if start == end:
            ax.plot([start], [i], "o", color=color, markersize=8, zorder=4)
        else:
            ax.barh(i, end - start + 1, left=start - 0.5, height=0.42, color=color, zorder=3)
        ax.text(end + 0.75, i, str(end), va="center", fontsize=7.5, color=INK_SOFT)
    ax.axvspan(last_epa + 0.5, 2026.5, color=C8, alpha=0.10, zorder=1)
    ax.text(
        last_epa + 0.8, 2.6, "Periode B:\nkeine Emissionsdaten",
        ha="left", va="center", fontsize=7.4, color=C8, linespacing=1.3,
    )
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=8)
    ax.set_xlim(2015.5, 2026.5)
    ax.set_ylim(-0.7, 3.4)
    ax.set_xlabel("Geschaeftsjahr")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.set_title("Warum die Periodenteilung keine Stilfrage ist")
    _clean(ax)
    return _save(fig, "verfuegbarkeit")


def fig_size_bias(bands: pd.DataFrame, panel: pd.DataFrame, esg: pd.DataFrame) -> str:
    """Haengt die Note an der Firmengroesse?"""
    own = bands.merge(panel[["ticker", "revenue_musd"]], on="ticker").dropna(
        subset=["revenue_musd", "p50"]
    )
    own = own[own["revenue_musd"] > 0]
    com = esg.merge(panel[["ticker", "revenue_musd"]], on="ticker").dropna(
        subset=["revenue_musd", "esg_risk_total"]
    )
    com = com[com["revenue_musd"] > 0]

    fig, axes = plt.subplots(1, 2, figsize=(5.9, 2.8), sharex=True)
    for ax, d, ycol, ylab, color, title in (
        (axes[0], own, "p50", "eigenes Perzentil", C1, "physisch gemessen"),
        (axes[1], com, "esg_risk_total", "ESG-Risiko (invertiert)", C2, "kommerziell"),
    ):
        y = d[ycol] if ycol == "p50" else -d[ycol]
        x = np.log10(d["revenue_musd"])
        rho, _ = stats.spearmanr(x, y)
        ax.scatter(x, y, s=18, color=color, alpha=0.65, edgecolor="white", linewidth=0.5, zorder=3)
        if len(d) > 3:
            b = np.polyfit(x, y, 1)
            xs = np.linspace(x.min(), x.max(), 20)
            ax.plot(xs, np.polyval(b, xs), color=INK, linewidth=1.2, zorder=4)
        ax.set_title(f"{title}   $\\rho$ = {rho:.2f}", fontsize=8.5)
        ax.set_xlabel("Umsatz (log$_{10}$ Mio. USD)")
        ax.set_ylabel(ylab, fontsize=8)
        _clean(ax, grid="both")
    fig.suptitle(
        "Groessen-Verzerrung: in dieser Stichprobe nirgends belegbar",
        fontsize=9.5, fontweight="bold", x=0.005, ha="left", y=1.04,
    )
    return _save(fig, "groessen_verzerrung")


def fig_greenwashing(gw: pd.DataFrame) -> str:
    """Achse B: Intensitaet faellt, absolute Tonnen steigen."""
    d = gw.dropna(subset=["intensity_cagr", "absolute_cagr"])
    d = d[(d["intensity_cagr"].abs() < 0.6) & (d["absolute_cagr"].abs() < 0.6)]
    flag = d["intensity_illusion"]
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    ax.axhline(0, color=INK_SOFT, linewidth=0.8, zorder=2)
    ax.axvline(0, color=INK_SOFT, linewidth=0.8, zorder=2)
    ax.scatter(
        d.loc[~flag, "intensity_cagr"] * 100, d.loc[~flag, "absolute_cagr"] * 100,
        s=22, color=C1, alpha=0.6, edgecolor="white", linewidth=0.5, zorder=3,
        label="unauffaellig",
    )
    ax.scatter(
        d.loc[flag, "intensity_cagr"] * 100, d.loc[flag, "absolute_cagr"] * 100,
        s=32, color=C2, alpha=0.92, edgecolor="white", linewidth=0.5, zorder=4,
        label="Intensitaet faellt, Tonnen steigen",
    )
    ax.set_xlabel("Trend der CO$_2$-Intensitaet (%/Jahr)")
    ax.set_ylabel("Trend der absoluten Tonnen\n(%/Jahr)")
    ax.set_title("Das Warnsignal sieht nur, wer beides misst")
    ax.legend(loc="upper left", fontsize=7.5)
    _clean(ax, grid="both")
    return _save(fig, "greenwashing_achse")


# ---------------------------------------------------------------------------
# Grafiken zum Datenluecken-Bericht
# ---------------------------------------------------------------------------


def fig_quellenlage(quellen: pd.DataFrame) -> str:
    """Wie weit reicht jede Quelle zeitlich -- und was kostet der Zugang?"""
    d = quellen.sort_values("jahr_bis")
    fig, ax = plt.subplots(figsize=(5.8, 3.2))
    colors = [C1 if z == "frei" else C4 for z in d["zugang"]]
    y = np.arange(len(d))
    ax.barh(y, d["jahr_bis"] - 2018, left=2018, height=0.6, color=colors, zorder=3)
    for i, (jahr, grenze) in enumerate(zip(d["jahr_bis"], d["grenze"])):
        ax.text(jahr + 0.12, i, str(jahr), va="center", fontsize=7.5, color=INK_SOFT)
    ax.set_yticks(y)
    ax.set_yticklabels(d["quelle"], fontsize=8)
    ax.axvline(2023.5, color=C8, linewidth=1.4, linestyle="--", zorder=4)
    ax.text(2023.35, -0.95, "bisher endete hier alles", fontsize=7.2,
            color=C8, va="center", ha="right")
    ax.set_xlim(2018, 2027.4)
    ax.set_ylim(-1.5, len(d) - 0.3)
    ax.set_xlabel("letztes geliefertes Geschaeftsjahr")
    ax.set_title("Die zeitliche Luecke ist schliessbar")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
    _clean(ax)
    return _save(fig, "quellenlage")


def fig_abdeckung_vorher_nachher(cov: pd.DataFrame) -> str:
    """Abdeckung je Sektor, heute gegen erreichbar."""
    d = cov.sort_values("union_pct")
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    ax.barh(y + 0.19, d["union_pct"], height=0.36, color=C3, zorder=3,
            label="mit den neuen Quellen")
    ax.barh(y - 0.19, d["epa_pct"], height=0.36, color=C1, zorder=3,
            label="heute (nur EPA)")
    for i, (a, b) in enumerate(zip(d["epa_pct"], d["union_pct"])):
        ax.text(b + 1.5, i + 0.19, f"{b:.0f}", va="center", fontsize=7, color=INK_SOFT)
        ax.text(a + 1.5, i - 0.19, f"{a:.0f}", va="center", fontsize=7, color=INK_SOFT)
    ax.set_yticks(y)
    ax.set_yticklabels(d["gics_sector"], fontsize=8)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Anteil der Firmen mit Daten (%)")
    ax.set_title("Wo die neuen Quellen wirklich greifen")
    ax.legend(loc="lower right", fontsize=7.5)
    _clean(ax)
    return _save(fig, "abdeckung_vorher_nachher")


def fig_komplementaritaet(cov: pd.DataFrame) -> str:
    """EPA und SBTi decken gegenlaeufige Haelften des Index ab."""
    d = cov.copy()
    d["epa_p"] = d["epa"] / d["firmen"] * 100
    d["sbti_p"] = d["sbti"] / d["firmen"] * 100
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    ax.plot([0, 100], [100, 0], color=INK_SOFT, linewidth=0.9, linestyle="--", zorder=2)
    ax.scatter(d["epa_p"], d["sbti_p"], s=46, color=C1, alpha=0.85,
               edgecolor="white", linewidth=0.8, zorder=4)
    for _, r in d.iterrows():
        lab = r["gics_sector"]
        lab = {"Information Technology": "Info Tech",
               "Communication Services": "Comm Services",
               "Consumer Discretionary": "Cons Discr.",
               "Consumer Staples": "Cons Staples"}.get(lab, lab)
        off = {"Real Estate": (-40, -2), "Info Tech": (6, 5),
               "Health Care": (7, -9), "Cons Discr.": (-38, -3),
               "Comm Services": (6, -3), "Energy": (6, 2)}.get(lab, (5, 4))
        ax.annotate(lab, (r["epa_p"], r["sbti_p"]), fontsize=6.8, color=INK,
                    xytext=off, textcoords="offset points")
    ax.set_xlabel("Abdeckung durch EPA-Anlagendaten (%)")
    ax.set_ylabel("Abdeckung durch SBTi-Ziele (%)")
    ax.set_title("Die beiden Quellen sind fast spiegelbildlich")
    ax.set_xlim(-4, 104)
    ax.set_ylim(-4, 90)
    _clean(ax, grid="both")
    return _save(fig, "komplementaritaet")


def fig_datenart(stats: dict, n_total: int) -> str:
    """Was die Abdeckung tatsaechlich ist -- Menge, Selbstauskunft oder nur Ziel."""
    v = stats["vereinigung"]
    gemessen = stats["ausgangslage"]["firmen_mit_emissionsdaten"]
    selbst = v["davon_mit_emissionsmenge_erwartet"] - gemessen
    nur_ziel = v["nur_zielstatus_ohne_menge"]
    nichts = n_total - gemessen - selbst - nur_ziel
    teile = [
        ("gemessene Tonnen (EPA)", gemessen, C1),
        ("selbstberichtet, zu extrahieren", selbst, C3),
        ("nur Zielstatus, keine Menge", nur_ziel, C4),
        ("weiterhin ohne Daten", nichts, "#C8CDD2"),
    ]
    fig, ax = plt.subplots(figsize=(5.8, 2.1))
    left = 0
    for label, val, color in teile:
        ax.barh(0, val, left=left, height=0.5, color=color, zorder=3,
                edgecolor="white", linewidth=1.6)
        if val > 22:
            ax.text(left + val / 2, 0, str(val), ha="center", va="center",
                    fontsize=8.5, color="white", fontweight="bold")
        left += val
    ax.set_xlim(0, n_total)
    ax.set_ylim(-1.15, 0.45)
    ax.set_yticks([])
    ax.set_xlabel(f"Firmen im S&P 500 (n = {n_total})")
    ax.set_title("Abdeckung ist nicht gleich Abdeckung")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in teile]
    ax.legend(handles, [t[0] for t in teile], fontsize=7, ncol=2,
              loc="upper left", bbox_to_anchor=(0, 0.42), handlelength=1.1)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    return _save(fig, "datenart")


def fig_dimensionen(dim: pd.DataFrame) -> str:
    """Abdeckung und Unabhaengigkeit der vier neuen Dimensionen."""
    d = dim.sort_values("indexfirmen")
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(6.1, 2.9), gridspec_kw={"width_ratios": [1.35, 1]}
    )
    y = np.arange(len(d))
    ax1.barh(y, d["indexfirmen"], height=0.5, color=C1, zorder=3, label="erreichte Firmen")
    ax1.barh(y, d["neu"], height=0.5, color=C3, zorder=4, label="davon neu")
    for i, (tot, neu) in enumerate(zip(d["indexfirmen"], d["neu"])):
        ax1.text(tot + 6, i, f"{tot}", va="center", fontsize=7.5, color=INK_SOFT)
    ax1.set_yticks(y)
    ax1.set_yticklabels(d["quelle"], fontsize=8)
    ax1.set_xlim(0, 380)
    ax1.set_xlabel("Indexfirmen")
    ax1.set_title("Reichweite")
    ax1.legend(fontsize=7, loc="lower right")
    _clean(ax1)

    absr = d["rho_zu_co2"].abs()
    colors = [C3 if v < 0.3 else C4 for v in absr]
    ax2.barh(y, absr, height=0.5, color=colors, zorder=3)
    for i, (v, raw) in enumerate(zip(absr, d["rho_zu_co2"])):
        ax2.text(v + 0.015, i, f"{raw:+.2f}", va="center", fontsize=7.5, color=INK_SOFT)
    ax2.axvline(0.3, color=INK_SOFT, linewidth=0.9, linestyle="--", zorder=4)
    ax2.set_yticks(y)
    ax2.set_yticklabels([])
    ax2.set_xlim(0, 0.72)
    ax2.set_xlabel("|Rangkorrelation| zur CO$_2$-Intensitaet")
    ax2.set_title("Unabhaengigkeit")
    _clean(ax2)
    fig.subplots_adjust(wspace=0.12)
    return _save(fig, "neue_dimensionen")


def fig_dimension_abdeckung(cov: pd.DataFrame) -> str:
    """Sektorabdeckung vor und nach den neuen Dimensionen."""
    d = cov.sort_values("pct_neu")
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    ax.barh(y + 0.19, d["pct_neu"], height=0.36, color=C3, zorder=3,
            label="mit neuen Dimensionen")
    ax.barh(y - 0.19, d["pct_heute"], height=0.36, color=C1, zorder=3,
            label="nur Emissionsdaten")
    for i, (a, b) in enumerate(zip(d["pct_heute"], d["pct_neu"])):
        ax.text(b + 1.5, i + 0.19, f"{b:.0f}", va="center", fontsize=7, color=INK_SOFT)
        ax.text(a + 1.5, i - 0.19, f"{a:.0f}", va="center", fontsize=7, color=INK_SOFT)
    ax.set_yticks(y)
    ax.set_yticklabels(d["gics_sector"], fontsize=8)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Anteil der Firmen mit mindestens einer Kennzahl (%)")
    ax.set_title("Nur die Finanzbranche bleibt weitgehend blind")
    ax.legend(loc="lower right", fontsize=7.5)
    _clean(ax)
    return _save(fig, "dimension_abdeckung")
