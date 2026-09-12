import Browser from "./browser";
import { getDataset } from "@/lib/data";

function pick(
  metrics: { metric: string; value: number | null }[],
  name: string,
): number | null {
  const m = metrics.find((x) => x.metric === name);
  return m && m.value !== null ? m.value : null;
}

export default async function Page() {
  const data = await getDataset();

  const rows = data.companies.map((c) => {
    const p10 = pick(c.metrics, "rank_p10");
    const p90 = pick(c.metrics, "rank_p90");
    return {
      ticker: c.ticker,
      company: c.company,
      sector: c.sector,
      n: c.metrics.length,
      sources: new Set(c.metrics.map((m) => m.sourceId)).size,
      rank: pick(c.metrics, "rank_p50"),
      band:
        p10 !== null && p90 !== null ? ([p10, p90] as [number, number]) : null,
      co2: pick(c.metrics, "co2_intensity"),
      dart: pick(c.metrics, "dart_rate"),
      sbti: pick(c.metrics, "sbti_validated"),
    };
  });

  // Firmen ohne jeden Wert trotzdem listen: Sie fehlen nicht aus Versehen,
  // sondern weil keine freie Quelle etwas über sie hergibt.
  for (const c of data.withoutData) {
    rows.push({
      ticker: c.ticker,
      company: c.company,
      sector: c.sector,
      n: 0,
      sources: 0,
      rank: null,
      band: null,
      co2: null,
      dart: null,
      sbti: null,
    });
  }

  const sectors = [...new Set(rows.map((r) => r.sector))].sort();
  const values = data.companies.reduce((s, c) => s + c.metrics.length, 0);
  const sourceCount = new Set(
    data.companies.flatMap((c) => c.metrics.map((m) => m.sourceId)),
  ).size;

  return (
    <main>
      <p className="eyebrow">Gesammelter Datensatz</p>
      <h1>Alle Werte, jeder mit seiner Quelle</h1>
      <p className="lede">
        Zwölf Quellen, an einem Tag zusammengetragen und einzeln am Endpunkt
        geprüft. Der Datensatz liegt im Langformat vor, damit die Herkunft an
        jedem einzelnen Wert hängt und nicht nur an der Spalte — eine
        CO₂-Zahl kann gemessen, gerechnet oder abgeschrieben sein, und das
        muss sichtbar bleiben.
      </p>

      <div className="stats">
        <div className="stat">
          <div className="k">Firmen mit Daten</div>
          <div className="v">{data.companies.length}</div>
          <div className="s">von 503 im Index</div>
        </div>
        <div className="stat">
          <div className="k">Werte in dieser Sicht</div>
          <div className="v">{values.toLocaleString("de-DE")}</div>
          <div className="s">jüngstes volles Jahr je Kennzahl</div>
        </div>
        <div className="stat">
          <div className="k">Kennzahlen</div>
          <div className="v">{Object.keys(data.metrics).length}</div>
          <div className="s">über sieben Achsen</div>
        </div>
        <div className="stat">
          <div className="k">Quellen</div>
          <div className="v">{sourceCount}</div>
          <div className="s">zwei mit Schlüsselpflicht</div>
        </div>
        <div className="stat">
          <div className="k">nicht bewertbar</div>
          <div className="v">{data.withoutData.length}</div>
          <div className="s">ausdrücklich, nicht als Null</div>
        </div>
      </div>

      <Browser rows={rows} sectors={sectors} />

      <div className="note">
        <b>Das Rangband ist das Ergebnis, nicht der Platz.</b> Die Spalte zeigt
        das Intervall vom 10. bis zum 90. Perzentil über 1500 zufällig gezogene
        Methodenkombinationen. Wo es breit ist, ist die Einordnung eine Frage
        der Methode und keine Eigenschaft der Firma.
      </div>

      <footer>
        <span>Stand {data.generatedAt}</span>
        <span>Langformat: data/out/dataset_long.parquet</span>
        <span>{data.withoutData.length} Firmen ohne jeden Wert</span>
      </footer>
    </main>
  );
}
