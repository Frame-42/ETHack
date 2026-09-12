#!/usr/bin/env bash
# Holt die im Datenbrowser getroffenen Entscheidungen vom Server ins Repo.
# Danach: python scripts/10_pruefung.py --ai && python scripts/07_dataset.py
set -euo pipefail
cd "$(dirname "$0")/.."
URL="${DATENBROWSER_URL:-http://sleepyserver:3810}"
curl -fsS "$URL/api/entscheidungen?format=csv" -o data/review/entscheidungen.csv
echo "$(($(wc -l < data/review/entscheidungen.csv) - 1)) Entscheidungen nach data/review/entscheidungen.csv geholt"
