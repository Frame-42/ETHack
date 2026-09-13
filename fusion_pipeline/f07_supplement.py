"""Zusatzachsen: gemessen, aber nicht im Score (zu geringe Abdeckung
oder zu hohe Korrelation). Werden nur fuer die Firmen ausgewiesen,
die sie tatsaechlich haben - ohne Imputation."""
import numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import spearmanr
F = Path("fusion")

bands = pd.read_parquet(F / "out_rank_bands.parquet")
tri = pd.read_parquet(F / "src_tri.parquet")
osha = pd.read_parquet(F / "src_osha.parquet")
fin = pd.read_parquet("build/src_financials.parquet").set_index("company_id")

d = bands[["company_id", "ticker", "company_name", "gics_sector",
           "profile_group", "median_pct"]].copy()
d = d.merge(tri[["company_id", "tri_kg", "karzinogen_anteil"]], on="company_id", how="left")
d = d.merge(osha[["company_id", "unfallrate", "faelle", "stunden"]], on="company_id", how="left")
d["revenue_musd"] = d.company_id.map(fin.revenue_usd / 1e6)
d["tri_je_musd"] = d.tri_kg / d.revenue_musd
d.to_csv(F / "out_supplement.csv", index=False)

for name, col in [("Giftstoffe je Mio. USD", "tri_je_musd"),
                  ("Arbeitsunfallrate", "unfallrate")]:
    sub = d.dropna(subset=[col, "median_pct"])
    r = spearmanr(sub[col], sub.median_pct)
    print(f"{name:26s} n={len(sub):3d}  median={sub[col].median():8.2f}  "
          f"rho zum Score = {r.statistic:+.2f} (p={r.pvalue:.2f})")
print(f"\nAbdeckung: TRI {d.tri_kg.notna().sum()}/116, OSHA {d.unfallrate.notna().sum()}/116")
