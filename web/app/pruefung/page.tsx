import { readFile } from "node:fs/promises";
import path from "node:path";
import Review, { type ReviewFlag } from "./review";

type Summary = {
  flags: number;
  fehler: number;
  pruefen: number;
  je_regel: Record<string, number>;
  firmen_betroffen: number;
  ranking_relevant: number;
  ki?: {
    modell: string;
    eskalation: string;
    urteile: Record<string, number>;
    ursachen: Record<string, number>;
    routen: Record<string, number>;
    eskaliert: number;
    regel_bestaetigt_fehler: number;
    regel_widersprochen_fehler: number;
    tokens_gesamt: number;
    referenz: { faelle: number; urteil_richtig: number; ursache_richtig: number };
  };
  referenz_faelle?: {
    regel: string;
    ticker: string;
    erwartet: string;
    ki_urteil: string;
    urteil_richtig: boolean;
    erwartete_ursache: string;
    ki_ursache: string;
    ursache_richtig: boolean;
    konfidenz: number;
    route: string;
    beleg: string;
  }[];
};

async function readJson<T>(name: string, fallback: T): Promise<T> {
  try {
    return JSON.parse(await readFile(path.join(process.cwd(), "public", "data", name), "utf8")) as T;
  } catch {
    return fallback;
  }
}

const de = (v: number, d = 0) =>
  v.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });

export default async function Page() {
  const s = await readJson<Summary>("pruefung.json", {
    flags: 0, fehler: 0, pruefen: 0, je_regel: {}, firmen_betroffen: 0, ranking_relevant: 0,
  });
  const flags = await readJson<ReviewFlag[]>("flags_gepruft.json", []);
  const ki = s.ki;

  return (
    <main>
      <p className="eyebrow">Prüfung</p>
      <h1>Auffällige Werte, geprüft von Regeln, KI und Mensch</h1>
      <p className="lede">
        Regeln finden Kandidaten und legen zu jedem ein Belegpaket an: Wert,
        Zeitreihe, Branchenvergleich, Rohdaten-Auszug. Ein Sprachmodell
        beurteilt jedes Paket und nennt die wahrscheinlichste Ursache. Wer
        entscheidet, bestimmt eine feste Regel, nicht das Modell: Unsichere,
        folgenreiche oder korrigierende Fälle gehen an einen Menschen.
      </p>

      <div className="pipeline" aria-label="Prüfablauf">
        <div className="step"><span className="n">1</span><b>Regeln</b><span>{de(s.flags)} Kandidaten, {de(s.fehler)} Fehler, {de(s.pruefen)} zu prüfen</span></div>
        <div className="step"><span className="n">2</span><b>KI-Gutachten</b><span>{ki ? `${ki.modell}, unsichere Fälle an ${ki.eskalation}` : "nicht gelaufen"}</span></div>
        <div className="step"><span className="n">3</span><b>Weiterleitung</b><span>{ki ? `${de(ki.routen.automatisch ?? 0)} automatisch, ${de(ki.routen.mensch ?? 0)} an Menschen` : "–"}</span></div>
        <div className="step"><span className="n">4</span><b>Mensch</b><span>Entscheidung in data/review/entscheidungen.csv, hat Vorrang</span></div>
      </div>

      {ki && (
        <div className="stats">
          <div className="stat">
            <div className="k">KI bestätigt Regel-Fehler</div>
            <div className="v">{de(ki.regel_bestaetigt_fehler)}</div>
            <div className="s">von {de(s.fehler)} Fehler-Flags</div>
          </div>
          <div className="stat">
            <div className="k">KI widerspricht Regel</div>
            <div className="v">{de(ki.regel_widersprochen_fehler)}</div>
            <div className="s">Fehler-Flag, KI hält plausibel</div>
          </div>
          <div className="stat">
            <div className="k">Referenzfälle richtig</div>
            <div className="v">{de(ki.referenz.urteil_richtig)}/{de(ki.referenz.faelle)}</div>
            <div className="s">Ursache richtig: {de(ki.referenz.ursache_richtig)}/{de(ki.referenz.faelle)}</div>
          </div>
          <div className="stat">
            <div className="k">Tokens gesamt</div>
            <div className="v">{de(ki.tokens_gesamt / 1000)}k</div>
            <div className="s">{de(ki.eskaliert)} Fälle eskaliert</div>
          </div>
        </div>
      )}

      {s.referenz_faelle && s.referenz_faelle.length > 0 && (
        <>
          <h2>Wie gut die KI ist — gemessen an belegten Fällen</h2>
          <p className="lede small">
            Für diese Fälle ist die richtige Antwort aus den Rohdaten bekannt,
            unabhängig vom Modell. Nur so lässt sich sagen, ob man einem Urteil
            trauen kann.
          </p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Fall</th><th>Beleg</th><th>erwartet</th><th>KI</th><th>Ursache (KI)</th><th className="num">Konfidenz</th><th>Weg</th>
                </tr>
              </thead>
              <tbody>
                {s.referenz_faelle.map((r) => (
                  <tr key={`${r.regel}-${r.ticker}`}>
                    <td className="mono">{r.ticker}<br /><span className="dim">{r.regel}</span></td>
                    <td className="dim">{r.beleg}</td>
                    <td>{r.erwartet}</td>
                    <td><span className={`chip ${r.urteil_richtig ? "good" : "warn"}`}>{r.ki_urteil}</span></td>
                    <td><span className={`chip ${r.ursache_richtig ? "good" : ""}`}>{r.ki_ursache}</span></td>
                    <td className="num">{de(r.konfidenz, 2)}</td>
                    <td>{r.route}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>Alle Fälle</h2>
      <Review flags={flags} />

      <div className="note">
        <b>So entscheidet ein Mensch.</b> Eine Zeile in{" "}
        <code>data/review/entscheidungen.csv</code> mit <code>flag_id</code>,{" "}
        <code>entscheidung</code> (fehler, ok, korrigieren), Name, Datum und
        einem Satz Begründung. Beim nächsten Lauf von{" "}
        <code>scripts/10_pruefung.py</code> hat diese Entscheidung Vorrang vor
        Regel und KI und fließt mit Namen in den Datensatz.
      </div>

      <footer>
        <span>Regeln: pipeline/quality.py</span>
        <span>KI: pipeline/ai_review.py</span>
        <span>Downloads: flags_gepruft.csv</span>
      </footer>
    </main>
  );
}
