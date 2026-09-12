"""Snapshot publicly displayed WBA assessments; no account or API key required.

Raw responses are cached, checksummed and never silently replaced. Re-running
uses the cache. To refresh, archive data/cache first and review the data diff.
"""
import csv
import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cache"
RAW = ROOT / "data/raw"
BASE = "https://www.worldbenchmarkingalliance.org"
UNIVERSE = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"


def fetch(url, key, form=None):
    path = CACHE / key
    if not path.exists():
        args = ["curl", "-sSfL", "--retry", "2", "--max-time", "60", url]
        if form:
            args += ["-H", "X-Requested-With: XMLHttpRequest", "--data", form]
        payload = subprocess.check_output(args)
        path.write_bytes(payload)
    payload = path.read_bytes()
    return payload, {"url": url, "sha256": hashlib.sha256(payload).hexdigest(),
                     "retrieved_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                     "cache_file": key}


def normalize(name):
    name = re.sub(r"\(class [abc]\)", "", name.lower())
    name = re.sub(r"\b(incorporated|inc|corporation|corp|company|co|plc|limited|ltd|the)\b", "", name)
    return re.sub(r"[^a-z0-9]", "", name)


def parse_assessment(payload):
    soup = BeautifulSoup(payload, "html.parser")
    scores = {}
    for row in soup.select(".score-tab .t-row"):
        tag = row.select_one(".tag")
        value = row.select_one(".t-sub-score")
        if tag and value:
            match = re.fullmatch(r"(\d+(?:\.\d+)?)/100", value.get_text(strip=True))
            if match:
                scores[tag.get_text(" ", strip=True)] = float(match[1])
    narrative = soup.select_one(".company-benchmark-act-text-col")
    text = narrative.get_text(" ", strip=True) if narrative else ""
    tpq = re.search(r"transition plan quality \(TPQ\).*?scores (\d+(?:\.\d+)?) out of 5", text)
    ctt = re.search(r"contribution to the low-carbon transition \(CTT\).*?scores (\d+(?:\.\d+)?) out of 2", text)
    grade = soup.select_one(".t-act-score")
    footprint = {}
    for label in soup.select(".stat-label"):
        value = label.find_next_sibling("h4")
        if value:
            footprint[label.get_text(" ", strip=True)] = value.get_text(" ", strip=True)
    return {"tpq": float(tpq[1]) if tpq else None,
            "ctt": float(ctt[1]) if ctt else None,
            "act_grade": grade.get_text(" ", strip=True) if grade else None,
            "nature": scores.get("Nature Benchmark"),
            "social": scores.get("Social Benchmark"),
            "just_transition": scores.get("Just Transition"),
            "footprint_context_only": footprint,
            "assessment_cycle": 2026}


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    universe, universe_source = fetch(UNIVERSE, "constituents.csv")
    directory, directory_source = fetch(BASE + "/companies-listing/ajax/update-block", "directory.json",
                                         "column_id=original-col&limit=2000")
    html = next(x["data"] for x in json.loads(directory) if x["command"] == "insert")
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for row in soup.select("tr[data-url]"):
        label = row.select_one(".t-comp-name")
        if label:
            entries.append({"name": label.get_text(" ", strip=True), "path": row["data-url"],
                            "id": label["data-company-id"]})
    lookup = {}
    for entry in entries:
        lookup.setdefault(normalize(entry["name"]), []).append(entry)
    aliases = json.loads((ROOT / "data/aliases.json").read_text())
    constituents = list(csv.DictReader(universe.decode("utf-8-sig").splitlines()))
    # CIK identifies issuers: combine share classes so Alphabet does not count twice.
    issuers = {}
    for c in constituents:
        key = c["CIK"].zfill(10)
        if key in issuers:
            issuers[key]["tickers"].append(c["Symbol"])
            continue
        issuers[key] = {"cik": key, "ticker": c["Symbol"], "tickers": [c["Symbol"]],
                        "name": c["Security"], "sector": c["GICS Sector"],
                        "industry": c["GICS Sub-Industry"]}
    matches = []
    for company in issuers.values():
        name = aliases.get(company["ticker"], company["name"])
        candidates = lookup.get(normalize(name), [])
        company["match_method"] = "unmatched"
        company["wba"] = None
        if len(candidates) == 1:
            company["match_method"] = "reviewed_alias" if company["ticker"] in aliases else "normalized_exact"
            company["wba"] = candidates[0]
            matches.append(company)

    def load(company):
        entry = company["wba"]
        payload, source = fetch(BASE + entry["path"], entry["id"] + ".html")
        result = parse_assessment(payload)
        result["source"] = source
        company["assessment"] = result
        return company

    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, _ in enumerate(pool.map(load, matches), 1):
            if i % 25 == 0:
                print(f"Read {i}/{len(matches)} public company pages", flush=True)
    output = {"snapshot_date": datetime.now(timezone.utc).date().isoformat(),
              "universe_source": universe_source, "directory_source": directory_source,
              "directory_rows_returned": len(entries), "directory_headline_count": 2000,
              "security_count": len(constituents), "companies": list(issuers.values())}
    (RAW / "snapshot.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    (RAW / "constituents.csv").write_bytes(universe)
    (RAW / "directory.json").write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
    print(f"Saved {len(issuers)} issuers, {len(matches)} matched, {len(entries)} WBA directory rows")


if __name__ == "__main__":
    main()
