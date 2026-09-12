import { readdir } from "node:fs/promises";
import path from "node:path";
import Browser, { type MetricOption, type Row } from "./browser";
import { getDataset } from "@/lib/data";

async function logoTickers(): Promise<Set<string>> {
  try {
    const files = await readdir(path.join(process.cwd(), "public", "logos"));
    return new Set(
      files.filter((f) => f.endsWith(".png")).map((f) => f.replace(/\.png$/, "")),
    );
  } catch {
    return new Set();
  }
}

export default async function Page() {
  const data = await getDataset();
  const logos = await logoTickers();

  const rows: Row[] = data.companies.map((c) => ({
    ticker: c.ticker,
    company: c.company,
    sector: c.sector,
    n: c.metrics.length,
    sources: new Set(c.metrics.map((m) => m.sourceId)).size,
    assessed: c.assessed ?? true,
    logo: logos.has(c.ticker),
    values: Object.fromEntries(c.metrics.map((m) => [m.metric, m.value])),
  }));

  // Firmen ohne jeden Wert trotzdem listen: Sie fehlen nicht aus Versehen,
  // sondern weil keine freie Quelle etwas über sie hergibt.
  const listed = new Set(rows.map((r) => r.ticker));
  for (const c of data.withoutData) {
    if (listed.has(c.ticker)) continue;
    rows.push({
      ticker: c.ticker,
      company: c.company,
      sector: c.sector,
      n: 0,
      sources: 0,
      assessed: false,
      logo: logos.has(c.ticker),
      values: {},
    });
  }

  const metrics: MetricOption[] = Object.entries(data.metrics).map(([id, m]) => ({
    id,
    label: m.label,
    unit: m.unit,
    axis: m.axis,
    direction: m.direction,
  }));

  const sectors = [...new Set(rows.map((r) => r.sector))].sort();
  const assessed = rows.filter((r) => r.assessed).length;
  const values = data.companies.reduce((s, c) => s + c.metrics.length, 0);
  const sourceCount = new Set(
    data.companies.flatMap((c) => c.metrics.map((m) => m.sourceId)),
  ).size;

  return (
    <main>
      <p className="eyebrow">Gesammelter Datensatz</p>
      <h1>Alle Werte, jeder mit seiner Quelle</h1>
      <p className="lede">
        Aus frei zugänglichen Quellen zusammengetragen und einzeln am Endpunkt
        geprüft, dazu die Datensätze aus dem Team. Die Herkunft hängt an jedem
        einzelnen Wert und nicht nur an der Spalte — eine CO₂-Zahl kann
        gemessen, gerechnet oder abgeschrieben sein, und das muss sichtbar
        bleiben. Spaltenköpfe sortieren; über „Kennzahl-Spalte“ lässt sich jede
        der {metrics.length} Kennzahlen einblenden und danach sortieren.
      </p>

      <div className="stats">
        <div className="stat">
          <div className="k">Firmen mit Nachhaltigkeitsdaten</div>
          <div className="v">{assessed}</div>
          <div className="s">von 503 im Index</div>
        </div>
        <div className="stat">
          <div className="k">Werte in dieser Sicht</div>
          <div className="v">{values.toLocaleString("de-DE")}</div>
          <div className="s">jüngstes volles Jahr je Kennzahl</div>
        </div>
        <div className="stat">
          <div className="k">Kennzahlen</div>
          <div className="v">{metrics.length}</div>
          <div className="s">über sieben Achsen</div>
        </div>
        <div className="stat">
          <div className="k">Quellen</div>
          <div className="v">{sourceCount}</div>
          <div className="s">zwei mit Schlüsselpflicht</div>
        </div>
        <div className="stat">
          <div className="k">nicht bewertbar</div>
          <div className="v">{rows.length - assessed}</div>
          <div className="s">höchstens Finanzdaten, nicht als Null</div>
        </div>
      </div>

      <Browser rows={rows} sectors={sectors} metrics={metrics} />

      <div className="note">
        <b>Das Rangband ist das Ergebnis, nicht der Platz.</b> Die Spalte zeigt
        das Intervall vom 10. bis zum 90. Perzentil über 1500 zufällig gezogene
        Methodenkombinationen. Wo es breit ist, ist die Einordnung eine Frage
        der Methode und keine Eigenschaft der Firma. Beim Sortieren nach dieser
        Spalte zählt der Median.
      </div>

      <footer>
        <span>Stand {data.generatedAt}</span>
        <span>Logos: Favicons der Firmen-Websites, Websites aus Wikidata und SEC</span>
        <span>{rows.length - assessed} Firmen ohne Nachhaltigkeitswert</span>
      </footer>
    </main>
  );
}
