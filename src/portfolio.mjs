export const FUND = 1_000_000_000;
export const THEMES = {
  grid: { name: "Grid & connections", color: "#3159da" },
  power: { name: "Low-carbon power", color: "#147c77" },
  efficiency: { name: "Use less energy", color: "#7296ab" },
  components: { name: "Enabling components", color: "#b87512" },
  reserve: { name: "Treasury-bill reserve", color: "#6d7883" },
};
export const HOLDINGS = [
  {
    ticker: "ETN",
    name: "Eaton",
    weight: 8,
    theme: "grid",
    thesis:
      "Power distribution and electrical equipment for an expanding electrified economy.",
    risk: "Valuation and industrial demand; exposure is broader than climate solutions.",
    source:
      "https://www.eaton.com/content/dam/eaton/company/sustainability/files/eaton-sustainability-report.pdf",
  },
  {
    ticker: "GEV",
    name: "GE Vernova",
    weight: 8,
    theme: "grid",
    thesis: "Grid equipment connects new generation to the users who need it.",
    risk: "Gas-turbine exposure and project execution; not a pure renewable company.",
    source: "https://www.gevernova.com/electrification/",
  },
  {
    ticker: "PWR",
    name: "Quanta Services",
    weight: 8,
    theme: "grid",
    thesis:
      "Engineering and construction capacity for power lines and substations.",
    risk: "Skilled-labor shortages, permitting and fixed-price contract losses.",
    source: "https://www.quantaservices.com/capabilities/electric-power",
  },
  {
    ticker: "HUBB",
    name: "Hubbell",
    weight: 6,
    theme: "grid",
    thesis:
      "Distribution hardware and grid automation address the connection bottleneck.",
    risk: "Utility procurement cycles and input costs.",
    source:
      "https://www.hubbell.com/hubbellpowersystems/en/markets/distribution",
  },
  {
    ticker: "CEG",
    name: "Constellation Energy",
    weight: 8,
    theme: "power",
    thesis:
      "Existing nuclear generation supplies power while new capacity is built.",
    risk: "Outages, nuclear liabilities, merchant power prices and non-nuclear assets.",
    source:
      "https://www.constellationenergy.com/our-work/what-we-do/generation.html",
  },
  {
    ticker: "NEE",
    name: "NextEra Energy",
    weight: 8,
    theme: "power",
    thesis:
      "Renewable development and power infrastructure provide deployment capacity.",
    risk: "Interest rates, storm exposure and a continuing fossil-generation business.",
    source: "https://www.nexteraenergy.com/about-us.html",
  },
  {
    ticker: "FSLR",
    name: "First Solar",
    weight: 8,
    theme: "power",
    thesis:
      "Utility-scale solar modules supply the build-out of low-carbon generation.",
    risk: "Trade policy, manufacturing execution, materials and module pricing.",
    source: "https://www.firstsolar.com/en/Solutions/Utility-Scale",
  },
  {
    ticker: "TT",
    name: "Trane Technologies",
    weight: 6,
    theme: "efficiency",
    thesis:
      "Building thermal systems and electrification lower energy required for heating and cooling.",
    risk: "Construction cycles, refrigerants and customer payback periods.",
    source:
      "https://www.tranetechnologies.com/en/index/innovation/electrification.html",
  },
  {
    ticker: "CARR",
    name: "Carrier Global",
    weight: 5,
    theme: "efficiency",
    thesis: "Efficient HVAC equipment supports building retrofits.",
    risk: "Housing demand, financing costs and refrigerant transition.",
    source: "https://www.carrier.com/us/en/commercial/",
  },
  {
    ticker: "JCI",
    name: "Johnson Controls",
    weight: 5,
    theme: "efficiency",
    thesis: "Building controls and thermal equipment reduce wasted energy.",
    risk: "Retrofit execution and customer capital budgets.",
    source: "https://www.johnsoncontrols.com/",
  },
  {
    ticker: "ROK",
    name: "Rockwell Automation",
    weight: 4,
    theme: "efficiency",
    thesis: "Industrial automation supports more efficient production.",
    risk: "Factory investment cycle; automation is not automatically an emissions reduction.",
    source: "https://www.rockwellautomation.com/",
  },
  {
    ticker: "APH",
    name: "Amphenol",
    weight: 6,
    theme: "components",
    thesis: "Interconnects and sensors support industrial electrification.",
    risk: "Diversified end markets; no claim that all revenue is green.",
    source: "https://www.amphenol.com/markets/industrial",
  },
  {
    ticker: "T-BILLS",
    name: "Short-dated US Treasury bills",
    weight: 20,
    theme: "reserve",
    thesis:
      "Liquidity for primary capital raises and repricing after the announcement.",
    risk: "Cash drag; the reserve has no direct decarbonisation claim.",
    source:
      "https://www.treasurydirect.gov/marketable-securities/treasury-bills/",
  },
];
export const STRESSES = {
  none: {
    name: "No assumed price shock",
    shocks: { grid: 0, power: 0, efficiency: 0, components: 0, reserve: 0 },
  },
  delay: {
    name: "Deployment delays",
    shocks: {
      grid: -20,
      power: -25,
      efficiency: -15,
      components: -20,
      reserve: 0,
    },
  },
  crowded: {
    name: "Crowded-trade repricing",
    shocks: {
      grid: -30,
      power: -30,
      efficiency: -30,
      components: -30,
      reserve: 0,
    },
  },
  build: {
    name: "Faster deployment",
    shocks: { grid: 15, power: 20, efficiency: 12, components: 15, reserve: 0 },
  },
};
export function allocate(
  weights = Object.fromEntries(HOLDINGS.map((h) => [h.ticker, h.weight])),
) {
  const rows = HOLDINGS.map((h) => ({
    ...h,
    weight: weights[h.ticker],
    dollars: (FUND * weights[h.ticker]) / 100,
  }));
  const problems = [];
  if (rows.some((h) => !Number.isFinite(h.weight) || h.weight < 0))
    problems.push("Weights must be finite and non-negative.");
  const total = rows.reduce((s, h) => s + h.weight, 0);
  if (Math.abs(total - 100) > 1e-7)
    problems.push(
      `Allocation totals ${total.toFixed(1)}%; it must equal 100%.`,
    );
  if (rows.some((h) => h.theme !== "reserve" && h.weight > 8))
    problems.push("Single-company limit: 8%.");
  const themes = Object.keys(THEMES).map((key) => ({
    key,
    ...THEMES[key],
    weight: rows
      .filter((h) => h.theme === key)
      .reduce((s, h) => s + h.weight, 0),
  }));
  if (themes.some((t) => t.key !== "reserve" && t.weight > 35))
    problems.push("Single-theme limit: 35%.");
  if (rows.find((h) => h.theme === "reserve").weight < 10)
    problems.push("Treasury-bill reserve must be at least 10%.");
  return { rows, themes, total, problems, valid: problems.length === 0 };
}
export function stressPortfolio(allocation, scenario = "none") {
  if (!allocation.valid)
    throw new Error(
      "Balance the allocation before calculating a stress result.",
    );
  const stress = STRESSES[scenario];
  if (!stress) throw new Error("Unknown scenario.");
  const change = allocation.rows.reduce(
    (s, h) => s + (h.dollars * stress.shocks[h.theme]) / 100,
    0,
  );
  return { change, percent: (change / FUND) * 100, ending: FUND + change };
}
