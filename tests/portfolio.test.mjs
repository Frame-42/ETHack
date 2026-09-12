import { test } from "node:test";
import assert from "node:assert/strict";
import {
  HOLDINGS,
  allocate,
  stressPortfolio,
  FUND,
} from "../src/portfolio.mjs";
const weights = () =>
  Object.fromEntries(HOLDINGS.map((h) => [h.ticker, h.weight]));
test("baseline allocates exactly one billion within concentration limits", () => {
  const a = allocate();
  assert.ok(a.valid);
  assert.equal(a.total, 100);
  assert.equal(
    a.rows.reduce((s, h) => s + h.dollars, 0),
    FUND,
  );
  assert.deepEqual(
    a.themes.map((t) => t.weight),
    [30, 24, 20, 6, 20],
  );
});
test("stress arithmetic agrees with independently hand-computed dollar impacts", () => {
  assert.equal(stressPortfolio(allocate(), "delay").change, -162e6);
  assert.equal(stressPortfolio(allocate(), "crowded").change, -240e6);
  assert.equal(stressPortfolio(allocate(), "build").change, 126e6);
});
test("overfunding, shorting, concentration and insufficient reserve are rejected", () => {
  for (const w of [
    { ...weights(), ETN: 9 },
    { ...weights(), ETN: -1, "T-BILLS": 29 },
    { ...weights(), ETN: 9, "T-BILLS": 19 },
    { ...weights(), "T-BILLS": 9 },
    { ...weights(), ETN: NaN },
  ]) {
    const a = allocate(w);
    assert.equal(a.valid, false);
    assert.throws(() => stressPortfolio(a));
  }
  const concentrated = {
    ...weights(),
    ETN: 12,
    GEV: 12,
    PWR: 12,
    "T-BILLS": 8,
  };
  assert.ok(
    allocate(concentrated).problems.includes("Single-theme limit: 35%."),
  );
});
