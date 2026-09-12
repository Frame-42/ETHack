import { readFile } from "node:fs/promises";
import path from "node:path";

export type MetricValue = {
  metric: string;
  label: string;
  value: number | null;
  unit: string;
  year: number | null;
  axis: string;
  sourceId: string;
  sourceName: string;
  sourceUrl: string;
  /** Wahr, wenn der Wert aus dem laufenden, noch unvollstaendigen Jahr stammt. */
  partial?: boolean;
};

export type Company = {
  ticker: string;
  company: string;
  sector: string;
  subIndustry: string;
  metrics: MetricValue[];
};

export type Source = {
  name: string;
  url: string;
  access: string;
  license: string;
  coverage: string;
  measurement: string;
  caveat: string;
  retrieved_at: string;
};

export type MetricDef = {
  label: string;
  unit: string;
  direction: number;
  axis: string;
  sourceId: string;
};

export type Dataset = {
  generatedAt: string;
  companies: Company[];
  withoutData: { ticker: string; company: string; sector: string }[];
  sources: Record<string, Source>;
  metrics: Record<string, MetricDef>;
};

let cache: Dataset | null = null;

/** Liest den gesammelten Datensatz. Beim Bauen einmal, danach aus dem Speicher. */
export async function getDataset(): Promise<Dataset> {
  if (cache) return cache;
  const file = path.join(process.cwd(), "public", "data", "companies.json");
  cache = JSON.parse(await readFile(file, "utf8")) as Dataset;
  return cache;
}

/** Achsen des Modells, in der Reihenfolge, in der sie gezeigt werden. */
export const AXES: Record<string, { label: string; hint: string }> = {
  A: { label: "Kernnote", hint: "physisch gemessene Ergebnisse" },
  S: { label: "Sozial", hint: "Arbeitssicherheit" },
  G: { label: "Governance", hint: "dokumentierte Regeltreue" },
  B: { label: "Glaubwürdigkeit", hint: "getrennt von der Kernnote gerechnet" },
  ergebnis: { label: "Ergebnis", hint: "Rangband über alle Methodenkombinationen" },
  vergleich: { label: "Vergleichsmaßstab", hint: "fremde Note, nur zum Gegenhalten" },
  meta: { label: "Bezugsgrößen", hint: "Nenner und Gütewerte, keine Bewertung" },
};

/** Zahl mit deutscher Tausendertrennung, sinnvoll gerundet. */
export function fmt(v: number | null, unit?: string): string {
  if (v === null || !Number.isFinite(v)) return "–";
  const abs = Math.abs(v);
  if (unit === "ja/nein") return v ? "ja" : "nein";
  if (unit === "Jahr") return String(Math.round(v));
  if (unit === "%/Jahr") return (v * 100).toFixed(1).replace(".", ",") + " %";
  let digits = 0;
  if (abs < 1) digits = 3;
  else if (abs < 10) digits = 2;
  else if (abs < 1000) digits = 1;
  return v.toLocaleString("de-DE", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
