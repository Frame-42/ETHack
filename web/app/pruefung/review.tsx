"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

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

type Decision = { flag_id: string; entscheidung: string; person: string; datum: string; begruendung: string };

const ROUTE_LABEL: Record<string, string> = { mensch: "an Menschen", automatisch: "automatisch", eskalation: "eskaliert" };

const ACTIONS: { value: string; label: string; hint: string; cls: string }[] = [
  { value: "fehler", label: "Fehler bestätigen", hint: "Wert wird nicht verrechnet", cls: "bad" },
  { value: "korrigieren", label: "Korrektur nötig", hint: "Wert ist falsch, Quelle oder Zuordnung muss angepasst werden", cls: "fix" },
  { value: "ok", label: "Wert ist ok", hint: "Regel hat Fehlalarm ausgelöst, Wert bleibt", cls: "okay" },
];
const DECISION_LABEL: Record<string, string> = { fehler: "Fehler bestätigt", korrigieren: "Korrektur nötig", ok: "Wert ok" };

function readName(): string {
  try { return localStorage.getItem("pruefung.person") ?? ""; } catch { return ""; }
}

export default function Review({ flags }: { flags: ReviewFlag[] }) {
  const [route, setRoute] = useState("mensch");
  const [state, setState] = useState("offen");
  const [rule, setRule] = useState("");
  const [verdict, setVerdict] = useState("");
  const [q, setQ] = useState("");
  const [person, setPerson] = useState("");
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    setPerson(readName());
    fetch("/api/entscheidungen")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((list: Decision[]) => {
        setDecisions(Object.fromEntries(list.map((d) => [d.flag_id, d])));
        setOnline(true);
      })
      .catch(() => setOnline(false));
  }, []);

  const rememberName = (v: string) => {
    setPerson(v);
    try { localStorage.setItem("pruefung.person", v); } catch {}
  };

  const rules = useMemo(() => [...new Set(flags.map((f) => f.rule))].sort(), [flags]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of flags) c[f.route ?? "–"] = (c[f.route ?? "–"] ?? 0) + 1;
    return c;
  }, [flags]);
  const decided = (f: ReviewFlag) => Boolean(decisions[f.flag_id]);
  const open = flags.filter((f) => f.route === "mensch" && !decided(f)).length;
  const done = Object.keys(decisions).length;

  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    return flags
      .filter(
        (f) =>
          (!route || f.route === route) &&
          (!state || (state === "offen" ? !decisions[f.flag_id] : Boolean(decisions[f.flag_id]))) &&
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
  }, [flags, route, state, rule, verdict, q, decisions]);

  if (flags.length === 0) {
    return <div className="note">Noch keine geprüften Fälle. <code>python scripts/10_pruefung.py --ai</code> ausführen.</div>;
  }

  return (
    <>
      <div className="reviewer">
        <label>
          <span>Dein Name</span>
          <input value={person} onChange={(e) => rememberName(e.target.value)} placeholder="für die Nachvollziehbarkeit" maxLength={80} />
        </label>
        <span className="progress">
          <b>{open}</b> offen an Menschen · <b>{done}</b> entschieden
        </span>
        {online === false && <span className="chip warn">Speichern nicht erreichbar</span>}
        <a className="btn ghost" href="/api/entscheidungen?format=csv">Entscheidungen als CSV ↓</a>
      </div>

      <div className="filters static">
        <div className="switch" role="group" aria-label="Weg">
          {["mensch", "automatisch", ""].map((r) => (
            <button key={r || "alle"} type="button" className={route === r ? "on" : undefined} onClick={() => setRoute(r)} aria-pressed={route === r}>
              {r ? `${ROUTE_LABEL[r]} (${counts[r] ?? 0})` : `alle (${flags.length})`}
            </button>
          ))}
        </div>
        <div className="switch" role="group" aria-label="Stand">
          {[["offen", "offen"], ["entschieden", "entschieden"], ["", "beides"]].map(([v, l]) => (
            <button key={v || "beides"} type="button" className={state === v ? "on" : undefined} onClick={() => setState(v)} aria-pressed={state === v}>
              {l}
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
          <Case
            key={f.flag_id}
            f={f}
            person={person}
            decision={decisions[f.flag_id]}
            onDecided={(d) =>
              setDecisions((cur) => {
                const next = { ...cur };
                if (d) next[f.flag_id] = d;
                else delete next[f.flag_id];
                return next;
              })
            }
          />
        ))}
      </div>
    </>
  );
}

function Case({
  f,
  person,
  decision,
  onDecided,
}: {
  f: ReviewFlag;
  person: string;
  decision?: Decision;
  onDecided: (d: Decision | null) => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function decide(entscheidung: string) {
    if (!person.trim()) { setErr("Bitte oben deinen Namen eintragen."); return; }
    setBusy(true); setErr("");
    try {
      const r = await fetch("/api/entscheidungen", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ flag_id: f.flag_id, entscheidung, person, begruendung: reason }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? `HTTP ${r.status}`);
      onDecided(data as Decision);
    } catch (e) {
      setErr(`Nicht gespeichert: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    setBusy(true); setErr("");
    try {
      const r = await fetch(`/api/entscheidungen?flag_id=${encodeURIComponent(f.flag_id)}`, { method: "DELETE" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      onDecided(null);
    } catch (e) {
      setErr(`Nicht zurückgenommen: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className={`case ${f.severity}${decision ? " decided" : ""}`}>
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
        {decision && <span className="chip good">✓ {DECISION_LABEL[decision.entscheidung] ?? decision.entscheidung}</span>}
      </summary>
      <div className="cbody">
        <p><span className="lbl">Regel</span>{f.rule} — {f.message}</p>
        {f.ai_explanation && (
          <p><span className="lbl">KI</span>{f.ai_cause} · Vorschlag: {f.ai_action} · {f.ai_model}<br />{f.ai_explanation}</p>
        )}

        {decision ? (
          <div className="decision">
            <p>
              <span className="lbl">Mensch</span>
              <b>{DECISION_LABEL[decision.entscheidung] ?? decision.entscheidung}</b> · {decision.person} · {decision.datum}
              {decision.begruendung && <><br />{decision.begruendung}</>}
            </p>
            <button type="button" className="btn ghost" onClick={undo} disabled={busy}>Entscheidung zurücknehmen</button>
          </div>
        ) : (
          <div className="decide">
            <span className="lbl">Mensch</span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Ein Satz Begründung, z. B. Beleg aus 8-K oder Anlagenliste"
              rows={2}
              maxLength={600}
            />
            <div className="actions">
              {ACTIONS.map((a) => (
                <button key={a.value} type="button" className={`btn ${a.cls}`} title={a.hint} onClick={() => decide(a.value)} disabled={busy}>
                  {a.label}
                </button>
              ))}
            </div>
          </div>
        )}
        {err && <p className="err">{err}</p>}

        <p className="lbl">Belege</p>
        <pre className="evidence">{JSON.stringify(f.evidence, null, 2)}</pre>
      </div>
    </details>
  );
}
