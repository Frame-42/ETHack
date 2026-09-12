# After the Pledge: a sustainability evidence framework for the S&P 500

## Research question

Which companies have evidence that their transition is credible, contributes to a low-carbon economy, and respects people and nature? How sensitive is the comparison to our definition of sustainability?

We define sustainability as the capacity to provide economic value while moving toward a low-carbon economy without externalising unacceptable costs onto people and ecosystems. Our operational measure is narrower: disclosed evidence assessed against WBA benchmarks. It measures transition preparedness and conduct, not a company's complete physical impact or financial survival probability.

The delivered application, frozen data, reproducible model, ranked CSVs and separate investment memo constitute the solution. No company measurements are generated or simulated. Scenario price shocks are explicitly hypothetical.

## Dataset and suitability

The index universe is a retrieval-date snapshot of the [DataHub S&P 500 constituent mirror](https://github.com/datasets/s-and-p-500-companies). It includes names, share-class tickers, CIKs and GICS sectors. It is maintained from Wikipedia rather than supplied under an official S&P index-data licence. The exact constituent CSV is retained with its SHA-256 and retrieval timestamp. Combine securities sharing a CIK: 503 securities become 500 issuers in this snapshot. This prevents Alphabet, Fox and News Corp share classes receiving duplicate company weight.

Assessment data comes directly from public [World Benchmarking Alliance company profiles](https://www.worldbenchmarkingalliance.org/company-scoreboard) in the 2026 release:

| Input | Source | Unit | Selection rationale |
|---|---|---|---|
| Climate contribution, CTT | [ACT Core](https://www.worldbenchmarkingalliance.org/benchmark/act-core) | Ordinal 0, 1, 2 | Connects emissions/target alignment and investment to transition contribution |
| Transition plan quality, TPQ | ACT Core | Ordinal 0–5 | Tests the structure and credibility of transition planning |
| Social score | [Social Benchmark](https://www.worldbenchmarkingalliance.org/benchmark/social-benchmark) | 0–100 benchmark points | Adds human rights, decent work and ethical conduct |
| Nature score | [Nature Benchmark](https://www.worldbenchmarkingalliance.org/benchmark/nature-benchmark) | 0–100 benchmark points | Adds ecosystem, biodiversity and resource stewardship |

WBA is appropriate because its methodology and issuer assessments are inspectable, cross-sector and available under [CC BY 4.0](https://www.worldbenchmarkingalliance.org/disclaimer). It does not offer complete index coverage. WBA assessments depend heavily on disclosure, and the benchmarks are not independent: governance and social content can overlap. This project is a transparent recombination of assessed inputs, not a new audit of company reports.

WBA's 2025 research cycle generally considers reports published September 1, 2024–August 31, 2025, with earlier-period exceptions and policies remaining in force. See its [research disclaimer](https://www.worldbenchmarkingalliance.org/disclaimer). “2026” is the assessment release, not the year in which every metric was measured. The frozen source metadata records when this project retrieved each page. There is no claim of real-time data.

## Joining and coverage

1. Preserve every constituent issuer and its ticker list.
2. Normalize names by case, punctuation, common corporate suffixes and explicit share-class suffixes.
3. Accept a normalized exact name only when it has one directory candidate.
4. Apply seven explicitly reviewed aliases in `data/aliases.json`. They are BX→Blackstone Group, DLR→Digital Realty Trust, F→Ford, MLM→Martin Marietta, TAP→Molson Coors, PFG→Principal Financial and TROW→T. Rowe Price Group.
5. Preserve unresolved issuers as unmatched. No automatic fuzzy matching, ticker guessing or company substitution.

The public directory endpoint returns 1,955 companies against a 2,000 headline; WBA separately lists 45 unscored companies and explains its English-language disclosure restriction. We retain the observed directory count, rather than asserting that 2,000 rows were fetched. An unmatched company is unresolved by this join, not proved absent from WBA. Even exact-name joins need human scrutiny around mergers and spin-offs; the source name, WBA ID and CIK remain visible for review.

The frozen join yields 217 companies with TPQ, CTT and Social scores. Nature is available for only 71 of those. The application offers two lenses:

- **Core:** a 217-company comparison using climate contribution, planning and social evidence.
- **With nature:** a 71-company comparison requiring all four pillars.

The nature lens cannot support a universal cross-sector leaderboard: five GICS sectors have no complete records in it. The full sector coverage table is computed in `docs/results.md`, not hand-written into a chart. Both views display all 500 companies. Unavailable observations remain null.

## Scoring, explicitly normative

Let C be the mapping of CTT categories (0, 1, 2) to (0, 50, 100). Let P = 20 × TPQ. Let S and N be the published Social and Nature scores.

```
Core score        = 0.50 C + 0.20 P + 0.30 S
Nature-inclusive  = 0.40 C + 0.20 P + 0.20 N + 0.20 S
```

Climate contribution gets the largest weight because our definition prioritises aligned investment and business transition over a plan alone. Social receives meaningful weight so climate disclosure cannot erase the treatment of people. The nature-inclusive lens trades coverage for a broader definition. These weights express priorities; they were not statistically estimated or tuned to promote particular companies.

Higher is better on each input. We do not normalise to the best company in the observed sample: that would turn weak absolute evidence into a perfect score. Published categories are mapped explicitly rather than assigning equally spaced values to WBA's A–G letters. The UI retains original CTT and TPQ units beside the composite.

CTT is a mixed indicator of alignment, targets and investment, not observed emissions alone. Equal category spacing is a utility assumption, not a physical law. Test the middle CTT mapping at 25, 50 and 75. Sliders represent nonnegative weights and are normalised to sum to one. An all-zero vector is invalid. No numerical threshold certifies a company “sustainable.”

An additive score allows compensation between pillars. We expose every pillar, sector context and low social scores rather than conceal that trade-off behind a label. A future implementation could add investor-specific minimum standards, but this submission does not invent a universal exclusion threshold from these data.

## Unknowns, ranking and robustness

For required missing pillars, calculate completion bounds:

```
lower = sum(weight × score for observed required pillars)
upper = lower + 100 × sum(weights of missing required pillars)
```

The lower bound is not a zero-imputed ranking score. Incomplete companies have a null composite and no rank. Even if the user sets a missing pillar's weight to zero, completeness remains fixed by the lens. Companies can therefore be compared under changing preferences without silently changing the cohort. Neither interval is a confidence interval; no distribution is assumed for unknown values.

Rank complete companies in descending composite order with competition ties (1, 1, 3). Rank before applying UI search or sector filters, so a filter cannot misleadingly change global standing. Also show a sector percentile in company details, only when at least five complete peers exist. Percentiles use `(number below + (number tied - 1)/2)/(n - 1)`; singleton or very small cohorts receive no percentile. Sector-relative performance does not certify absolute sustainability.

Robustness runs five predefined weighting profiles × three middle-CTT mappings = 15 scenarios per lens. Core profiles are baseline, climate-heavy, people-heavy, planning-heavy and equal. Extended profiles are baseline, climate-heavy, people-heavy, nature-heavy and equal. Exact vectors are in `src/model.mjs`. Each company's best and worst rank is calculated over the same eligible cohort. These ranks reflect only selected modelling assumptions; they do not include measurement error, missing-not-at-random effects or an exhaustive weight simplex. They remain labelled as predefined sensitivity ranges when custom sliders are used.

## Results and interpretation

The reproducible results are in [results.md](results.md). In the core cohort, 216 companies receive CTT 0, one receives CTT 1 and none receives CTT 2. This discrete input contains little cross-sectional information. It should be treated as a diagnostic finding and a limitation, not smoothed into invented continuous emissions performance.

Target leads the baseline core model with 52.4/100, but spans ranks 1–5 in the sensitivity scenarios. Its one-step contribution advantage is consequential under the chosen mapping. Ford and Newmont follow. In the nature-inclusive cohort, Newmont leads with 39.1; the cohort itself is different, so changes in rank are not solely caused by changing weights. The low leading scores are useful: a leaderboard need not manufacture an apparent sustainability champion.

None of these findings claims that a retailer has lower lifecycle impact than a software company, that a miner is harmless, or that a high-ranked company is attractively priced. The source data cannot establish those conclusions.

## Why not carbon intensity or a financial pillar?

Scope 1, location-based Scope 2, relevant Scope 3 categories, output-based intensity and historical absolute emissions would be valuable. A defensible implementation requires matched reporting periods, consistent boundaries, restatements and sector-specific output denominators. Dividing rounded profile emissions by rounded revenue of unknown vintage does not provide that. Revenue-based comparisons also reward high-margin business models and may shift with inflation.

The collector retains public profile footprint strings as context in the raw snapshot, but the model does not use them. It does not mix market-based and location-based Scope 2, fill missing Scope 3 with zero, sum overlapping supply-chain emissions across companies, or count avoided emissions as negative operational emissions.

Financial viability matters to executing a transition and buying a security. This dataset lacks matched audited free cash flow, leverage, valuation and liquidity. Rather than proxy financial health with market capitalisation or fabricate a return optimiser, we state those requirements in the investment memo. The bonus is a scenario allocation, not a claim of a fully underwritten executable portfolio.

## Reproducibility and improvements

The collector uses three concurrent requests, caches responses, stores retrieval times and SHA-256 hashes, and stops on failed requests. The public directory's POST is a read-only table request used by its website; the authenticated WBA API is not accessed. Committed extracted observations reproduce the app without external requests. Exact HTML is held in the ignored local cache; source hashes permit checking retained cache bytes. Live recollection may change as websites change, so refreshing is deliberately separate from rebuilding.

Priority improvements: manually review unmatched issuers and reorganisations; acquire granular licensed/API records with original report-level timestamps; add consistent physical emissions histories and investment data; add labor enforcement and controversy observations; add location-specific water and biodiversity pressures. A time-series backtest would require historical constituent membership and contemporaneous data availability, neither supplied here.

WBA data and methodology remain attributed to WBA. The ordinal transformations, weights, join, uncertainty bounds, UI and investment scenario are this project's work. WBA does not endorse the model or portfolio. DataHub/Wikipedia source terms remain separate from WBA's licence.
