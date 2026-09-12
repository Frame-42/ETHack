"""Firmenlogos für den Datenbrowser, selbst gehostet.

Zwei Schritte:

1. **Website je Firma.** Aus Wikidata (CC0) über die SEC-Kennung CIK
   (Eigenschaft P5531) und die offizielle Website (P856). Wo Wikidata nichts
   hat, aus dem Feld ``website`` der SEC-Submissions-Schnittstelle.
2. **Logo.** Das Favicon der Domain über Googles Favicon-Dienst in 64 px.
   Liefert der Dienst sein Standard-Weltkugel-Symbol, gilt die Firma als ohne
   Logo -- ein Platzhalter ist ehrlicher als ein falsches Bild.

Die Bilder werden beim Bauen geladen und unter ``web/public/logos`` abgelegt.
Die Seite fragt damit zur Laufzeit keinen fremden Server an. Logos sind Marken
der jeweiligen Firmen und dienen nur der Wiedererkennung.

Herkunft je Logo: ``data/out/logos.csv``.
"""
from __future__ import annotations

import hashlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from pipeline.config import OUT, RAW, ROOT, USER_AGENT

LOGOS = ROOT / "web" / "public" / "logos"
WIKIDATA = "https://query.wikidata.org/sparql"
QUERY = """
SELECT ?cik ?website WHERE {
  ?item wdt:P5531 ?cik .
  ?item wdt:P856 ?website .
}
"""
FAVICON = "https://www.google.com/s2/favicons?domain={domain}&sz=64"
SEC = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
HEADERS = {"User-Agent": USER_AGENT}


def domain_of(url: str) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    u = url.strip()
    if "://" not in u:
        u = "https://" + u
    host = urlparse(u).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host or None


def wikidata_websites() -> pd.DataFrame:
    r = requests.get(
        WIKIDATA, params={"query": QUERY},
        headers={**HEADERS, "Accept": "text/csv"}, timeout=180,
    )
    r.raise_for_status()
    from io import StringIO

    w = pd.read_csv(StringIO(r.text), dtype=str)
    w["cik"] = pd.to_numeric(w["cik"].str.lstrip("0"), errors="coerce")
    w = w.dropna(subset=["cik"]).drop_duplicates("cik")
    w["cik"] = w["cik"].astype(int)
    w["website_source"] = "Wikidata P856 (CC0), verknuepft ueber CIK P5531"
    return w


def sec_website(cik: int) -> str | None:
    try:
        r = requests.get(SEC.format(cik=cik), headers=HEADERS, timeout=60)
        if r.status_code != 200:
            return None
        d = r.json()
        return d.get("website") or d.get("investorWebsite") or None
    except requests.RequestException:
        return None
    finally:
        time.sleep(0.12)  # SEC erlaubt 10 Anfragen je Sekunde


def main() -> None:
    master = pd.read_parquet(RAW / "sp500_master.parquet")
    master["cik"] = master["cik"].astype(int)
    df = master.merge(wikidata_websites(), on="cik", how="left")

    missing = df["website"].isna()
    for i in df[missing].index:
        site = sec_website(int(df.at[i, "cik"]))
        if site:
            df.at[i, "website"] = site
            df.at[i, "website_source"] = "SEC Submissions, Feld website"
    df["domain"] = df["website"].map(domain_of)

    LOGOS.mkdir(parents=True, exist_ok=True)
    default = requests.get(
        FAVICON.format(domain="diesedomaingibtesnicht-ethack-4711.com"), timeout=30
    ).content
    default_hash = hashlib.sha256(default).hexdigest()

    def fetch(row) -> dict:
        out = {"ticker": row.ticker, "domain": row.domain, "logo_file": None}
        if not row.domain:
            return out
        try:
            r = requests.get(FAVICON.format(domain=row.domain), timeout=30)
        except requests.RequestException:
            return out
        if r.status_code != 200 or hashlib.sha256(r.content).hexdigest() == default_hash:
            return out
        path = LOGOS / f"{row.ticker}.png"
        path.write_bytes(r.content)
        out["logo_file"] = f"logos/{row.ticker}.png"
        return out

    with ThreadPoolExecutor(max_workers=6) as pool:
        got = pd.DataFrame(list(pool.map(fetch, df.itertuples(index=False))))

    prov = df[["ticker", "company", "website", "website_source", "domain"]].merge(
        got[["ticker", "logo_file"]], on="ticker", how="left"
    )
    prov["logo_url"] = prov["domain"].map(
        lambda d: FAVICON.format(domain=d) if isinstance(d, str) else None
    )
    prov["logo_source"] = prov["logo_file"].map(
        lambda f: "Google-Favicon-Dienst, Marke der jeweiligen Firma" if isinstance(f, str) else None
    )
    prov["retrieved_at"] = date.today().isoformat()
    prov.to_csv(OUT / "logos.csv", index=False)

    print(f"Website gefunden: {prov['website'].notna().sum()} von {len(prov)}")
    print(prov["website_source"].value_counts().to_string())
    print(f"Logo gespeichert: {prov['logo_file'].notna().sum()} von {len(prov)} -> {LOGOS}")


if __name__ == "__main__":
    main()
