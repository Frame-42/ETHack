import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { rankCompanies, sensitivity, csvText, EXTENDED_WEIGHTS } from '../src/model.mjs';
const root = new URL('../', import.meta.url);
const bytes = await readFile(new URL('data/raw/snapshot.json', root));
const raw = JSON.parse(bytes);
const ranked = rankCompanies(raw.companies);
const ranges = sensitivity(raw.companies);
const extended = rankCompanies(raw.companies, EXTENDED_WEIGHTS, 50, 'extended');
const extendedRanges = sensitivity(raw.companies, 'extended');
const sectors = [...new Set(ranked.map(c => c.sector))].sort().map(sector => {
  const rows = ranked.filter(c => c.sector === sector);
  return { sector, total: rows.length, matched: rows.filter(c => c.wba).length, complete: rows.filter(c => c.result.complete).length,
    extended: extended.filter(c => c.sector === sector && c.result.complete).length };
});
const metadata = { snapshot_date: raw.snapshot_date, assessment_cycle: 2026, securities: raw.security_count,
  issuers: ranked.length, matched: ranked.filter(c => c.wba).length, complete: ranked.filter(c => c.result.complete).length,
  extended: extended.filter(c => c.result.complete).length,
  directory_rows: raw.directory_rows_returned, directory_headline: raw.directory_headline_count,
  snapshot_sha256: createHash('sha256').update(bytes).digest('hex'), universe_source: raw.universe_source,
  sectors, sensitivity_scenarios: 15 };
const companies = ranked.map(({ result, rank, ...c }) => ({ ...c, baseline_rank: rank, sensitivity: { core: ranges[c.cik], extended: extendedRanges[c.cik] } }));
await mkdir(new URL('data/processed/', root), { recursive: true });
await writeFile(new URL('data/processed/companies.json', root), JSON.stringify({ metadata, companies }, null, 2) + '\n');
await writeFile(new URL('data/processed/ranking.csv', root), csvText(ranked) + '\n');
await writeFile(new URL('data/processed/ranking-with-nature.csv', root), csvText(extended) + '\n');
const leaders = (rows, r) => `| Company | Score | Rank across 15 assumptions |\n|---|---:|---:|\n${rows.filter(c => c.result.complete).slice(0, 12).map(c => `| [${c.name} (${c.ticker})](${c.assessment.source.url}) | ${c.result.value.toFixed(1)} | ${r[c.cik].best}–${r[c.cik].worst} |`).join('\n')}`;
const cttCounts = [0, 1, 2].map(n => ranked.filter(c => c.assessment?.ctt === n).length);
const report = `# Snapshot results\n\nRetrieved ${metadata.snapshot_date}. ${metadata.securities} securities collapse to ${metadata.issuers} issuers by CIK. ${metadata.matched} match WBA. The core comparison has ${metadata.complete} companies; the nature-inclusive comparison has ${metadata.extended}.\n\nThe WBA directory returns ${metadata.directory_rows} rows against a headline of ${metadata.directory_headline}. The missing 45 are listed as unscored by WBA. Unmatched means unresolved by this extraction, not necessarily absent from WBA.\n\n## What the data actually says\n\nCTT counts (0/2, 1/2, 2/2): ${cttCounts.join(', ')}. High plan quality alone does not establish an aligned transition. CTT mixes reported performance, target alignment and investment; it is not a measured emissions series. The results below are relative leaders in an incomplete cohort, not a list of companies certified sustainable.\n\n## Core comparison: climate and people\n\n${leaders(ranked, ranges)}\n\n## With nature: a narrower cohort\n\n${leaders(extended, extendedRanges)}\n\n## Sector coverage\n\n| Sector | Universe | Core | With nature |\n|---|---:|---:|---:|\n${sectors.map(s => `| ${s.sector} | ${s.total} | ${s.complete} | ${s.extended} |`).join('\n')}\n\nThe composite is our value judgment applied to WBA assessments, not a WBA rating. Rank ranges are sensitivity results, not statistical confidence intervals. A score is not an expected return.\n`;
await mkdir(new URL('docs/', root), { recursive: true });
await writeFile(new URL('docs/results.md', root), report);
console.log(`Built ${metadata.issuers} issuers; ${metadata.complete} core, ${metadata.extended} with nature. CTT: ${cttCounts.join('/')}`);
