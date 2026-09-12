import { readFile } from "node:fs/promises";
import path from "node:path";
import Link from "next/link";

type Level = "belastbar" | "eingeschränkt" | "dünn" | "keine";
type Family = {
  id: string;
  label: string;
  weight: number;
  companies: number;
  metrics: { id: string; weight: number; evidence: string }[];
};
type Pillar = {
  id: "E" | "S" | "G";
  name: string;
  maxScore: number;
  levels: Record<Level, number>;
  scoreHist: { from: number; to: number; companies: number }[];
  families: Family[];
};
type Payload = {
  total: number;
  rules: {
    anchorWeight: number;
    minFamilies: number;
    minScore: number;
    partialScore: number;
    minPeers: number;
    narrowBand: number;
    levels: Record<Level, string>;
  };
  values: { n: number; companies: number }[];
  valuesMedian: number;
  pillars: Pillar[];
  combos: { pattern: string; companies: number }[];
  sectors: { sector: string; companies: number; E: number; S: number; G: number; all3: number; rankable: number }[];
  funnel: { label: string; companies: number }[];
  rankableList: {
    ticker: string;
    company: string;
    gics_sector: string;
    E_score: number;
    S_score: number;
    G_score: number;
    e_band_width: number | null;
  }[];
};

const LEVELS: Level[] = ["belastbar", "eingeschränkt", "dünn", "keine"];
const de = (v: number, d = 0) =>
  v.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });

async function load(): Promise<Payload> {
  const file = path.join(process.cwd(), "public", "data", "belastbarkeit.json");
  return JSON.parse(await readFile(file, "utf8")) as Payload;
}

/** Waagerechtes Balkendiagramm: y = Kategorie, x = Anzahl Firmen. */
function HBars({
  rows,
  max,
  label,
  highlight,
  unit = "Firmen",
}: {
  rows: { key: string; label: string; value: number; tone?: string }[];
  max: number;
  label: string;
  highlight?: (key: string) => boolean;
  unit?: string;
}) {
  return (
    <div className="hbars" role="img" aria-label={label}>
      {rows.map((r) => (
        <div
          key={r.key}
          className={`hrow${highlight?.(r.key) ? " hi" : ""}`}
          title={`${r.label}: ${de(r.value)} ${unit}`}
        >
          <span className="hl">{r.label}</span>
          <span className="ht">
            <span
              className={`hb${r.tone ? ` ${r.tone}` : ""}`}
              style={{ width: `${max ? (r.value / max) * 100 : 0}%` }}
            />
          </span>
          <span className="hv">{r.value ? de(r.value) : ""}</span>
        </div>
      ))}
    </div>
  );
}

export default async function Page() {
  const d = await load();
  const maxValues = Math.max(...d.values.map((v) => v.companies));
  const threshold = d.rules.minScore;

  return (
    <main>
      <p className="eyebrow">Belastbarkeit</p>
      <h1>Was wir über die Firmen wirklich wissen</h1>
      <p className="lede">
        Nicht jede Zahl trägt ein Urteil. Diese Seite zählt zuerst, wie viele
        Werte je Firma vorliegen, und prüft dann je Bereich, ob das Material
        stark genug ist: Gemessenes wiegt mehr als Selbstauskunft, abgeleitete
        Kennzahlen zählen nicht doppelt, und eine einzelne Quelle reicht nie.
      </p>

      {/* -------------------------------------------------- Werte je Firma */}
      <h2>Wie viele Werte je Firma vorliegen</h2>
      <p className="lede">
        Waagerecht die Zahl der Firmen, senkrecht die Zahl verschiedener
        Kennzahlen, zu denen eine Firma einen Wert hat. Median:{" "}
        <b>{de(d.valuesMedian)} Kennzahlen</b>. Mitgezählt sind auch
        Finanzkennzahlen, deshalb hat fast jede Firma mindestens einen Wert.
      </p>
      <div className="panel">
        <div className="axisnote">
          <span>Anzahl Kennzahlen mit Wert</span>
          <span>Anzahl Firmen →</span>
        </div>
        <HBars
          label="Verteilung der Anzahl Kennzahlen je Firma"
          max={maxValues}
          rows={[...d.values].reverse().map((v) => ({ key: String(v.n), label: String(v.n), value: v.companies }))}
        />
      </div>

      {/* -------------------------------------------------- Regeln */}
      <h2>Wann ein Bereich als belastbar gilt</h2>
      <div className="rules">
        {LEVELS.map((lv) => (
          <div key={lv} className="rule">
            <span className={`lvl ${lv}`}>{lv}</span>
            <span>{d.rules.levels[lv]}</span>
          </div>
        ))}
      </div>
      <p className="lede small">
        <b>Familie:</b> Kennzahlen, die denselben Sachverhalt beschreiben —
        etwa CO₂-Menge, CO₂-Intensität und Schornsteinmessung. Eine Familie
        zählt einmal, mit dem Gewicht ihrer stärksten vorhandenen Kennzahl.{" "}
        <b>Gewicht:</b> Beweiskraft, nicht Wichtigkeit — 1,0 gemessen oder
        behördlich festgestellt, 0,8 gesetzlich gemeldet, 0,5–0,7 abgeleitet
        oder unsicher zugeordnet, 0,3–0,4 Bewertung von Offenlegung, 0,2
        bloßer Meldestatus. Die Werte sind gesetzt und stehen in{" "}
        <code>pipeline/reliability.py</code>.
      </p>

      {/* -------------------------------------------------- E, S, G */}
      <h2>Umwelt, Soziales, Unternehmensführung</h2>
      <div className="pillars">
        {d.pillars.map((p) => {
          const histMax = Math.max(...p.scoreHist.map((h) => h.companies));
          const hist = [...p.scoreHist].reverse();
          return (
            <section key={p.id} className="pillar">
              <div className="axishead">
                <span className="t">
                  {p.id} · {p.name}
                </span>
                <span className="h">max. {de(p.maxScore, 1)} Punkte</span>
              </div>
              <div className="panel tight">
                <div className="big">
                  <span className="v">{de(p.levels.belastbar)}</span>
                  <span className="s">
                    Firmen belastbar · {de((p.levels.belastbar / d.total) * 100)} %
                  </span>
                </div>
                <div className="stack" aria-label={`Stufen im Bereich ${p.name}`}>
                  {LEVELS.map((lv) => (
                    <span
                      key={lv}
                      className={`seg ${lv}`}
                      style={{ width: `${(p.levels[lv] / d.total) * 100}%` }}
                      title={`${lv}: ${p.levels[lv]} Firmen`}
                    />
                  ))}
                </div>
                <ul className="legend">
                  {LEVELS.map((lv) => (
                    <li key={lv}>
                      <span className={`dot ${lv}`} />
                      {lv} <b>{de(p.levels[lv])}</b>
                    </li>
                  ))}
                </ul>

                <p className="sub">Verteilung der Punkte</p>
                <div className="axisnote">
                  <span>Punkte</span>
                  <span>Firmen →</span>
                </div>
                <HBars
                  label={`Punkteverteilung ${p.name}`}
                  max={histMax}
                  rows={hist.map((h) => ({
                    key: String(h.from),
                    label: `${de(h.from, 2)}–${de(h.to, 2)}`,
                    value: h.companies,
                    tone: h.from >= threshold ? "ok" : undefined,
                  }))}
                />
                <p className="hint">
                  Grün: Summe ab {de(threshold, 1)} — dazu braucht es noch zwei
                  Familien und einen Anker.
                </p>

                <p className="sub">Familien</p>
                <table className="mini">
                  <thead>
                    <tr>
                      <th>Familie</th>
                      <th className="num">Gewicht</th>
                      <th className="num">Firmen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.families.map((f) => (
                      <tr key={f.id} title={[...new Set(f.metrics.map((m) => m.evidence))].join(" · ")}>
                        <td>
                          {f.label}
                          {f.weight >= d.rules.anchorWeight && <span className="chip good anchor">Anker</span>}
                        </td>
                        <td className="num">{de(f.weight, 1)}</td>
                        <td className="num">{de(f.companies)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}
      </div>

      {/* -------------------------------------------------- Zusammen */}
      <h2>Alle drei Bereiche zusammen</h2>
      <p className="lede">
        Ein gemeinsames Ranking über E, S und G setzt voraus, dass in allen
        drei Bereichen belastbares Material vorliegt. Aber auch das reicht
        nicht: Verglichen wird innerhalb der Branche, also braucht es genug
        solche Firmen je Branche, und der Platz muss unabhängig von der
        Methodenwahl stabil sein.
      </p>
      <div className="panel">
        <div className="funnel">
          {d.funnel.map((f, i) => (
            <div key={f.label} className={`frow${i >= 4 ? " key" : ""}`}>
              <span className="fl">{f.label}</span>
              <span className="ft">
                <span className="fb" style={{ width: `${(f.companies / d.total) * 100}%` }} />
              </span>
              <span className="fv">
                {de(f.companies)} <span className="dim">· {de((f.companies / d.total) * 100)} %</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="twocol">
        <section>
          <div className="axishead">
            <span className="t">Kombinationen</span>
            <span className="h">in welchen Bereichen belastbar</span>
          </div>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Muster</th>
                  <th className="num">Firmen</th>
                </tr>
              </thead>
              <tbody>
                {d.combos.map((c) => (
                  <tr key={c.pattern}>
                    <td className="mono">
                      {c.pattern.split("").map((ch, i) => (
                        <span key={i} className={ch === "·" ? "pat off" : "pat on"}>
                          {ch === "·" ? ["E", "S", "G"][i] : ch}
                        </span>
                      ))}
                    </td>
                    <td className="num">{de(c.companies)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <div className="axishead">
            <span className="t">Je Branche</span>
            <span className="h">Ranking ab {d.rules.minPeers} Firmen mit allen drei</span>
          </div>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Branche</th>
                  <th className="num">Firmen</th>
                  <th className="num">E</th>
                  <th className="num">S</th>
                  <th className="num">G</th>
                  <th className="num">alle 3</th>
                </tr>
              </thead>
              <tbody>
                {d.sectors.map((s) => (
                  <tr key={s.sector}>
                    <td>{s.sector}</td>
                    <td className="num dim">{s.companies}</td>
                    <td className="num">{s.E}</td>
                    <td className="num">{s.S}</td>
                    <td className="num">{s.G}</td>
                    <td className="num">
                      {s.rankable ? <span className="chip good">{s.all3}</span> : <span className="dim">{s.all3}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <h2>Firmen, für die ein gemeinsames Ranking möglich ist</h2>
      <p className="lede">
        In allen drei Bereichen belastbar und in einer Branche mit mindestens{" "}
        {d.rules.minPeers} solchen Firmen. Das Umwelt-Rangband stammt aus der
        Monte-Carlo-Analyse; für S und G gibt es noch kein Rangband, dort ist
        die Stabilität des Platzes also noch nicht geprüft.
      </p>
      {d.rankableList.length === 0 ? (
        <div className="note">
          <b>Für keine Firma.</b> Keine Branche erreicht {d.rules.minPeers} Firmen,
          die in allen drei Bereichen belastbar sind.
        </div>
      ) : (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Kürzel</th>
                <th>Firma</th>
                <th>Branche</th>
                <th className="num">E-Punkte</th>
                <th className="num">S-Punkte</th>
                <th className="num">G-Punkte</th>
                <th className="num">E-Rangband</th>
              </tr>
            </thead>
            <tbody>
              {d.rankableList.map((r) => (
                <tr key={r.ticker}>
                  <td className="tick">
                    <Link href={`/firma/${r.ticker}`}>{r.ticker}</Link>
                  </td>
                  <td>
                    <Link href={`/firma/${r.ticker}`}>{r.company}</Link>
                  </td>
                  <td className="dim">{r.gics_sector}</td>
                  <td className="num">{de(r.E_score, 1)}</td>
                  <td className="num">{de(r.S_score, 1)}</td>
                  <td className="num">{de(r.G_score, 1)}</td>
                  <td className="num">
                    {r.e_band_width == null ? (
                      <span className="dim">–</span>
                    ) : r.e_band_width <= d.rules.narrowBand ? (
                      <span className="chip good">{de(r.e_band_width)} Pkt.</span>
                    ) : (
                      <span className="chip warn">{de(r.e_band_width)} Pkt.</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer>
        <span>Regeln: pipeline/reliability.py</span>
        <span>je Firma: downloads/belastbarkeit.csv</span>
      </footer>
    </main>
  );
}
