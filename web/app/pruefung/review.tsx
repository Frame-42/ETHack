"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

export type ReviewFlag = {
  flag_id: string;
  rule: string;
  severity: "fehler" | "pruefen";
  ticker: string;
  company?: string;
  gics_sector?: string;
  metric: string;
  year: number | null;
  value: number | null;
  message: string;
  impact_t?: number;
  ranking_relevant?: boolean;
  evidence: Record<string, unknown>;
  ai_verdict?: "fehler" | "plausibel" | "unklar";
  ai_cause?: string;
  ai_explanation?: string;
  ai_action?: string;
  ai_confidence?: number;
  ai_model?: string;
  route?: "automatisch" | "mensch" | "eskalation";
  entscheidung?: string;
};

const ROUTE_LABEL: Record<string, string> = { mensch: "an Menschen", automatisch: "automatisch", eskalation: "eskaliert" };

export default function Review({ flags }: { flags: ReviewFlag[] }) {
  const [route, setRoute] = useState("mensch");
  const [rule, setRule] = useState("");
  const [verdict, setVerdict] = useState("");
  const [q, setQ] = useState("");

  const rules = useMemo(() => [...new Set(flags.map((f) => f.rule))].sort(), [flags]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of flags) c[f.route ?? "–"] = (c[f.route ?? "–"] ?? 0) + 1;
    return c;
  }, [flags]);

  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    return flags
      .filter(
        (f) =>
          (!route || f.route === route) &&
          (!rule || f.rule === rule) &&
          (!verdict || f.ai_verdict === verdict) &&
          (!n || f.ticker.toLowerCase().includes(n) || (f.company ?? "").toLowerCase().includes(n) || f.message.toLowerCase().includes(n)),
      )
      .sort(
        (a, b) =>
          Number(b.ranking_relevant ?? false) - Number(a.ranking_relevant ?? false) ||
          (b.impact_t ?? 0) - (a.impact_t ?? 0) ||
          (a.ai_confidence ?? 1) - (b.ai_confidence ?? 1),
      );
  }, [flags, route, rule, verdict, q]);

  if (flags.length === 0) {
    return <div className="note">Noch keine geprüften Fälle. <code>python scripts/10_pruefung.py --ai</code> ausführen.</div>;
  }

  return (
    <>
      <div className="filters static">
        <div className="switch" role="group" aria-label="Weg">
          {["mensch", "automatisch", ""].map((r) => (
            <button key={r || "alle"} type="button" className={route === r ? "on" : undefined} onClick={() => setRoute(r)} aria-pressed={route === r}>
              {r ? `${ROUTE_LABEL[r]} (${counts[r] ?? 0})` : `alle (${flags.length})`}
            </button>
          ))}
        </div>
        <select value={rule} onChange={(e) => setRule(e.target.value)} aria-label="Regel">
          <option value="">alle Regeln</option>
          {rules.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select value={verdict} onChange={(e) => setVerdict(e.target.value)} aria-label="KI-Urteil">
          <option value="">alle KI-Urteile</option>
          <option value="fehler">fehler</option>
          <option value="plausibel">plausibel</option>
          <option value="unklar">unklar</option>
        </select>
        <input type="search" placeholder="Firma, Kürzel oder Text …" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Suchen" />
        <span className="count">{shown.length} Fälle</span>
      </div>

      <div className="cases">
        {shown.map((f) => (
          <details key={f.flag_id} className={`case ${f.severity}`}>
            <summary>
              <span className="mono cid">{f.flag_id}</span>
              <Link href={`/firma/${f.ticker}`} className="mono tk">{f.ticker}</Link>
              <span className="cm">
                <b>{f.metric}</b>
                {f.year ? ` · ${f.year}` : ""}
                {f.value != null ? ` · ${Number(f.value).toLocaleString("de-DE", { maximumFractionDigits: 3 })}` : ""}
              </span>
              <span className={`chip ${f.severity === "fehler" ? "warn" : ""}`}>Regel: {f.severity}</span>
              {f.ai_verdict && (
                <span className={`chip ${f.ai_verdict === "fehler" ? "warn" : f.ai_verdict === "plausibel" ? "good" : ""}`}>
                  KI: {f.ai_verdict} {f.ai_confidence != null ? `· ${Math.round(f.ai_confidence * 100)} %` : ""}
                </span>
              )}
              {f.route && <span className={`chip ${f.route === "mensch" ? "a" : ""}`}>{ROUTE_LABEL[f.route]}</span>}
              {f.ranking_relevant && <span className="chip warn">rankingrelevant</span>}
            </summary>
            <div className="cbody">
              <p><span className="lbl">Regel</span>{f.rule} — {f.message}</p>
              {f.ai_explanation && (
                <p><span className="lbl">KI</span>{f.ai_cause} · Vorschlag: {f.ai_action} · {f.ai_model}<br />{f.ai_explanation}</p>
              )}
              {f.entscheidung && <p><span className="lbl">Mensch</span>{f.entscheidung}</p>}
              <p className="lbl">Belege</p>
              <pre className="evidence">{JSON.stringify(f.evidence, null, 2)}</pre>
            </div>
          </details>
        ))}
      </div>
    </>
  );
}
