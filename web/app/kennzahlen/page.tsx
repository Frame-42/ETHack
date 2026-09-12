import { AXES, getDataset } from "@/lib/data";

export default async function Page() {
  const data = await getDataset();

  const coverage = new Map<string, Set<string>>();
  for (const c of data.companies) {
    for (const m of c.metrics) {
      const s = coverage.get(m.metric) ?? new Set<string>();
      s.add(c.ticker);
      coverage.set(m.metric, s);
    }
  }

  const byAxis = new Map<string, [string, (typeof data.metrics)[string]][]>();
  for (const [id, def] of Object.entries(data.metrics)) {
    const list = byAxis.get(def.axis) ?? [];
    list.push([id, def]);
    byAxis.set(def.axis, list);
  }

  return (
    <main>
      <p className="eyebrow">Sicht 2</p>
      <h1>Nach Datentyp</h1>
      <p className="lede">
        Dieselben Werte, gruppiert nach dem, was sie messen. Der Pfeil gibt die
        Richtung an: ↓ heißt, kleiner ist besser. Die Spalte Firmen zeigt, für
        wie viele Indexmitglieder ein Wert vorliegt.
      </p>

      {Object.keys(AXES)
        .filter((a) => byAxis.has(a))
        .map((axis) => (
          <section key={axis} className="axisblock">
            <div className="axishead">
              <span className="t">{AXES[axis].label}</span>
              <span className="h">{AXES[axis].hint}</span>
            </div>
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Kennzahl</th>
                    <th>technisch</th>
                    <th>Einheit</th>
                    <th className="num">Richtung</th>
                    <th className="num">Firmen</th>
                    <th>Quelle</th>
                  </tr>
                </thead>
                <tbody>
                  {byAxis
                    .get(axis)!
                    .sort(
                      (a, b) =>
                        (coverage.get(b[0])?.size ?? 0) -
                        (coverage.get(a[0])?.size ?? 0),
                    )
                    .map(([id, def]) => (
                      <tr key={id}>
                        <td>{def.label}</td>
                        <td>
                          <code>{id}</code>
                        </td>
                        <td className="dim">{def.unit}</td>
                        <td className="num">
                          {def.direction === -1
                            ? "↓"
                            : def.direction === 1
                              ? "↑"
                              : "–"}
                        </td>
                        <td className="num">{coverage.get(id)?.size ?? 0}</td>
                        <td className="src">
                          {data.sources[def.sourceId]?.name ?? def.sourceId}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}

      <div className="note">
        <b>Die Kennzahlen sind nicht gleichwertig.</b> Nebeneinander stehen
        Gemessenes (Schornsteinmessung, behördliche Feststellung), Gemeldetes
        (Selbstauskunft, teils geprüft) und Berechnetes. Wer sie zu einer Note
        verrechnet, sollte diese Unterscheidung mitführen — deshalb steht sie
        an jedem Wert.
      </div>

      <footer>
        <span>Stand {data.generatedAt}</span>
        <span>{Object.keys(data.metrics).length} Kennzahlen</span>
      </footer>
    </main>
  );
}
