import { getDataset } from "@/lib/data";

export default async function Page() {
  const data = await getDataset();
  const entries = Object.entries(data.sources);
  const used = new Map<string, { firmen: Set<string>; werte: number }>();
  for (const c of data.companies) {
    for (const m of c.metrics) {
      const e = used.get(m.sourceId) ?? { firmen: new Set<string>(), werte: 0 };
      e.firmen.add(c.ticker);
      e.werte += 1;
      used.set(m.sourceId, e);
    }
  }

  return (
    <main>
      <p className="eyebrow">Sicht 1</p>
      <h1>Nach Quelle</h1>
      <p className="lede">
        Keine dieser Quellen steht hier, weil sie in einer Dokumentation
        erwähnt wird. Jede wurde am Abrufdatum aufgerufen; wo eine Grenze
        steht, ist sie beim Abruf aufgefallen.
      </p>

      {entries.map(([id, s]) => {
        const u = used.get(id);
        const key = s.access.toLowerCase().includes("schluessel");
        return (
          <section key={id} className="axisblock">
            <div className="axishead">
              <span className="t">{s.name}</span>
              <span className="h">
                {u ? `${u.firmen.size} Firmen · ${u.werte} Werte` : "Hilfsquelle"}
              </span>
              <span style={{ marginLeft: "auto" }}>
                {key ? (
                  <span className="chip warn">Schlüssel nötig</span>
                ) : (
                  <span className="chip good">frei</span>
                )}
              </span>
            </div>
            <div className="tablewrap">
              <table>
                <tbody>
                  <tr>
                    <th style={{ width: "170px" }}>Abrufadresse</th>
                    <td className="mono" style={{ wordBreak: "break-all" }}>
                      <a href={s.url} target="_blank" rel="noreferrer noopener">
                        {s.url}
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <th>Zugang</th>
                    <td>{s.access}</td>
                  </tr>
                  <tr>
                    <th>Lizenz</th>
                    <td>{s.license}</td>
                  </tr>
                  <tr>
                    <th>Abdeckung</th>
                    <td>{s.coverage}</td>
                  </tr>
                  <tr>
                    <th>Messart</th>
                    <td>{s.measurement}</td>
                  </tr>
                  <tr>
                    <th>Grenze</th>
                    <td>{s.caveat}</td>
                  </tr>
                  <tr>
                    <th>Abgerufen</th>
                    <td className="mono">{s.retrieved_at}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        );
      })}

      <div className="note">
        <b>Zwei Schlüssel, beide kostenlos und sofort.</b> Der EPA-Schlüssel für
        die Clean Air Markets schließt die Datenlücke nach 2023 für den
        Stromsektor; ohne ihn greift ein Demo-Schlüssel mit zehn Anfragen je
        Stunde. Der EIA-Schlüssel dient nur der unabhängigen Gegenprobe. Beide
        liegen in <code>.env</code>, die nicht im Repository steht.
      </div>

      <footer>
        <span>Stand {data.generatedAt}</span>
        <span>{entries.length} Quellen</span>
      </footer>
    </main>
  );
}
