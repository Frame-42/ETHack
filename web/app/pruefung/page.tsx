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
  };
  reparaturen?: {
    thema: string;
    ticker: string;
    beleg: string;
    behoben: boolean;
    befund: string;
  }[];
  reparaturen_behoben?: number;
};

// Stand vor der Reparatur, aus data/out/flags_vor_reparatur.csv. Diese Zahlen
// sind der Vergleichsmassstab: Dieselben Regeln fanden 382 Fälle, 246 davon
// gingen an Menschen.
const VORHER = { flags: 382, fehler: 239, firmen: 176, mensch: 246, automatisch: 136 };

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
        Zwei Regeln stehen über allem. <b>Erstens:</b> Entweder eine
        vertrauenswürdige Quelle veröffentlicht den Wert — oder es gibt keinen
        Wert. Jede Zeile ist <i>gemeldet</i> (so veröffentlicht) oder{" "}
        <i>aggregiert</i> (Summe der veröffentlichten Einzelwerte einer Firma);
        selbstgerechnete Kennzahlen wie Intensität, Rate je MWh, Unfallrate,
        Trend und Rangband gibt es hier nicht mehr. <b>Zweitens:</b>
        systematische Fehler gehören repariert, nicht geprüft — deshalb sind
        ihre Ursachen in der Pipeline behoben. Was übrig bleibt, kennzeichnen
        Regeln und ein Sprachmodell; löschen darf nur ein Mensch.
      </p>

      <div className="stats">
        <div className="stat">
          <div className="k">Fälle aus den Regeln</div>
          <div className="v">{de(s.flags)}</div>
          <div className="s">vorher {de(VORHER.flags)}</div>
        </div>
        <div className="stat">
          <div className="k">davon an Menschen</div>
          <div className="v">{ki ? de(ki.routen.mensch ?? 0) : "–"}</div>
          <div className="s">vorher {de(VORHER.mensch)}</div>
        </div>
        <div className="stat">
          <div className="k">betroffene Firmen</div>
          <div className="v">{de(s.firmen_betroffen)}</div>
          <div className="s">vorher {de(VORHER.firmen)}</div>
        </div>
        <div className="stat">
          <div className="k">Reparaturen belegt</div>
          <div className="v">{de(s.reparaturen_behoben ?? 0)}/{de(s.reparaturen?.length ?? 0)}</div>
          <div className="s">Kontrollfälle aus den Rohdaten</div>
        </div>
      </div>

      {s.reparaturen && s.reparaturen.length > 0 && (
        <>
          <h2>Was repariert wurde — und der Beleg, dass es hält</h2>
          <p className="lede small">
            Jede Zeile ist ein Fall, dessen richtige Behandlung aus den
            Rohdaten belegt ist. Die Prüfung läuft bei jedem Lauf mit: Kommt
            eine Ursache zurück, fällt sie hier auf.
          </p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Ursache</th><th>Fall</th><th>Beleg aus den Rohdaten</th><th>Stand heute</th><th>behoben</th>
                </tr>
              </thead>
              <tbody>
                {s.reparaturen.map((r) => (
                  <tr key={`${r.thema}-${r.ticker}`}>
                    <td>{r.thema}</td>
                    <td className="mono">{r.ticker}</td>
                    <td className="dim">{r.beleg}</td>
                    <td className="dim">{r.befund}</td>
                    <td><span className={`chip ${r.behoben ? "good" : "warn"}`}>{r.behoben ? "ja" : "offen"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="docs">
        <a className="btn primary" href="/downloads/pruefung_vorgehen.pdf" download="ETHack-Pruefung-Vorgehen.pdf">Vorgehen als PDF ↓</a>
        <a className="btn" href="/downloads/qualitaetspruefung.pdf" download="ETHack-Qualitaetspruefung.pdf">Ursachenbericht als PDF ↓</a>
        <a className="btn ghost" href="/downloads/flags_gepruft.csv" download>Alle Fälle als CSV ↓</a>
      </div>

      <div className="pipeline" aria-label="Prüfablauf">
        <div className="step"><span className="n">1</span><b>Nur Quellwerte</b><span>gemeldet oder aggregiert, nichts Gerechnetes</span></div>
        <div className="step"><span className="n">2</span><b>Reparatur</b><span>systematische Ursachen in der Pipeline behoben</span></div>
        <div className="step"><span className="n">3</span><b>Regeln</b><span>{de(s.flags)} Kandidaten, {de(s.fehler)} Fehler, {de(s.pruefen)} zu prüfen</span></div>
        <div className="step"><span className="n">4</span><b>KI-Gutachten</b><span>{ki ? `${ki.modell}, unsichere Fälle an ${ki.eskalation}` : "nicht gelaufen"}</span></div>
        <div className="step"><span className="n">5</span><b>Weiterleitung</b><span>{ki ? `${de(ki.routen.automatisch ?? 0)} automatisch, ${de(ki.routen.mensch ?? 0)} an Menschen` : "–"}</span></div>
        <div className="step"><span className="n">6</span><b>Mensch</b><span>Entscheidet per Knopf an jedem Fall, hat beim nächsten Lauf Vorrang</span></div>
      </div>

      {ki && (
        <div className="stats">
          <div className="stat">
            <div className="k">KI-Urteil</div>
            <div className="v">{de(ki.urteile.fehler ?? 0)}/{de(s.flags)}</div>
            <div className="s">Fehler; {de(ki.urteile.plausibel ?? 0)} plausibel, {de(ki.urteile.unklar ?? 0)} unklar</div>
          </div>
          <div className="stat">
            <div className="k">automatisch entschieden</div>
            <div className="v">{de(ki.routen.automatisch ?? 0)}</div>
            <div className="s">{de(ki.eskaliert)} zuvor an {ki.eskalation} eskaliert</div>
          </div>
          <div className="stat">
            <div className="k">an Menschen</div>
            <div className="v">{de(ki.routen.mensch ?? 0)}</div>
            <div className="s">Widerspruch, große Wirkung oder unsicher</div>
          </div>
          <div className="stat">
            <div className="k">Tokens</div>
            <div className="v">{de(ki.tokens_gesamt / 1000, 1)}k</div>
            <div className="s">{ki.modell}, Antworten zwischengespeichert</div>
          </div>
        </div>
      )}

      <div className="note">
        <b>Löschen darf nur ein Mensch.</b> Eine automatische Entscheidung
        kennzeichnet einen Wert, sie nimmt ihn nie aus dem Bestand. Dafür
        braucht es eine Zeile mit Name, Datum und Begründung.{" "}
        <b>Wann ein Mensch drankommt.</b> Nur in vier Fällen: Regel und KI
        widersprechen sich; das Modell bleibt auch nach der Eskalation unsicher;
        ein Eingriff träfe das Ranking oder mehr als eine Megatonne; das Modell
        braucht Belege, die es nicht hat, und ist sich nicht sicher. Der bloße
        Wunsch des Modells nach einem Menschen genügt nicht — in der ersten
        Fassung setzte es ihn fast immer und schickte {de(VORHER.mensch)} von{" "}
        {de(VORHER.flags)} Fällen an Menschen.
      </div>

      <h2>Alle Fälle</h2>
      <Review flags={flags} />

      <div className="note">
        <b>So entscheidet ein Mensch.</b> Namen eintragen, Fall aufklappen,
        Belege lesen, einen Satz Begründung schreiben und einen der drei Knöpfe
        drücken: <i>Fehler bestätigen</i>, <i>Korrektur nötig</i> oder{" "}
        <i>Wert ist ok</i>. Die Entscheidung wird sofort gespeichert und lässt
        sich zurücknehmen. <code>scripts/entscheidungen_holen.sh</code> holt
        sie nach <code>data/review/entscheidungen.csv</code>; beim nächsten Lauf
        von <code>scripts/10_pruefung.py</code> hat sie Vorrang vor Regel und KI
        und fließt mit Namen in den Datensatz.
      </div>

      <footer>
        <span>Regeln: pipeline/quality.py</span>
        <span>KI: pipeline/ai_review.py</span>
        <span>Downloads: flags_gepruft.csv</span>
      </footer>
    </main>
  );
}
