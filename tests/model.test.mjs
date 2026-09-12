import { test } from 'node:test';
import assert from 'node:assert/strict';
import { score, rankCompanies, normalizedWeights, sensitivity, peerPercentile, csvText, DEFAULT_WEIGHTS, EXTENDED_WEIGHTS } from '../src/model.mjs';
const company = (ticker, a = {}) => ({ ticker, tickers: [ticker], cik: ticker, name: ticker, sector: 'Test', assessment: { ctt: 1, tpq: 3, nature: 40, social: 50, ...a } });
test('core and extended formula reproduce a hand-computed example', () => {
  const c = company('A');
  assert.equal(score(c).value, 52); // .5*50 + .2*60 + .3*50
  assert.equal(score(c, EXTENDED_WEIGHTS, 50, 'extended').value, 50);
});
test('unknown is distinct from zero and cannot win a rank', () => {
  const unknown = company('Unknown', { ctt: null, tpq: null, nature: null, social: null });
  const zero = company('Zero', { ctt: 0, tpq: 0, nature: 0, social: 0 });
  assert.deepEqual([score(unknown).value, score(unknown).lower, score(unknown).upper], [null, 0, 100]);
  const rows = rankCompanies([unknown, zero]);
  assert.equal(rows[0].ticker, 'Zero'); assert.equal(rows[0].rank, 1); assert.equal(rows[1].rank, null);
});
test('completion bounds contain every possible missing nature value', () => {
  const c = company('A', { nature: null });
  const result = score(c, EXTENDED_WEIGHTS, 50, 'extended');
  assert.equal(result.value, null); assert.equal(result.lower, 42); assert.equal(result.upper, 62);
  for (const nature of [0, 17, 50, 100]) {
    const actual = score(company('A', { nature }), EXTENDED_WEIGHTS, 50, 'extended').value;
    assert.ok(actual >= result.lower && actual <= result.upper);
  }
  assert.ok(score(c).complete, 'Nature is not required by the explicitly named core lens');
  assert.equal(score(c, { ...EXTENDED_WEIGHTS, nature: 0 }, 50, 'extended').value, null, 'Zeroing a weight does not change eligibility');
});
test('weights normalize; invalid weights and ordinal mapping fail loudly', () => {
  assert.equal(score(company('A'), Object.fromEntries(Object.entries(DEFAULT_WEIGHTS).map(([k,v])=>[k,v*2]))).value, 52);
  for (const x of [0, -1, NaN, Infinity]) assert.throws(()=>normalizedWeights({ contribution:x, planning:0, nature:0, social:0 }));
  assert.throws(()=>score(company('A'), DEFAULT_WEIGHTS, 300));
  assert.throws(()=>score(company('A'), EXTENDED_WEIGHTS));
  assert.throws(()=>score(company('A', { social:101 })));
});
test('ties use competition ranks and increasing any pillar cannot lower the score', () => {
  const rows = rankCompanies([company('A'), company('B'), company('C', { social:0 })]);
  assert.deepEqual(rows.map(c=>c.rank), [1,1,3]);
  for (const [key, next] of [['ctt',2],['tpq',4],['social',80]]) assert.ok(score(company('X', { [key]:next })).value >= score(company('X')).value);
});
test('changing the ordinal midpoint really changes results', () => {
  assert.equal(score(company('A'), DEFAULT_WEIGHTS, 25).value, 39.5);
  assert.equal(score(company('A'), DEFAULT_WEIGHTS, 75).value, 64.5);
});
test('sensitivity keeps incomplete companies unranked and evaluates 15 scenarios', () => {
  const rows = [company('A'), company('B',{social:null})];
  const s = sensitivity(rows);
  assert.deepEqual(s.A,{best:1,worst:1,scenarios:15}); assert.equal(s.B,null);
});
test('sector percentiles suppress tiny samples and handle ties at the midpoint', () => {
  const small = rankCompanies([company('A'),company('B')]); assert.equal(peerPercentile(small[0],small),null);
  const tied = rankCompanies(['A','B','C','D','E'].map(t=>company(t))); assert.equal(peerPercentile(tied[0],tied).value,50);
});
test('CSV preserves source absence and escapes embedded quotes', () => {
  const rows = rankCompanies([{...company('A'),name:'A, "quoted" company'},{ticker:'B',tickers:['B'],name:'B',cik:'B'}]);
  const csv=csvText(rows); assert.match(csv,/"A, ""quoted"" company"/); assert.equal(csv.split('\n').length,3);
  assert.match(csv.split('\n')[2],/"","","0.00","100.00"/);
});
