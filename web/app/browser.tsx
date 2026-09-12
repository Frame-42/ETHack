"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AXES, fmt } from "@/lib/format";

export type Row = {
  ticker: string;
  company: string;
  sector: string;
  n: number;
  sources: number;
  assessed: boolean;
  logo: boolean;
  /** jüngster vollständiger Wert je Kennzahl */
  values: Record<string, number | null>;
};

export type MetricOption = {
  id: string;
  label: string;
  unit: string;
  axis: string;
  direction: number;
};

type Col = {
  key: string;
  label: string;
  num?: boolean;
  get: (r: Row) => string | number | null;
};

const BASE: Col[] = [
  { key: "ticker", label: "Kürzel", get: (r) => r.ticker },
  { key: "company", label: "Firma", get: (r) => r.company },
  { key: "sector", label: "Branche", get: (r) => r.sector },
  { key: "n", label: "Werte", num: true, get: (r) => r.n },
  { key: "sources", label: "Quellen", num: true, get: (r) => r.sources },
  { key: "scope1", label: "Scope 1", num: true, get: (r) => r.values.scope1_t ?? null },
  { key: "tri", label: "TRI", num: true, get: (r) => r.values.tri_releases_lbs ?? null },
  { key: "dafw", label: "Unfälle", num: true, get: (r) => r.values.osha_dafw_cases ?? null },
  { key: "sbti", label: "SBTi", num: true, get: (r) => r.values.sbti_validated ?? null },
];

function Logo({ row }: { row: Row }) {
  if (row.logo) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        className="logo"
        src={`/logos/${row.ticker}.png`}
        alt=""
        width={18}
        height={18}
        loading="lazy"
      />
    );
  }
  return (
    <span className="logo logo-empty" aria-hidden="true">
      {row.company.charAt(0)}
    </span>
  );
}

export default function Browser({
  rows,
  sectors,
  metrics,
}: {
  rows: Row[];
  sectors: string[];
  metrics: MetricOption[];
}) {
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("");
  const [extra, setExtra] = useState("whd_backwages_usd");
  const [sortKey, setSortKey] = useState("n");
  const [desc, setDesc] = useState(true);

  const extraDef = metrics.find((m) => m.id === extra);
  const cols: Col[] = useMemo(() => {
    if (!extraDef) return BASE;
    return [
      ...BASE,
      {
        key: `m:${extraDef.id}`,
        label: extraDef.label,
        num: true,
        get: (r) => r.values[extraDef.id] ?? null,
      },
    ];
  }, [extraDef]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const col = cols.find((c) => c.key === sortKey) ?? cols[3];
    const out = rows.filter(
      (r) =>
        (!sector || r.sector === sector) &&
        (!needle ||
          r.company.toLowerCase().includes(needle) ||
          r.ticker.toLowerCase().includes(needle)),
    );
    return out.sort((a, b) => {
      const av = col.get(a);
      const bv = col.get(b);
      // Fehlende Werte stehen immer unten, egal in welche Richtung sortiert wird.
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      const cmp =
        typeof av === "string" || typeof bv === "string"
          ? String(av).localeCompare(String(bv), "de")
          : (av as number) - (bv as number);
      return desc ? -cmp : cmp;
    });
  }, [rows, q, sector, sortKey, desc, cols]);

  function sortBy(key: string, num?: boolean) {
    if (key === sortKey) {
      setDesc(!desc);
    } else {
      setSortKey(key);
      // Zahlen zuerst absteigend, Texte zuerst alphabetisch.
      setDesc(Boolean(num));
    }
  }

  function chooseExtra(id: string) {
    setExtra(id);
    setSortKey(`m:${id}`);
    const def = metrics.find((m) => m.id === id);
    // "Kleiner ist besser" zeigt zuerst die besten, sonst die höchsten Werte.
    setDesc(def?.direction !== -1);
  }

  const byAxis = Object.keys(AXES)
    .map((axis) => ({ axis, items: metrics.filter((m) => m.axis === axis) }))
    .filter((g) => g.items.length);

  return (
    <>
      <div className="filters">
        <input
          type="search"
          placeholder="Firma oder Kürzel suchen …"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Firma suchen"
        />
        <select
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          aria-label="Branche filtern"
        >
          <option value="">alle Branchen</option>
          {sectors.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label className="pick">
          <span>Kennzahl-Spalte</span>
          <select
            value={extra}
            onChange={(e) => chooseExtra(e.target.value)}
            aria-label="Zusätzliche Kennzahl als Spalte"
          >
            {byAxis.map((g) => (
              <optgroup key={g.axis} label={AXES[g.axis].label}>
                {g.items.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <span className="count">{shown.length} Firmen</span>
      </div>

      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              {cols.map((c) => {
                const active = c.key === sortKey;
                return (
                  <th
                    key={c.key}
                    className={c.num ? "num" : undefined}
                    aria-sort={active ? (desc ? "descending" : "ascending") : "none"}
                  >
                    <button
                      type="button"
                      className={active ? "sort on" : "sort"}
                      onClick={() => sortBy(c.key, c.num)}
                      title="Klicken zum Sortieren"
                    >
                      {c.label}
                      <span className="arrow">{active ? (desc ? "↓" : "↑") : "↕"}</span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.ticker}>
                <td className="tick">
                  <Link href={`/firma/${r.ticker}`} className="tickcell">
                    <Logo row={r} />
                    {r.ticker}
                  </Link>
                </td>
                <td>
                  <Link href={`/firma/${r.ticker}`}>{r.company}</Link>
                </td>
                <td className="dim">{r.sector}</td>
                <td className="num">
                  {r.n === 0 ? (
                    <span className="chip">keine Daten</span>
                  ) : !r.assessed ? (
                    <span
                      className="chip"
                      title="nur Finanzkennzahlen, keine Nachhaltigkeitswerte"
                    >
                      nur Finanzen · {r.n}
                    </span>
                  ) : (
                    r.n
                  )}
                </td>
                <td className="num">{r.n === 0 ? "–" : r.sources}</td>
                <td className="num">{fmt(r.values.scope1_t ?? null, "t CO2e")}</td>
                <td className="num">{fmt(r.values.tri_releases_lbs ?? null, "lbs")}</td>
                <td className="num">{fmt(r.values.osha_dafw_cases ?? null)}</td>
                <td>
                  {r.values.sbti_validated == null ? (
                    <span className="dim">–</span>
                  ) : r.values.sbti_validated ? (
                    <span className="chip good">geprüft</span>
                  ) : (
                    <span className="chip">kein Ziel</span>
                  )}
                </td>
                {extraDef && (
                  <td className="num">
                    {fmt(r.values[extraDef.id] ?? null, extraDef.unit)}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {shown.length === 0 && (
        <div className="note">
          Kein Treffer. Die Liste enthält alle 503 Indexmitglieder, auch die
          ohne jeden Wert.
        </div>
      )}
    </>
  );
}
