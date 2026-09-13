# Technical explanation and reproducibility reference

> **Dashboard 2:** [Open the dashboard](../dashboard.html). Ali’s supplied four-axis snapshot retains 503 securities, including share classes; 147 meet its comparison threshold and 129 have all four axes. Its one-year viability reconstruction and portfolio illustrations are separate from the reproducible climate/evidence/historical-viability pipeline documented here. The generating code was absent from main commit `b0692c4`; cleanup preserves all 22,050 numeric and boolean values rather than inventing a rebuild. Missing records are labeled as coverage gaps, and percentile ranges are not treated as confidence intervals.

This reference describes the executable framework and the retained snapshot. The [introductory explanation](FRAMEWORK.md) develops the motivation and practical examples. Code links below identify implementation choices; paper citations support the methodological rationale, not the validity of the project's numerical thresholds.

## 1. Estimand and scope

The climate output is a distribution of **within-peer percentile positions for partial operational emissions performance**, conditional on observed data and sampled modeling assumptions. It is neither a complete ESG rating nor an estimate of absolute sustainability. The three other outputs describe evidence availability, contextual warning signals, and cash-flow capacity.

The membership file contains 503 securities and 500 distinct SEC CIKs. Share classes are mapped to a primary symbol by descending symbol length, then lexical order. This is a deterministic naming convention, not a statement about voting rights. Dots in ticker symbols are normalized to hyphens. The retained climate band for GOOG is identified as GOOGL after this issuer mapping; its numerical percentiles were preserved.

The membership snapshot is applied retrospectively and is subject to survivorship bias. GICS sectors are broad, sub-industries may be sparse, and the subsidiary map is curated rather than a complete historical corporate-ownership database. [`universe.py`](../pipeline/universe.py), [`resolve.py`](../pipeline/resolve.py).

## 2. Data contract and provenance

`data/out/dataset_long.csv` has a unique `(ticker, year, metric)` key. All 11,425 original numerical observations were retained during cleanup. Its 44 metrics span 13 source families with observations; the source catalog also documents auxiliary sources.

| Field | Meaning |
|---|---|
| `ticker`, `company`, `gics_sector`, `gics_sub_industry` | Issuer identity and peer metadata |
| `year` | Assigned reporting/snapshot year; see the period caveats below |
| `metric`, `metric_label`, `value`, `unit` | Stable metric identifier, English label, numerical observation, and unit |
| `direction` | -1: lower is preferred; +1: higher; 0: contextual |
| `axis` | A: environmental observations; S: social; G: compliance-related governance; B: targets/assessment context; meta: supporting fields; comparison: external benchmark |
| `value_type` | `reported` or `aggregated`; source category encodings are included in `reported` |
| `source_id`, `source_name`, `source_url`, `source_access`, `source_license` | Source-family reference and access/reuse notes |
| `assembled_at` | Date assigned by the export build, **not a verified source retrieval timestamp** |
| `partial_year` | Marks current-year CAMPD quantities as incomplete in the configured export |
| `quality_status`, `quality_rule`, `quality_note` | `ok`, `review`, or `error`, with the rule and rationale |

Source URLs often identify a dataset or endpoint, not an exact company filing or underlying facility row. Detailed accession numbers and source references exist in the team inputs, but row-level lineage is not complete for every consolidated observation. `metrics.json` and `sources.json` are the dictionaries. The team CSV's former embedded explanation row is now `hard_variables_dictionary.json`.

The `reported` label is intentionally modest: it includes source-reported assessments and coded statuses, not just physical measurements. Currency/unit conversions and ownership-weighted sums are transformations. In particular, an unexpired-target flag depends on the build year. A Form SD filing flag says nothing about responsible sourcing.

Period caveats in the retained data must not be repaired by guessing: WHD's 2024 label summarizes findings ending in 2022-2024; ECHO has a rolling multi-year history; Form SD's historical 2025 output label refers to a team snapshot containing some 2026 filing dates. WBA uses its snapshot assessment year. Future eGRID aggregation preserves the year in the downloaded file rather than assigning 2023 to a newer release. CAMPD and eGRID measure CO2, so their units are `t CO2`; GHGRP's combined gases use `t CO2e`. These label corrections do not rescale any stored value.

Different emissions sources overlap. Never add GHGRP, CAMPD, and eGRID totals as if they were disjoint contributions to a corporate footprint.

## 3. Facility attribution and observation construction

GHGRP facility and emissions records join on `(facility_id, year)`. The connector separates direct emitters from suppliers and injection and excludes biogenic CO2 from this total. Nonpositive reported quantities are excluded from the climate panel; no-match and no-report states are not treated as evidence of zero impact.

For facility \(f\), issuer \(i\), and year \(t\), the attributed total is

\[
E_{it}=\sum_f s_{fit}e_{ft},
\]

where \(s_{fit}\) is the parsed ownership share. Missing shares divide the residual equally among named owners; totals above 1.01 are rescaled. These are allocation assumptions, not verified legal ownership. Exact names, curated subsidiaries, and fuzzy matching are distinguished through `match_method` and heuristic `match_confidence`. The fuzzy cutoff is 92. Selected acquisitions and separations have inclusive year bounds.

CAMPD parses owner and operator roles but its exported owner attribution does **not** apply ownership fractions: a jointly owned plant can be fully attributed to multiple matching owners. eGRID uses operator/utility names. ECHO links through FRS IDs and the first listed GHGRP parent. TRI, OSHA, and WHD use conservative name matching without the GHGRP fuzzy fallback. Consequently, boundaries differ between sources. Name matching also cannot by itself distinguish independent franchise employers.

ECHO joins are deduplicated by facility and ticker. Only V and S history characters count as violations; at most twelve characters are examined per facility. Source quantities and denominators remain separate in the long table. [`canonical.py`](../pipeline/canonical.py), [`03_aggregate.py`](../scripts/03_aggregate.py), [`consolidate.py`](../pipeline/consolidate.py).

## 4. Climate metric construction

The configured core window is 2018-2023. This is a study cutoff, not a claim that newer EPA data are unavailable. Let revenue \(R_{it}\) be measured in millions of USD. Intensity is

\[
I_{it}=E_{it}/R_{it}.
\]

The latest available observation in the window supplies the intensity level. For either positive emissions or positive intensity observations, fit

\[
\log x_{it}=a_i+b_it+\epsilon_{it},\qquad g_i=\exp(b_i)-1.
\]

`absolute_cagr` and `intensity_cagr` are these log-linear OLS growth estimates. They are not endpoint CAGRs; using multiple observations does not make OLS robust to outliers. At least three positive observations are needed for a fit. The trend guard also requires at least three observed years, a first-year/median emissions ratio between 0.2 and 2.5, and an absolute fitted annual growth rate at most 1.

The analysis-panel admission rule is less strict than a complete-case rule: latest intensity must be present and there must be at least three observed years. One or both trends may still be missing after their guards. Aggregation normally renormalizes over available metrics. The current normalizers can assign neutral values to constant or entirely missing groups, and the MAD method can become uninformative when MAD is zero. These behaviors limit interpretation and need explicit testing before changing the scoring model.

The numerator covers matched US reporting facilities, while SEC revenue can cover worldwide activities. Currency prices, business mix, outsourcing, divestitures, and changing reporting boundaries can move intensity without equivalent changes in physical efficiency.

## 5. Normalization, weighting, and aggregation

Each draw chooses GICS sector or sub-industry peers. Sub-industries with fewer than six companies fall back to their sector. **There is no further minimum-size exclusion for a sector.** A singleton can therefore receive the 100th percentile with a zero-width band. Percentiles compare position within the selected group, not absolute impacts between sectors.

Metrics are oriented so larger transformed values mean better performance. Normalized values generally use the positive interval `[0.01, 1]`:

| Method | Implementation |
|---|---|
| `rank` | Average-tie percentile rank, followed by the positive-floor mapping; ignores winsorization |
| `winsor-z` | Optional winsorization, mean/standard-deviation scaling, clipping to [-3, 3], and min-max rescaling |
| `min-max` | Optional winsorization followed by rescaling of oriented values |
| `median-mad` | Median and 1.4826 × median absolute deviation, clipping to [-3, 3], then rescaling; ignores winsorization |

Winsorization is inactive with fewer than five nonmissing observations. Its sampled tail fractions are 0, 0.01, and 0.05.

Equal weights assign \(1/K\). Entropy weights normalize each column into shares \(p_{ij}\), compute \(e_j=-\sum_i p_{ij}\log p_{ij}/\log n\), and normalize \(1-e_j\). CRITIC uses \(c_j=\sigma_j\sum_k(1-r_{jk})\), then normalizes \(c_j\). CRITIC's contrast/correlation rationale comes from [Diakoulaki, Mavrotas, and Papayannakis (1995)](https://doi.org/10.1016/0305-0548(94)00059-H). Neither statistical dispersion nor low correlation establishes environmental importance.

Weights are estimated across the pooled matrix **after** within-peer normalization, not separately for every peer group. Column-mean filling is used to estimate weights; the original normalized matrix goes to aggregation.

For available normalized values \(z_{ij}\) and weights \(w_j\), the alternatives are

\[
A_i=\frac{\sum_{j\in O_i}w_jz_{ij}}{\sum_{j\in O_i}w_j},\qquad
G_i=\exp\left(\frac{\sum_{j\in O_i}w_j\log z_{ij}}{\sum_{j\in O_i}w_j}\right).
\]

The geometric mean limits compensation but does not prohibit it. The ensemble samples both aggregators; geometric aggregation with equal weights and winsorized z-scores is a reference configuration in separate diagnostics, not the sole model behind the saved band. [`scoring/`](../pipeline/scoring/).

## 6. Monte Carlo interpretation

The main script requests 1,500 draws with seed `20260912`; the reusable configuration class defaults to 1,000 unless overridden. Each draw independently samples from:

- Four normalizers, three weighting methods, two aggregators, two peer levels, and three winsor fractions: **144 base configurations**.
- With probability 0.30, one of the three metrics is omitted uniformly; otherwise none is omitted. Including omission states gives **576 nominal discrete configurations**, sampled with unequal probabilities. These are not 576 enumerated runs, and some settings yield identical calculations.
- Additive Gaussian perturbations before normalization:

\[
x^{(d)}_{ij}=x_{ij}+\sigma_j\left[0.05+0.35(1-c_i)\right]Z^{(d)}_{ij},
\quad Z^{(d)}_{ij}\sim N(0,1).
\]

Here \(\sigma_j\) is the pooled cross-sectional population standard deviation and \(c_i\) is heuristic matching confidence, with missing confidence treated as zero. The perturbation is unbounded and can produce negative values even for nonnegative quantities. It represents a sensitivity scenario, not an empirically estimated measurement-error distribution or a model of correlated attribution mistakes.

Scores are ranked within that draw's peer group using average ties and percentile ranks multiplied by 100. Store P10, P50, P90, P90-P10, and the shares of draws at or above 80 and at or below 20. P10-P90 is an **80% central sensitivity range conditional on the chosen scenario distribution**. It is not a frequentist confidence interval, Bayesian credible interval, or probability of absolute sustainability. Nor does it quantify omitted Scope 2/3, unobserved facilities, or uncertain peer-universe membership.

Separate 800-draw method-only and noise-only runs diagnose the source of variation. Their widths are not additive variance components. Conditional mean-percentile spreads by method are descriptive; the code does not compute Sobol indices. The methodological motivation is robustness analysis of composite indicators, as developed by [Saisana, Saltelli, and Tarantola (2005)](https://doi.org/10.1111/j.1467-985X.2005.00350.x) and the [OECD/JRC handbook (2008)](https://doi.org/10.1787/9789264043466-en).

The retained climate-band CSV has no complete raw-data cache or draw archive. Its percentiles were preserved during cleanup and checked for consistency; they were **not recomputed from original source records**. A fixed seed alone cannot reproduce them without the original inputs and environment.

## 7. Context signals and evidence availability

`intensity_illusion` flags negative intensity growth with positive absolute emissions growth. `base_year_flag` checks whether first-year emissions exceed the within-window median by more than 10%, after the base-stability guard. These signals can reflect growth, reporting changes, or genuine business changes. They are not findings of deception. The name `greenwashing_axis` is retained internally, but the exported filename is `context_signals.csv`.

For evidence family \(f\) in pillar \(p\), take its maximum available metric weight, then sum across families:

\[
H_{ip}=\sum_f\max_{j\in f\cap O_i}w_j.
\]

A pillar is `strong` if it has at least two distinct families, an anchor weight of at least 0.8, and a total of at least 1.5; `partial` if it has an anchor or a total of at least 1; `thin` if some evidence remains; otherwise `none`. These are uncalibrated design thresholds. The complete metric-to-family mapping is in [`reliability.py`](../pipeline/reliability.py).

An observation marked `error` is excluded from evidence assessment. `review` observations still count and require inspection. Presence of a zero-valued status still counts as evidence about that status. Families reduce duplicate counting but are not proven independent. The rule does not enforce recency, worldwide coverage, employer attribution certainty, or completeness of a sustainability dimension. ECHO's classification under G is an explicit modeling choice about a narrow compliance signal.

## 8. Quality review

The active rules check repeated CIKs, nonpositive emissions, CAMPD reporting programs, impossible ECHO histories, suspicious plant attribution, selected historical ownership, implausible OSHA hours, trade-name wage attribution, conflicting target types, and sector extremes. A high robust log-scale z-score triggers review rather than automatic deletion. Zero MAD is replaced by a small floor in the outlier rule; very large archived z-scores can therefore reflect ties, not correspondingly strong evidence of error.

Human decisions in `data/review/decisions.csv` take precedence. IDs hash the rule, issuer, metric, period, value, and evidence, so changed evidence does not inherit a decision merely because it occupies the same row. A human `keep`/`ok`/`plausible` decision clears a flag; `error`/`suppress`/`correct` marks an error without inventing a corrected numerical value.

Optional AI advice is cached and can escalate uncertain cases. The model does not supply observations, and its own confidence is not calibrated. Automatic suppression/correction advice remains `review` until a human decision or hard rule establishes otherwise. The shipped 18 findings contain **English summaries of archived model advice**, explicitly labeled as such; no new model review was performed during cleanup. There are no recorded human decisions. Thirteen observations remain marked for review, and five archived plausible/keep recommendations resolve to `ok`.

The rule-only command refreshes findings, honors human decisions, and rewrites observation annotations. Full rule recomputation requires the raw caches. The offline validator checks the saved findings and their linkage without claiming to re-audit source records. Quality annotations do not automatically rerun or filter the climate analysis; inspect ranking-relevant findings and rebuild after confirmed source corrections. [`quality.py`](../pipeline/quality.py), [`flag_apply.py`](../pipeline/flag_apply.py).

## 9. Economic viability

This is a separate capacity screen with three dimensions. It does not enter the climate ranking. The active implementation excludes the **entire GICS Financials sector**, including nonbank companies. Specialized regulatory or sector-appropriate measures would be needed to extend it.

SEC extraction reads USD facts from US GAAP or selected IFRS concepts, prioritizes tags and recent filings, reconstructs trailing twelve months as fiscal year + current YTD - comparable prior YTD when possible, and can annualize YTD as a fallback. Nonzero facts are preferred over zero placeholders for overlapping periods. Those extraction assumptions can also suppress a legitimate restated zero. The files are not a point-in-time historical dataset: later restatements may be used. [`sec_facts.py`](../pipeline/economy/sec_facts.py).

Define a clamped ramp \(r(x;a,b)=\min(1,\max(0,(x-a)/(b-a)))\). Reversing \(a,b\) makes a lower value better.

**Cash generation.** Over at most ten fiscal years, ramp the share of years with positive operating cash flow from zero at 0.5 to full credit at 1.0. Ramp the share covering depreciation from 0.5 to 0.9. Each history-based component needs at least three observations or paired years. A recent component is 0 if current trailing cash flow is nonpositive, 1 if positive and the last up-to-three fiscal years are all positive, and 0.5 otherwise. The dimension is the arithmetic mean of available components; three years of history are not a universal admission requirement for the entire model.

**Shock absorption.** For consecutive historical year pairs, calculate the largest nonnegative fall in operating cash flow divided by assets at the start of the year:

\[
d_i=\max_t\frac{\max(OCF_{i,t-1}-OCF_{it},0)}{Assets_{i,t-1}},
\qquad OCF_i^{stress}=OCF_i^{TTM}-d_iAssets_i^{latest}.
\]

At least two comparable pairs are required. Nonnegative stressed cash flow receives 1. Otherwise cash plus selected short-term investments divided by the shortfall is ramped from 0 at 0.25 to 1 at 1. This is a hypothetical replay of an observed decline at today's asset scale, not an observed future outcome or a calibrated stress probability.

**Debt service.** Interest paid divided by operating cash flow plus absolute interest paid is ramped from 0 at 0.5 to 1 at 0.1. Debt due within twelve months divided by cash plus nonnegative trailing operating cash flow is ramped from 0 at 1.5 to 1 at 0.5. Average the available components. Missing OCF is treated as zero in the second denominator; incomplete debt tags, restricted cash, and accounting classification differences remain limitations. Cash-months and tagged labor expense are informational only.

At least two dimensions are required. The numerical index is 100 times their equal-weight geometric mean, with a floor of 0.02 per dimension. The **category uses the weakest available dimension before that floor**: `viable` at 0.60 or above, `strained` at 0.25 or above, otherwise `at risk`. Missing dimensions are noted. A fixed `STALE_BEFORE = 2024-06-30` screening cutoff is retained and must be reconsidered for later builds. Exported component scores are rounded, so they may not reproduce a boundary classification exactly.

The thresholds are hand-set and the screen has not been validated against subsequent defaults, payroll failures, or other independent outcomes. A stress replay, saturation, and low sample correlations cannot prove predictive superiority or absence of size/sector bias. [`economic_viability.py`](../pipeline/economy/economic_viability.py).

## 10. Research comparison and validation boundary

| Research | What it contributes | What it does not establish here |
|---|---|---|
| Berg, Kölbel & Rigobon (2022), *Aggregate Confusion*, Review of Finance 26(6), 1315-1344. [DOI](https://doi.org/10.1093/rof/rfac033) | Provider disagreement can arise from scope, measurement, and weights; motivates inspecting the underlying evidence | That public data are unbiased or that our score is more accurate |
| Khan, Serafeim & Yoon (2016), *Corporate Sustainability: First Evidence on Materiality*, The Accounting Review 91(6), 1697-1724. [DOI](https://doi.org/10.2308/accr-51383) | Industry-relevant sustainability issues matter in their empirical setting | Validation of our GICS peer cutoffs, global-impact coverage, or three climate metrics |
| Saisana, Saltelli & Tarantola (2005), JRSS A 168(2), 307-323. [DOI](https://doi.org/10.1111/j.1467-985X.2005.00350.x) | Uncertainty/sensitivity analysis helps assess composite-indicator robustness | Calibration of our noise amplitudes, draw probabilities, or bands as confidence intervals |
| OECD/JRC (2008), *Handbook on Constructing Composite Indicators*. [DOI](https://doi.org/10.1787/9789264043466-en) | A framework for transparent construction, aggregation choices, and robustness checks | Certification of this implementation or a unique correct aggregate |
| Diakoulaki, Mavrotas & Papayannakis (1995), Computers & Operations Research 22(7), 763-770. [DOI](https://doi.org/10.1016/0305-0548(94)00059-H) | CRITIC's dispersion and correlation-based weighting rationale | That information-content weights equal social or environmental importance |

The defensible improvement is inspectability and explicit sensitivity for the narrow operational question. MSCI and Sustainalytics publish methodologies and use materiality/industry information; the project does not claim otherwise. The historical 2021 risk-score mirror is not a contemporaneous ground truth and must not be used to claim that disagreement demonstrates superiority. External assessments remain separately labeled and never enter the climate metrics.

A stronger comparative claim would require a pre-specified outcome, representative sector coverage, a dated ownership/membership universe, a manually audited attribution sample, and independent or held-out validation. Those studies are not included.

## 11. Running and checking the repository

The [README](../README.md) gives installation and the complete command sequence. The stages are fetch; climate analysis; facility aggregation; consolidated export; quality review; final evidence assessment; economic fetch/score; validation. The filenames retain a simple ordering, but review must precede the final reliability build.

`01_fetch.py` can accept source names and `--force`. `EPA_CAMD_API_KEY` supports CAMPD access and `EIA_API_KEY` supports EIA API access. Set `SEC_USER_AGENT` to your project name and real contact address; `.env` is ignored. `OPENAI_API_KEY` is used only when explicitly requesting `06_review.py --ai`, which incurs API charges. The saved snapshot needs none of these credentials.

Cached downloads are ignored under `data/raw/`. A refresh can change releases, dates, values, and coverage. Membership stays fixed to constituents.csv; update that snapshot deliberately to change the universe. Core sources are needed before later stages; some auxiliary sources may fail or be unavailable. Save the exact raw inputs and dependency versions if you need to reproduce a particular build. The source connectors and retained economic screen still contain fixed windows that require deliberate review for a new study period.

`08_validate.py` checks observation keys, English schemas, catalog references, issuer membership, percentile ordering, evidence-bound review IDs, annotations, and key source constraints. `--write-summary` updates `snapshot_summary.json` only after those checks pass. Tests cover deterministic scoring, missing-data aggregation, ownership boundaries, financial extraction, and review precedence. These software checks do not establish the truth of an underlying reported value.

The cleaned snapshot has 500 issuers, 449 with sustainability observations, 127 saved climate bands, a median band width of about 28.04 percentile points, 375 viable economic assessments, 29 strained, 19 at risk, and 77 not assessable. Evidence is `strong` under the heuristic rules for 135 issuers in E, 105 in S, and 54 in G; only 16 meet all three. The summary JSON is the reproducible count reference.
