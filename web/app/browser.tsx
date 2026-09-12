"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type Row = {
  ticker: string;
  company: string;
  sector: string;
  n: number;
  sources: number;
  rank: number | null;
  band: [number, number] | null;
  co2: number | null;
  dart: number | null;
  sbti: number | null;
};

function fmtNum(v: number | null, digits = 1): string {
  if (v === null || !Number.isFinite(v)) return "–";
  return v.toLocaleString("de-DE", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export default function Browser({
  rows,
  sectors,
}: {
  rows: Row[];
  sectors: string[];
}) {
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("");
  const [sort, setSort] = useState<keyof Row>("n");

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = rows.filter(
      (r) =>
        (!sector || r.sector === sector) &&
        (!needle ||
          r.company.toLowerCase().includes(needle) ||
          r.ticker.toLowerCase().includes(needle)),
    );
    return out.sort((a, b) => {
      const av = a[sort];
      const bv = b[sort];
      if (typeof av === "string" || typeof bv === "string")
        return String(av).localeCompare(String(bv));
      const an = av === null ? -Infinity : (av as number);
      const bn = bv === null ? -Infinity : (bv as number);
      return bn - an;
    });
  }, [rows, q, sector, sort]);

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
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as keyof Row)}
          aria-label="Sortieren nach"
        >
          <option value="n">nach Datenmenge</option>
          <option value="rank">nach Rangband-Median</option>
          <option value="co2">nach CO₂-Intensität</option>
          <option value="dart">nach Unfallrate</option>
          <option value="company">nach Name</option>
        </select>
        <span className="count">{shown.length} Firmen</span>
      </div>

      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Kürzel</th>
              <th>Firma</th>
              <th>Branche</th>
              <th className="num">Werte</th>
              <th className="num">Quellen</th>
              <th className="num">Rangband</th>
              <th className="num">CO₂-Int.</th>
              <th className="num">DART</th>
              <th>SBTi</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.ticker}>
                <td className="tick">
                  <Link href={`/firma/${r.ticker}`}>{r.ticker}</Link>
                </td>
                <td>
                  <Link href={`/firma/${r.ticker}`}>{r.company}</Link>
                </td>
                <td className="dim">{r.sector}</td>
                <td className="num">
                  {r.n === 0 ? <span className="chip">keine Daten</span> : r.n}
                </td>
                <td className="num">{r.n === 0 ? "–" : r.sources}</td>
                <td className="num mono">
                  {r.band
                    ? `${Math.round(r.band[0])}–${Math.round(r.band[1])}`
                    : "–"}
                </td>
                <td className="num">{fmtNum(r.co2, 0)}</td>
                <td className="num">{fmtNum(r.dart, 2)}</td>
                <td>
                  {r.sbti === null ? (
                    <span className="dim">–</span>
                  ) : r.sbti ? (
                    <span className="chip good">geprüft</span>
                  ) : (
                    <span className="chip">kein Ziel</span>
                  )}
                </td>
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
