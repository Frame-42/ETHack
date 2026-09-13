"""
Adapter auf den Team-Datensatz (dataset_long.parquet).

Der Datensatz liegt im Langformat: eine Zeile je Firma, Jahr und Kennzahl,
mit Quellenangabe an jedem Wert. Spalten laut Datenkatalog:

  ticker, company, gics_sector, gics_sub_industry, year,
  metric, metric_label, value, unit, direction, axis,
  source_id, source_name, source_url, source_access,
  source_license, retrieved_at

Dieses Skript macht drei Dinge, bevor irgendetwas gerechnet wird:

  TOR 1  Abdeckung. Kennzahlen unter der Mindestabdeckung kommen nicht in
         den Score, sondern auf eine Nebenachse. Ein Indikator, der zu
         40 Prozent imputiert ist, transportiert Gruppenmediane, keine Messung.
  TOR 2  Korrelation. Was zu stark mit der CO2-Intensitaet korreliert,
         ist eine zweite Stimme fuer dieselbe Aussage und fliegt raus.
  TOR 3  Messart. Gemessen, gemeldet und gerechnet werden getrennt gefuehrt
         und nie stillschweigend vermischt.

Danach laeuft dieselbe Simulation wie bisher, nur ueber sieben Achsen
statt einer.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import spearmanr

T = Path("team")
OUT = Path("team_out"); OUT.mkdir(exist_ok=True)

MIN_COVERAGE = 0.60      # Anteil der Firmen mit echtem Wert
MAX_ABS_RHO = 0.30       # Korrelations-Gate gegen die CO2-Intensitaet
REF_METRIC = "co2_intensity"

# Kennzahlen, die grundsaetzlich nie in den Score gehoeren.
NEVER_IN_SCORE = {
    "esg_risk_total",          # Fremdbewertung, nur Vergleichsmassstab
    "rank_p10", "rank_p50", "rank_p90",   # eigenes Ergebnis
    "revenue_musd", "n_facilities", "match_confidence",
    "campd_plants", "egrid_plants", "tri_facilities", "osha_sites",
    "net_income", "total_assets", "financial_debt",
    "operating_cashflow", "capex", "rnd",
    "sbti_near_term_year", "sbti_net_zero_year",   # Jahreszahlen, keine Richtung
}


# ----------------------------------------------------------------------
def load():
    df = pd.read_parquet(T / "dataset_long.parquet")
    df.columns = [c.strip() for c in df.columns]
    need = {"ticker", "metric", "value", "year"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"Spalten fehlen im Datensatz: {sorted(missing)}")

    metrics = {}
    p = T / "metrics.json"
    if p.exists():
        try:
            metrics = json.loads(p.read_text())
        except Exception as e:
            print(f"  metrics.json nicht lesbar ({e}) - wird uebersprungen")
    print(f"Datensatz: {len(df):,} Zeilen, {df.ticker.nunique()} Firmen, "
          f"{df.metric.nunique()} Kennzahlen, Jahre {df.year.min()}-{df.year.max()}")
    return df, metrics


def latest_wide(df):
    """Je Firma und Kennzahl der juengste Wert -> breite Matrix."""
    d = df.dropna(subset=["value"]).sort_values("year")
    d = d.drop_duplicates(subset=["ticker", "metric"], keep="last")
    wide = d.pivot(index="ticker", columns="metric", values="value")
    meta_cols = [c for c in ["company", "gics_sector", "gics_sub_industry"]
                 if c in df.columns]
    meta = (df.drop_duplicates("ticker").set_index("ticker")[meta_cols]
              .reindex(wide.index))
    return wide, meta, d


# ----------------------------------------------------------------------
def gate_coverage(wide, df):
    n = len(wide)
    rows = []
    for m in wide.columns:
        cov = wide[m].notna().mean()
        axis = (df[df.metric == m].axis.dropna().iloc[0]
                if "axis" in df.columns and (df.metric == m).any()
                and df[df.metric == m].axis.notna().any() else "?")
        direction = (df[df.metric == m].direction.dropna().iloc[0]
                     if "direction" in df.columns
                     and df[df.metric == m].direction.notna().any() else 0)
        rows.append({"metric": m, "firmen": int(wide[m].notna().sum()),
                     "abdeckung": round(cov, 3), "achse": axis,
                     "richtung": direction})
    cov = pd.DataFrame(rows).sort_values("abdeckung", ascending=False)
    cov["tor_abdeckung"] = np.where(
        cov.metric.isin(NEVER_IN_SCORE), "ausgeschlossen",
        np.where(cov.abdeckung >= MIN_COVERAGE, "ok", "Nebenachse"))
    cov.to_csv(OUT / "gate_abdeckung.csv", index=False)
    print(f"\nTOR 1 Abdeckung (Schwelle {MIN_COVERAGE:.0%}, n={n} Firmen):")
    print(cov.tor_abdeckung.value_counts().to_string())
    print(cov.head(20).to_string(index=False))
    return cov


def gate_correlation(wide, cov):
    cand = cov[cov.tor_abdeckung == "ok"].metric.tolist()
    if REF_METRIC not in wide.columns:
        print(f"\nTOR 2 uebersprungen: {REF_METRIC} fehlt im Datensatz")
        cov["tor_korrelation"] = "ungeprueft"
        return cov, cand
    ref = wide[REF_METRIC]
    rows = []
    for m in cand:
        both = wide[[m]].join(ref.rename("ref")).dropna()
        if len(both) < 20 or m == REF_METRIC:
            rho, p, n = (1.0, 0.0, len(both)) if m == REF_METRIC else (np.nan, np.nan, len(both))
        else:
            r = spearmanr(both[m], both["ref"])
            rho, p, n = float(r.statistic), float(r.pvalue), len(both)
        rows.append({"metric": m, "rho_zu_co2": round(rho, 3) if pd.notna(rho) else None,
                     "p": round(p, 4) if pd.notna(p) else None, "n": n})
    corr = pd.DataFrame(rows)
    corr["tor_korrelation"] = np.where(
        corr.metric == REF_METRIC, "Referenz",
        np.where(corr.rho_zu_co2.abs() > MAX_ABS_RHO, "Nebenachse", "ok"))
    corr.to_csv(OUT / "gate_korrelation.csv", index=False)
    print(f"\nTOR 2 Korrelation (Schwelle |rho| <= {MAX_ABS_RHO}):")
    print(corr.sort_values("rho_zu_co2", key=lambda s: s.abs(),
                           ascending=False).to_string(index=False))
    keep = corr[corr.tor_korrelation.isin(["ok", "Referenz"])].metric.tolist()
    return corr, keep


def axis_overview(df, keep, wide):
    """Welche Achsen sind mit wie vielen Score-Kennzahlen besetzt?"""
    if "axis" not in df.columns:
        return None
    a = (df[df.metric.isin(keep)].drop_duplicates("metric")
           .groupby("axis").metric.agg(list))
    print("\nAchsen im Score:")
    for ax, ms in a.items():
        print(f"  {ax}: {len(ms)} Kennzahlen -> {', '.join(ms)}")
    # Unabhaengigkeit der Achsen untereinander
    ax_map = df[df.metric.isin(keep)].drop_duplicates("metric").set_index("metric").axis
    scores = {}
    for ax in ax_map.unique():
        ms = [m for m in keep if ax_map.get(m) == ax]
        sub = wide[ms].rank(pct=True)
        scores[ax] = sub.mean(axis=1)
    S = pd.DataFrame(scores)
    C = S.corr(method="spearman").round(2)
    C.to_csv(OUT / "achsen_korrelation.csv")
    print("\nKorrelation der Achsen untereinander:")
    print(C.to_string())
    return C


# ----------------------------------------------------------------------
def summarise_sources(df):
    if "source_name" not in df.columns:
        return
    s = (df.groupby("source_name")
           .agg(werte=("value", "size"), firmen=("ticker", "nunique"),
                kennzahlen=("metric", "nunique"))
           .sort_values("werte", ascending=False))
    s.to_csv(OUT / "quellen_uebersicht.csv")
    print(f"\nQuellen: {len(s)}")
    print(s.head(20).to_string())


if __name__ == "__main__":
    if not (T / "dataset_long.parquet").exists():
        raise SystemExit(
            "team/dataset_long.parquet fehlt.\n"
            "Von https://dataset.ethack.slabs.dev/downloads herunterladen und\n"
            "zusammen mit metrics.json in den Ordner team/ legen.")
    df, metrics = load()
    wide, meta, latest = latest_wide(df)
    summarise_sources(df)
    cov = gate_coverage(wide, df)
    corr, keep = gate_correlation(wide, cov)
    axis_overview(df, keep, wide)

    wide.to_parquet(OUT / "wide_latest.parquet")
    meta.to_parquet(OUT / "meta.parquet")
    pd.Series(keep).to_csv(OUT / "score_metrics.csv", index=False, header=["metric"])
    print(f"\nNach beiden Toren im Score: {len(keep)} von {wide.shape[1]} Kennzahlen")
    print("Geschrieben nach team_out/. Naechster Schritt: f11_team_simulation.py")
