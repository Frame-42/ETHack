export const DIMENSIONS = [
  {
    key: "contribution",
    label: "Climate contribution",
    short: "Contribution",
    description:
      "WBA CTT: emissions/target alignment and low-carbon investment. An ordinal assessment, not tonnes avoided.",
  },
  {
    key: "planning",
    label: "Plan credibility",
    short: "Planning",
    description: "WBA transition plan quality (TPQ), from 0 to 5.",
  },
  {
    key: "nature",
    label: "Nature",
    short: "Nature",
    description:
      "WBA Nature Benchmark, 0–100. Ecosystems, biodiversity and resource stewardship.",
  },
  {
    key: "social",
    label: "People & conduct",
    short: "People",
    description:
      "WBA Social Benchmark, 0–100. Human rights, decent work and ethical conduct.",
  },
];
export const DEFAULT_WEIGHTS = {
  contribution: 50,
  planning: 20,
  nature: 0,
  social: 30,
};
export const EXTENDED_WEIGHTS = {
  contribution: 40,
  planning: 20,
  nature: 20,
  social: 20,
};
export const PRESETS = {
  balanced: DEFAULT_WEIGHTS,
  climate: { contribution: 65, planning: 20, nature: 0, social: 15 },
  people: { contribution: 30, planning: 20, nature: 0, social: 50 },
  planning: { contribution: 30, planning: 45, nature: 0, social: 25 },
  equal: { contribution: 1, planning: 1, nature: 0, social: 1 },
};
export const EXTENDED_PRESETS = {
  balanced: EXTENDED_WEIGHTS,
  climate: { contribution: 60, planning: 20, nature: 10, social: 10 },
  people: { contribution: 25, planning: 15, nature: 20, social: 40 },
  nature: { contribution: 25, planning: 15, nature: 40, social: 20 },
  equal: { contribution: 25, planning: 25, nature: 25, social: 25 },
};
export function normalizedWeights(weights) {
  const values = DIMENSIONS.map((d) => weights[d.key]);
  if (values.some((v) => !Number.isFinite(v) || v < 0))
    throw new Error("Weights must be finite and non-negative.");
  const total = values.reduce((a, b) => a + b, 0);
  if (!total) throw new Error("At least one weight must be above zero.");
  return Object.fromEntries(
    DIMENSIONS.map((d) => [d.key, weights[d.key] / total]),
  );
}
export function pillars(company, middleContribution = 50) {
  const a = company.assessment ?? {};
  return {
    contribution: a.ctt == null ? null : [0, middleContribution, 100][a.ctt],
    planning: a.tpq == null ? null : a.tpq * 20,
    nature: a.nature ?? null,
    social: a.social ?? null,
  };
}
export function score(
  company,
  weights = DEFAULT_WEIGHTS,
  middleContribution = 50,
  lens = "core",
) {
  if (!["core", "extended"].includes(lens))
    throw new Error("Unknown scoring lens.");
  if (![25, 50, 75].includes(middleContribution))
    throw new Error("Invalid ordinal mapping.");
  if (lens === "core" && weights.nature !== 0)
    throw new Error("Core lens excludes nature.");
  const w = normalizedWeights(weights),
    p = pillars(company, middleContribution);
  let lower = 0,
    missingWeight = 0,
    known = 0;
  const required = DIMENSIONS.filter(
    (d) => lens === "extended" || d.key !== "nature",
  );
  for (const d of required) {
    const v = p[d.key];
    if (v == null) missingWeight += w[d.key];
    else {
      if (!Number.isFinite(v) || v < 0 || v > 100)
        throw new Error(`Invalid ${d.key} for ${company.ticker}`);
      lower += w[d.key] * v;
      known++;
    }
  }
  // Zeroing a slider cannot change the eligible cohort or hide missing evidence.
  const complete = known === required.length;
  return {
    pillars: p,
    complete,
    known,
    required: required.length,
    lower,
    upper: lower + missingWeight * 100,
    value: complete ? lower : null,
    coverage: 1 - missingWeight,
  };
}
export function rankCompanies(
  companies,
  weights = DEFAULT_WEIGHTS,
  middleContribution = 50,
  lens = "core",
) {
  const rows = companies.map((c) => ({
    ...c,
    result: score(c, weights, middleContribution, lens),
  }));
  rows.sort(
    (a, b) =>
      (b.result.value ?? -1) - (a.result.value ?? -1) ||
      a.name.localeCompare(b.name),
  );
  let previous = null,
    rank = null;
  rows.forEach((c, i) => {
    if (c.result.complete) {
      if (previous == null || Math.abs(c.result.value - previous) > 1e-9)
        rank = i + 1;
      c.rank = rank;
      previous = c.result.value;
    } else c.rank = null;
  });
  return rows;
}
export function sensitivity(companies, lens = "core") {
  const scenarios = Object.values(
    lens === "core" ? PRESETS : EXTENDED_PRESETS,
  ).flatMap((weights) => [25, 50, 75].map((mid) => ({ weights, mid })));
  const ranks = new Map(companies.map((c) => [c.cik, []]));
  for (const s of scenarios)
    for (const c of rankCompanies(companies, s.weights, s.mid, lens))
      if (c.rank != null) ranks.get(c.cik).push(c.rank);
  return Object.fromEntries(
    [...ranks].map(([cik, values]) => [
      cik,
      values.length
        ? {
            best: Math.min(...values),
            worst: Math.max(...values),
            scenarios: values.length,
          }
        : null,
    ]),
  );
}
export function peerPercentile(company, rows) {
  if (!company.result.complete) return null;
  const peers = rows.filter(
    (c) => c.sector === company.sector && c.result.complete,
  );
  if (peers.length < 5) return null;
  const below = peers.filter(
    (c) => c.result.value < company.result.value - 1e-9,
  ).length;
  const tied = peers.filter(
    (c) => Math.abs(c.result.value - company.result.value) < 1e-9,
  ).length;
  return {
    value: (100 * (below + (tied - 1) / 2)) / (peers.length - 1),
    count: peers.length,
  };
}
export function csvText(rows) {
  const fields = [
    "ticker",
    "name",
    "sector",
    "rank",
    "score",
    "lower_bound",
    "upper_bound",
    "pillars_available",
    "pillars_required",
    "contribution",
    "planning",
    "nature",
    "social",
    "source",
  ];
  const quote = (v) => `"${String(v ?? "").replaceAll('"', '""')}"`;
  return [
    fields,
    ...rows.map((c) => [
      c.tickers.join("/"),
      c.name,
      c.sector,
      c.rank,
      c.result.value?.toFixed(2),
      c.result.lower.toFixed(2),
      c.result.upper.toFixed(2),
      c.result.known,
      c.result.required,
      ...DIMENSIONS.map((d) => c.result.pillars[d.key]),
      c.assessment?.source?.url,
    ]),
  ]
    .map((r) => r.map(quote).join(","))
    .join("\n");
}
