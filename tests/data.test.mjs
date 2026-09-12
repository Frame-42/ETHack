import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { rankCompanies, EXTENDED_WEIGHTS } from "../src/model.mjs";
import { HOLDINGS } from "../src/portfolio.mjs";
const rawBytes = await readFile(
  new URL("../data/raw/snapshot.json", import.meta.url),
);
const raw = JSON.parse(rawBytes);
const { metadata, companies } = JSON.parse(
  await readFile(new URL("../data/processed/companies.json", import.meta.url)),
);
test("universe deduplicates share classes and retains all 500 issuers", () => {
  assert.equal(companies.length, 500);
  assert.equal(new Set(companies.map((c) => c.cik)).size, 500);
  assert.equal(
    companies.reduce((n, c) => n + c.tickers.length, 0),
    503,
  );
  assert.equal(
    companies.filter(
      (c) => c.tickers.includes("GOOG") || c.tickers.includes("GOOGL"),
    ).length,
    1,
  );
});
test("all matched inputs have valid native units, unique source IDs and provenance", () => {
  const matched = companies.filter((c) => c.assessment);
  assert.equal(matched.length, 217);
  assert.equal(new Set(matched.map((c) => c.wba.id)).size, 217);
  for (const c of matched) {
    const a = c.assessment;
    assert.ok([0, 1, 2].includes(a.ctt));
    assert.ok([0, 1, 2, 3, 4, 5].includes(a.tpq));
    for (const k of ["social", "nature"])
      if (a[k] != null) assert.ok(a[k] >= 0 && a[k] <= 100);
    assert.match(
      a.source.url,
      /^https:\/\/www.worldbenchmarkingalliance.org\/company\//,
    );
    assert.match(a.source.sha256, /^[a-f0-9]{64}$/);
    assert.ok(!Number.isNaN(Date.parse(a.source.retrieved_at)));
  }
});
test("frozen observations reproduce coverage, headline findings and source hashes", async () => {
  assert.equal(
    metadata.snapshot_sha256,
    createHash("sha256").update(rawBytes).digest("hex"),
  );
  const constituentBytes = await readFile(
    new URL("../data/raw/constituents.csv", import.meta.url),
  );
  assert.equal(
    raw.universe_source.sha256,
    createHash("sha256").update(constituentBytes).digest("hex"),
  );
  const core = rankCompanies(companies),
    extended = rankCompanies(companies, EXTENDED_WEIGHTS, 50, "extended");
  assert.equal(core.filter((c) => c.rank != null).length, metadata.complete);
  assert.equal(metadata.complete, 217);
  assert.equal(
    extended.filter((c) => c.rank != null).length,
    metadata.extended,
  );
  assert.equal(metadata.extended, 71);
  assert.equal(core[0].ticker, "TGT");
  assert.ok(Math.abs(core[0].result.value - 52.35) < 1e-8);
  assert.equal(extended[0].ticker, "NEM");
  assert.equal(companies.filter((c) => c.assessment?.ctt === 1).length, 1);
  assert.deepEqual(
    companies.filter((c) => c.assessment?.ctt === 1).map((c) => c.ticker),
    ["TGT"],
  );
  assert.ok(raw.companies.every((c) => !c.assessment || c.wba));
});
test("sector coverage sums to the reported cohort sizes", () => {
  assert.equal(
    metadata.sectors.reduce((s, c) => s + c.total, 0),
    500,
  );
  assert.equal(
    metadata.sectors.reduce((s, c) => s + c.complete, 0),
    217,
  );
  assert.equal(
    metadata.sectors.reduce((s, c) => s + c.extended, 0),
    71,
  );
});
test("every scenario equity belongs to the frozen S&P 500 universe", () => {
  for (const h of HOLDINGS.filter((h) => h.theme !== "reserve"))
    assert.ok(
      companies.some((c) => c.tickers.includes(h.ticker)),
      h.ticker,
    );
  const assessedWeight = HOLDINGS.filter((h) =>
    companies.some((c) => c.tickers.includes(h.ticker) && c.assessment),
  ).reduce((s, h) => s + h.weight, 0);
  assert.equal(assessedWeight, 46);
});
