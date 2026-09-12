"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { fmt } from "@/lib/format";

export type CompareRow = {
  ticker: string;
  company: string;
  sector: string;
  logo: boolean;
  values: Record<string, number | null>;
};

export type CompareMetric = {
  id: string;
  label: string;
  unit: string;
  axis: string;
  direction: number;
  count: number;
  source: string;
};

const START = ["scope1_t", "tri_releases_lbs", "sbti_validated"];

export default function Compare({
  rows,
  metrics,
}: {
  rows: CompareRow[];
  metrics: CompareMetric[];
}) {
  const [selected, setSelected] = useState<string[]>(
    START.filter((id) => metrics.some((m) => m.id === id)),
  );
  const [normalized, setNormalized] = useState(false);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("");
  const [onlyComplete, setOnlyComplete] = useState(false);
  const [sortKey, setSortKey] = useState<string>(selected[0] ?? "company");
  const [desc, setDesc] = useState(true);

  const chosen = selected
    .map((id) => metrics.find((m) => m.id === id))
    .filter((m): m is CompareMetric => Boolean(m));

  // Spannweite je Kennzahl über alle Firmen, für die Normalisierung.
  const ranges = useMemo(() => {
    const out: Record<string, [number, number]> = {};
    for (const m of chosen) {
      let lo = Infinity;
      let hi = -Infinity;
      for (const r of rows) {
        const v = r.values[m.id];
        if (v === null || v === undefined || !Number.isFinite(v)) continue;
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
      out[m.id] = [lo, hi];
    }
    return out;
  }, [rows, chosen]);

  /** 1 = bester Wert der Kennzahl, 0 = schlechtester. Neutrale Kennzahlen: höchster Wert = 1. */
  function norm(m: CompareMetric, v: number | null | undefined): number | null {
    if (v === null || v === undefined || !Number.isFinite(v)) return null;
    const [lo, hi] = ranges[m.id] ?? [0, 0];
    if (!(hi > lo)) return 1;
    const x = (v - lo) / (hi - lo);
    return m.direction === -1 ? 1 - x : x;
  }

  function cell(r: CompareRow, m: CompareMetric): number | null {
    const v = r.values[m.id];
    return normalized ? norm(m, v) : (v ?? null);
  }

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = rows.filter(
      (r) =>
        (!needle ||
          r.company.toLowerCase().includes(needle) ||
          r.ticker.toLowerCase().includes(needle)) &&
        (!onlyComplete || chosen.every((m) => r.values[m.id] != null)),
    );
    const metric = chosen.find((m) => m.id === sortKey);
    const get = (r: CompareRow): string | number | null =>
      metric ? cell(r, metric) : sortKey === "sector" ? r.sector : sortKey === "ticker" ? r.ticker : r.company;
    return out.sort((a, b) => {
      const av = get(a);
      const bv = get(b);
      // Fehlende Werte immer ans Ende, unabhängig von der Richtung.
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      const cmp =
        typeof av === "string" || typeof bv === "string"
          ? String(av).localeCompare(String(bv), "de")
          : (av as number) - (bv as number);
      return desc ? -cmp : cmp;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, q, onlyComplete, chosen, sortKey, desc, normalized, ranges]);

  function toggle(id: string) {
    setSelected((cur) => {
      if (cur.includes(id)) {
        const next = cur.filter((x) => x !== id);
        if (sortKey === id) setSortKey(next[0] ?? "company");
        return next;
      }
      if (cur.length === 0) {
        setSortKey(id);
        setDesc(true);
      }
      return [...cur, id];
    });
  }

  function sortBy(key: string, numeric: boolean) {
    if (key === sortKey) setDesc(!desc);
    else {
      setSortKey(key);
      setDesc(numeric);
    }
  }

  const needleM = filter.trim().toLowerCase();
  const options = metrics.filter((m) => !needleM || m.label.toLowerCase().includes(needleM));

  const head = (key: string, label: string, numeric: boolean, title?: string) => {
    const active = key === sortKey;
    return (
      <th
        key={key}
        className={numeric ? "num" : undefined}
        aria-sort={active ? (desc ? "descending" : "ascending") : "none"}
        title={title}
      >
        <button type="button" className={active ? "sort on" : "sort"} onClick={() => sortBy(key, numeric)}>
          {label}
          <span className="arrow">{active ? (desc ? "↓" : "↑") : "↕"}</span>
        </button>
      </th>
    );
  };

  return (
    <div className="compare">
      <aside className="picker">
        <div className="pickhead">
          <span className="t">Kennzahlen</span>
          <span className="h">
            {selected.length} gewählt
            {selected.length > 0 && (
              <button type="button" className="linkbtn" onClick={() => setSelected([])}>
                leeren
              </button>
            )}
          </span>
        </div>
        <input
          type="search"
          placeholder="Kennzahl suchen …"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Kennzahl suchen"
        />
        <ul>
          {options.map((m) => (
            <li key={m.id}>
              <label className={selected.includes(m.id) ? "on" : undefined} title={`${m.unit} · ${m.source}`}>
                <input type="checkbox" checked={selected.includes(m.id)} onChange={() => toggle(m.id)} />
                <span className="lbl">{m.label}</span>
                <span className="cnt">({m.count})</span>
              </label>
            </li>
          ))}
        </ul>
      </aside>

      <section className="grid">
        <div className="filters">
          <input
            type="search"
            placeholder="Firma oder Kürzel suchen …"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Firma suchen"
          />
          <div className="switch" role="group" aria-label="Darstellung der Werte">
            <button type="button" className={!normalized ? "on" : undefined} onClick={() => setNormalized(false)} aria-pressed={!normalized}>
              absolut
            </button>
            <button type="button" className={normalized ? "on" : undefined} onClick={() => setNormalized(true)} aria-pressed={normalized}>
              normalisiert 0–1
            </button>
          </div>
          <label className="pick">
            <input type="checkbox" checked={onlyComplete} onChange={(e) => setOnlyComplete(e.target.checked)} />
            <span>nur Firmen mit allen gewählten Werten</span>
          </label>
          <span className="count">{shown.length} Firmen</span>
        </div>

        {chosen.length === 0 ? (
          <div className="note">Links mindestens eine Kennzahl auswählen.</div>
        ) : (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  {head("ticker", "Kürzel", false)}
                  {head("company", "Firma", false)}
                  {head("sector", "Branche", false)}
                  {chosen.map((m) =>
                    head(
                      m.id,
                      normalized ? m.label : `${m.label} (${m.unit})`,
                      true,
                      `${m.direction === -1 ? "kleiner ist besser" : m.direction === 1 ? "größer ist besser" : "neutral: höchster Wert = 1"} · Quelle: ${m.source}`,
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.ticker}>
                    <td className="tick">
                      <Link href={`/firma/${r.ticker}`} className="tickcell">
                        {r.logo ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img className="logo" src={`/logos/${r.ticker}.png`} alt="" width={18} height={18} loading="lazy" />
                        ) : (
                          <span className="logo logo-empty" aria-hidden="true">{r.company.charAt(0)}</span>
                        )}
                        {r.ticker}
                      </Link>
                    </td>
                    <td>
                      <Link href={`/firma/${r.ticker}`}>{r.company}</Link>
                    </td>
                    <td className="dim">{r.sector}</td>
                    {chosen.map((m) => {
                      const v = cell(r, m);
                      if (v === null) return <td key={m.id} className="num dim">–</td>;
                      if (!normalized) return <td key={m.id} className="num">{fmt(v, m.unit)}</td>;
                      return (
                        <td key={m.id} className="num">
                          <span className="bar" aria-hidden="true">
                            <span style={{ width: `${Math.round(v * 100)}%` }} />
                          </span>
                          {v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {normalized && (
          <div className="note">
            <b>Normalisiert heißt: bezogen auf diese Spalte.</b> 1 ist der beste
            Wert aller Firmen in dieser Kennzahl, 0 der schlechteste — bei
            „kleiner ist besser“ also umgedreht. Die Skala ist linear, ein
            einzelner Ausreißer drückt alle anderen Werte nahe an ein Ende.
            Neutrale Größen wie Umsatz haben keine Richtung; dort ist der
            höchste Wert 1.
          </div>
        )}
      </section>
    </div>
  );
}
