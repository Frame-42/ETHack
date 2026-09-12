"""Download SEC XBRL companyfacts JSON for every CIK in constituents.csv.

Usage: python3 fetch_sec_facts.py <out_dir>
Respects SEC's 10 requests/second fair-access limit; already-downloaded
files are skipped, so the script can be re-run to resume.
"""
import csv
import gzip
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
USER_AGENT = os.environ.get("SEC_USER_AGENT", "ETHack research project admin@ethack-research.org")
MAX_PER_SECOND = 8
PREDECESSOR_CIKS = [34088]  # ExxonMobil before its 2026 re-registration (see financial_health.py)

_lock = threading.Lock()
_last = [0.0]


def throttle():
    with _lock:
        wait = _last[0] + 1 / MAX_PER_SECOND - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def fetch(cik, out_dir):
    path = os.path.join(out_dir, f"{cik}.json")
    if os.path.exists(path):
        return cik, "cached"
    req = urllib.request.Request(URL.format(cik), headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    for attempt in range(4):
        throttle()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            with open(path + ".tmp", "wb") as f:
                f.write(body)
            os.replace(path + ".tmp", path)
            return cik, "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return cik, "404"
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    return cik, "failed"


def main():
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    with open("constituents.csv", newline="") as f:
        ciks = sorted({int(row["CIK"]) for row in csv.DictReader(f)} | set(PREDECESSOR_CIKS))
    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for cik, status in pool.map(lambda c: fetch(c, out_dir), ciks):
            results.setdefault(status, []).append(cik)
    for status, items in results.items():
        print(f"{status}: {len(items)}" + (f" {items}" if status in ("404", "failed") else ""))


if __name__ == "__main__":
    main()
