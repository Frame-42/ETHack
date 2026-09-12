# After the Pledge

A working sustainability research framework for the S&P 500, with a separate $1 billion net-zero investment scenario.

**500 companies in scope. 217 matched public assessments. 71 with nature data. No invented ESG observations.**

The central finding is awkward: 216 of the 217 matched companies receive WBA's lowest climate-contribution category. A polished ranking cannot solve that measurement limit. This project shows it, exposes the scoring choices and keeps unassessed companies visible.

## Run

Requires Node.js 20+. No install is required to view or rebuild the app.

```sh
npm start
```

Open **http://127.0.0.1:4173**. The frozen data works without external network requests. `PORT=8080 npm start` selects another port. Stop with Ctrl-C.

```sh
npm run build:data   # regenerate both rankings, coverage and results from the committed snapshot
npm test            # model, dataset, portfolio and server invariants
```

For real-browser checks:

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

The browser test starts its own server. Screenshots are written to `test-results/`.

## What to look at

- **Company observatory:** an ordinal evidence matrix, sector/search filters, adjustable weights, two comparison lenses, company comparisons and source-linked evidence files.
- **Method & sources:** definitions, equations, missing-data bounds, sector coverage and downloadable research files.
- **The $1bn question:** a fully allocated portfolio, business rationales, visible data gaps, concentration constraints and explicit stress assumptions.

Start with the [research memo](docs/methodology.md), [computed results](docs/results.md) and [investment memo](docs/portfolio.md). The baseline core score is 50% climate contribution, 20% plan quality and 30% social evidence. The separate nature lens requires all four pillars. Fifteen modelling scenarios per lens expose rank sensitivity. None of these scores is a measured amount of environmental benefit or an expected return.

## Data and reproduction

`data/raw/constituents.csv` freezes the DataHub constituent mirror; `data/raw/snapshot.json` retains the extracted WBA observations, company IDs, matching decisions, original profile strings, timestamps and source SHA-256 hashes. `data/raw/directory.json` preserves the returned WBA directory. `data/aliases.json` is the seven-name manual crosswalk. `data/processed/` contains browser data and both complete-universe ranking CSVs; unranked issuers have empty scores and explicit bounds.

To recollect the public sources:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/collect.py
npm run build:data
```

The collector caches original HTML under ignored `data/cache/`. Re-running reuses cache; archive that directory before deliberately refreshing, then inspect the diff. The app build is deterministic from committed extracted data. Recollection from live websites is not guaranteed to reproduce older bytes. The collector uses public pages, no authenticated API or account.

Upstream WBA data is attributed under [CC BY 4.0](https://www.worldbenchmarkingalliance.org/disclaimer). The [DataHub constituent mirror](https://github.com/datasets/s-and-p-500-companies) has separate upstream terms and is not an official point-in-time S&P index history. Our score transformations, uncertainty treatment and scenario portfolio are independent work and are not endorsed by either source.

## Limits that affect the answer

Coverage is selective; the nature cohort excludes whole sectors. Assessments are disclosure-based and reporting dates vary. The model uses ordinal value mappings and subjective weights. There are no harmonised emissions histories, prices, financial ratios or measured avoided emissions in the scoring model. The investment scenario therefore supplies a concrete allocation and stress arithmetic, not a fitted optimiser, a historical backtest or executable orders at known prices.

The small dependency-free frontend shares its scoring functions with the data build and tests. No backend, credentials or cloud deployment is needed.
