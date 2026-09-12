import { readFile } from "node:fs/promises";
import path from "node:path";

export { AXES, fmt } from "./format";

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
  /** ok | pruefen -- Werte mit Status "fehler" erscheinen gar nicht */
  qualityStatus?: string;
  qualityRule?: string;
  qualityNote?: string;
};

export type Company = {
  ticker: string;
  company: string;
  sector: string;
  subIndustry: string;
  /** Wahr, wenn mindestens ein Nachhaltigkeitswert vorliegt, nicht nur Finanzdaten. */
  assessed?: boolean;
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
