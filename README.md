# ETHack sustainability framework

A transparent way to examine sustainability evidence for S&P 500 companies: trace the observations, compare operational climate performance, see how much the result depends on modeling choices, and assess economic viability separately.

Start with **[the plain-language explanation](docs/FRAMEWORK.md)** to understand why company reports still need interpretation before comparison, why we also use facility records, and how each framework step addresses that problem. Read **[the technical explanation](docs/TECHNICAL.md)** for equations, assumptions, data definitions, and the complete workflow.

The retained snapshot contains **11,425 observations across 500 issuers and 44 metrics**. Of those issuers, **449** have sustainability-related observations and **127** have a saved climate percentile band. These figures describe this repository's snapshot, not current index coverage. The framework does not establish that a company is sustainable in an absolute sense.

## Open Dashboard 2

Open **[dashboard.html](dashboard.html)** in a browser; it works offline. This is the English version of Ali’s `dashboard (2).html` from main (`b0692c4`). Its embedded four-axis results cover 503 securities and retain all original numerical values. The upload did not include their generating code. They are a separate supplied snapshot, not a rebuild of the cleaned pipeline outputs below. The dashboard preserves company views, rankings, comparisons, portfolio illustrations, patterns, and methodology notes.

## Use the saved data

Python 3.12 is the tested runtime. From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/08_validate.py
.venv/bin/python -m unittest discover -s tests -v
```

Validation is offline and leaves the data unchanged. No API keys are needed to read or validate the snapshot.

## Repository contents

| Location | Purpose |
|---|---|
| `dashboard.html` | English Dashboard 2, with embedded snapshot and provenance |
| `dashboard_v11.html` | Dashboard 11, with embedded company data and illustrative portfolios rebuilt by `scripts/rebuild_dashboard11_portfolios.py` |
| `pipeline/` | Source connectors, attribution, climate scoring, quality review, evidence assessment, and economic viability |
| `scripts/` | Numbered entry points and offline validation |
| `fusion_pipeline/` | A separate, self-contained fusion pipeline (German-language stage scripts `f01`-`f18` plus helpers) supplied by a teammate; not wired into `pipeline/` or `scripts/` |
| `constituents.csv` | Membership snapshot: 503 securities representing 500 CIKs |
| `data/external/team/` | Team source snapshots and an English input dictionary |
| `data/out/dataset_long.csv` | Source observations and aggregates, with units, provenance, and review annotations |
| `data/out/climate_bands.csv` | Saved derived climate percentiles |
| `data/out/economic_viability.csv` | Separate derived cash-flow capacity assessment |
| `data/out/reliability.csv` | Evidence availability by issuer and pillar |
| `data/out/reviewed_flags.csv` | Findings, evidence, archived model advice, and final review status |
| `data/out/metrics.json`, `sources.json` | Metric and source dictionaries |
| `data/out/snapshot_summary.json` | Counts reproduced by the validator |
| `data/review/decisions.csv` | Human decisions keyed to a finding's evidence |
| `docs/` | The accessible explanation and technical reference |
| `tests/` | Framework regression checks |

## Refresh from sources

The source caches and SEC companyfacts files are **not included**. A fresh download is a new data build; it cannot guarantee identical historical results. API access, source formats, and available releases may have changed. Membership stays fixed to constituents.csv unless you deliberately update it.

```bash
cp .env.example .env
# Enter your own SEC contact information and any required API keys.
.venv/bin/python scripts/01_fetch.py
.venv/bin/python scripts/02_analyze.py
.venv/bin/python scripts/03_aggregate.py
.venv/bin/python scripts/04_dataset.py
.venv/bin/python scripts/06_review.py
.venv/bin/python scripts/05_reliability.py
.venv/bin/python scripts/07_economy.py fetch data/raw/sec_facts
.venv/bin/python scripts/07_economy.py score data/raw/sec_facts
.venv/bin/python scripts/08_validate.py --write-summary
```

Review precedes the final reliability calculation so the evidence summary sees current quality annotations. `scripts/06_review.py --ai` optionally requests paid model advice; ordinary review uses deterministic rules. See the technical reference before interpreting or rebuilding the historical outputs.
