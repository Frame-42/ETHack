import Link from "next/link";
import { notFound } from "next/navigation";
import { AXES, fmt, getDataset } from "@/lib/data";

export async function generateStaticParams() {
  const data = await getDataset();
  return [...data.companies, ...data.withoutData].map((c) => ({
    ticker: c.ticker,
  }));
}

export default async function Page({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const data = await getDataset();
  const c = data.companies.find((x) => x.ticker === ticker);
  if (!c) {
    const empty = data.withoutData.find((x) => x.ticker === ticker);
    if (!empty) notFound();
    return (
      <main>
        <p className="back">
          <Link href="/">← alle Firmen</Link>
        </p>
        <p className="eyebrow">
          {empty.ticker} · {empty.sector}
        </p>
        <h1>{empty.company}</h1>
        <div className="note">
          <b>Zu dieser Firma liegt kein einziger Wert vor.</b> Keine der{" "}
          {Object.keys(data.sources).length} Quellen liefert etwas: keine
          meldepflichtigen Anlagen bei der EPA, kein Eintrag bei SBTi, keine
          zuordenbaren OSHA-Meldungen. Das ist typisch für Finanzdienstleister,
          deren Fußabdruck in finanzierten Emissionen liegt, also in Scope 3.
          Die Firma ist deshalb als nicht bewertbar gelistet, nicht mit null.
        </div>
        <footer>
          <span>Stand {data.generatedAt}</span>
          <span>{empty.ticker}</span>
        </footer>
      </main>
    );
  }

  const byAxis = new Map<string, typeof c.metrics>();
  for (const m of c.metrics) {
    const list = byAxis.get(m.axis) ?? [];
    list.push(m);
    byAxis.set(m.axis, list);
  }
  const order = Object.keys(AXES).filter((a) => byAxis.has(a));
  const sources = [...new Set(c.metrics.map((m) => m.sourceId))];

  return (
    <main>
      <p className="back">
        <Link href="/">← alle Firmen</Link>
      </p>
      <p className="eyebrow">
        {c.ticker} · {c.sector} · {c.subIndustry}
      </p>
      <h1>{c.company}</h1>
      <p className="lede">
        {c.metrics.length} Werte aus {sources.length}{" "}
        {sources.length === 1 ? "Quelle" : "Quellen"}. Jede Zeile nennt, woher
        sie stammt und für welches Geschäftsjahr sie gilt.
      </p>

      {order.map((axis) => {
        const rows = byAxis.get(axis)!;
        return (
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
                    <th className="num">Wert</th>
                    <th>Einheit</th>
                    <th className="num">Jahr</th>
                    <th>Quelle</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((m) => (
                    <tr key={m.metric}>
                      <td>
                        {m.label}
                        <br />
                        <code className="dim">{m.metric}</code>
                      </td>
                      <td className="num">{fmt(m.value, m.unit)}</td>
                      <td className="dim">{m.unit}</td>
                      <td className="num">
                        {m.year ?? "–"}
                        {m.partial && (
                          <>
                            {" "}
                            <span
                              className="chip warn"
                              title="laufendes Jahr, noch unvollständig"
                            >
                              Teiljahr
                            </span>
                          </>
                        )}
                      </td>
                      <td className="src">
                        <a
                          href={m.sourceUrl}
                          target="_blank"
                          rel="noreferrer noopener"
                        >
                          {m.sourceName}
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}

      <h2>Herkunft dieser Werte</h2>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Quelle</th>
              <th>Zugang</th>
              <th>Messart</th>
              <th>Grenze</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((sid) => {
              const s = data.sources[sid];
              if (!s) return null;
              return (
                <tr key={sid}>
                  <td>
                    <a href={s.url} target="_blank" rel="noreferrer noopener">
                      {s.name}
                    </a>
                  </td>
                  <td className="dim">{s.access}</td>
                  <td className="dim">{s.measurement}</td>
                  <td className="dim">{s.caveat}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <footer>
        <span>Stand {data.generatedAt}</span>
        <span>{c.ticker}</span>
      </footer>
    </main>
  );
}
