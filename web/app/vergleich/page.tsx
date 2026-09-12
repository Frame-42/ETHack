import { readdir } from "node:fs/promises";
import path from "node:path";
import Compare, { type CompareMetric, type CompareRow } from "./compare";
import { getDataset } from "@/lib/data";

async function logoTickers(): Promise<Set<string>> {
  try {
    const files = await readdir(path.join(process.cwd(), "public", "logos"));
    return new Set(files.filter((f) => f.endsWith(".png")).map((f) => f.slice(0, -4)));
  } catch {
    return new Set();
  }
}

export default async function Page() {
  const data = await getDataset();
  const logos = await logoTickers();

  const rows: CompareRow[] = data.companies.map((c) => ({
    ticker: c.ticker,
    company: c.company,
    sector: c.sector,
    logo: logos.has(c.ticker),
    values: Object.fromEntries(c.metrics.map((m) => [m.metric, m.value])),
  }));
  const listed = new Set(rows.map((r) => r.ticker));
  for (const c of data.withoutData) {
    if (!listed.has(c.ticker)) {
      rows.push({ ticker: c.ticker, company: c.company, sector: c.sector, logo: logos.has(c.ticker), values: {} });
    }
  }

  // Wie viele Firmen haben einen Wert je Kennzahl -- bestimmt die Reihenfolge der Auswahl.
  const counts = new Map<string, number>();
  for (const r of rows) {
    for (const [k, v] of Object.entries(r.values)) {
      if (v !== null && Number.isFinite(v)) counts.set(k, (counts.get(k) ?? 0) + 1);
    }
  }
  const metrics: CompareMetric[] = Object.entries(data.metrics)
    .map(([id, m]) => ({
      id,
      label: m.label,
      unit: m.unit,
      axis: m.axis,
      direction: m.direction,
      count: counts.get(id) ?? 0,
      source: data.sources[m.sourceId]?.name ?? m.sourceId,
    }))
    .filter((m) => m.count > 0)
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "de"));

  return (
    <main>
      <p className="eyebrow">Vergleich</p>
      <h1>Kennzahlen nebeneinander</h1>
      <p className="lede">
        Kennzahlen auswählen, alle 503 Firmen erscheinen mit genau diesen
        Werten. Die Auswahl ist nach Abdeckung sortiert, die Zahl in Klammern
        sagt, für wie viele Firmen ein Wert vorliegt. Der Schalter
        „normalisiert“ rechnet jede Spalte auf 0 bis 1 um: 1 ist der beste
        Wert in dieser Kennzahl, 0 der schlechteste.
      </p>
      <Compare rows={rows} metrics={metrics} />
      <footer>
        <span>Stand {data.generatedAt}</span>
        <span>{metrics.length} Kennzahlen mit mindestens einem Wert</span>
      </footer>
    </main>
  );
}
