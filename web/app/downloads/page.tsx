import { stat } from "node:fs/promises";
import path from "node:path";
import { getDataset } from "@/lib/data";

type Item = {
  file: string;
  title: string;
  format: string;
  what: string;
};

const GROUPS: { title: string; hint: string; items: Item[] }[] = [
  {
    title: "Dokumente",
    hint: "zum Lesen",
    items: [
      {
        file: "datenkatalog.pdf",
        title: "Datenkatalog",
        format: "PDF",
        what: "Alle Quellen mit Adresse, Schlüsselpflicht und Lizenz, dazu alle Kennzahlen nach Datentyp.",
      },
    ],
  },
  {
    title: "Datensatz",
    hint: "zum Weiterrechnen",
    items: [
      {
        file: "dataset_long.csv",
        title: "Gesammelter Datensatz",
        format: "CSV",
        what: "Eine Zeile je Firma, Jahr und Kennzahl. Jede Zeile nennt Quelle, Abrufadresse, Zugang, Lizenz und Abrufdatum.",
      },
      {
        file: "belastbarkeit.csv",
        title: "Belastbarkeit je Firma",
        format: "CSV",
        what: "Je Firma und Bereich E, S, G: Punkte, vorhandene Familien, Anker und Stufe (belastbar bis keine). Regeln in pipeline/reliability.py.",
      },
      {
        file: "dataset_long.parquet",
        title: "Gesammelter Datensatz",
        format: "Parquet",
        what: "Derselbe Inhalt, spaltenweise komprimiert. Direkt lesbar mit pandas, polars oder DuckDB.",
      },
    ],
  },
  {
    title: "Register",
    hint: "zum Nachschlagen",
    items: [
      {
        file: "sources.json",
        title: "Quellenregister",
        format: "JSON",
        what: "Je Quelle Name, Adresse, Zugang, Lizenz, Abdeckung, Messart und bekannte Grenze.",
      },
      {
        file: "metrics.json",
        title: "Kennzahlenregister",
        format: "JSON",
        what: "Je Kennzahl Bezeichnung, Einheit, Richtung, Achse und Quelle.",
      },
      {
        file: "companies.json",
        title: "Firmenansicht",
        format: "JSON",
        what: "Je Firma der jüngste vollständige Wert jeder Kennzahl, samt Firmen ohne Daten. Das liest diese Oberfläche.",
      },
    ],
  },
];

async function size(file: string): Promise<string> {
  try {
    const s = await stat(path.join(process.cwd(), "public", "downloads", file));
    const kb = s.size / 1024;
    return kb > 1024
      ? `${(kb / 1024).toLocaleString("de-DE", { maximumFractionDigits: 1 })} MB`
      : `${Math.round(kb).toLocaleString("de-DE")} KB`;
  } catch {
    return "fehlt";
  }
}

export default async function Page() {
  const data = await getDataset();
  const sized = await Promise.all(
    GROUPS.map(async (g) => ({
      ...g,
      items: await Promise.all(
        g.items.map(async (i) => ({ ...i, size: await size(i.file) })),
      ),
    })),
  );

  return (
    <main>
      <p className="eyebrow">Downloads</p>
      <h1>Datensatz und Katalog herunterladen</h1>
      <p className="lede">
        Alles, was diese Oberfläche zeigt, liegt hier auch als Datei. Die
        Quellenangabe reist dabei mit: Im Langformat steht sie an jeder
        einzelnen Zeile, nicht nur im Kopf der Datei.
      </p>

      {sized.map((g) => (
        <section key={g.title} className="axisblock">
          <div className="axishead">
            <span className="t">{g.title}</span>
            <span className="h">{g.hint}</span>
          </div>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Datei</th>
                  <th>Inhalt</th>
                  <th>Format</th>
                  <th className="num">Größe</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {g.items.map((i) => (
                  <tr key={i.file}>
                    <td>
                      {i.title}
                      <br />
                      <code className="dim">{i.file}</code>
                    </td>
                    <td className="dim">{i.what}</td>
                    <td>
                      <span className="chip a">{i.format}</span>
                    </td>
                    <td className="num">{i.size}</td>
                    <td className="num">
                      {i.size === "fehlt" ? (
                        <span className="dim">–</span>
                      ) : (
                        <a href={`/downloads/${i.file}`} download>
                          herunterladen ↓
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <div className="note">
        <b>Lizenzen gelten pro Quelle, nicht pro Datei.</b> Behördendaten der
        USA sind gemeinfrei, die WBA-Bewertungen stehen unter CC BY 4.0 und
        verlangen Namensnennung, SBTi erlaubt die Nutzung mit Quellenangabe. Wer
        den Datensatz weitergibt, sollte die Spalte <code>source_license</code>{" "}
        mitnehmen. Der kommerzielle ESG-Vergleichsdatensatz mit unklarer Lizenz
        ist nur zum Gegenhalten enthalten und sollte bei einer Weitergabe
        entfernt werden.
      </div>

      <footer>
        <span>Stand {data.generatedAt}</span>
        <span>{Object.keys(data.sources).length} Quellen</span>
      </footer>
    </main>
  );
}
