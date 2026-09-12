import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

// Menschliche Entscheidungen zu geprüften Fällen. Gespeichert im selben Format,
// das scripts/10_pruefung.py liest: flag_id,entscheidung,person,datum,begruendung.
// Im Container liegt die Datei in einem Volume (DECISIONS_FILE), lokal im Repo.
export const dynamic = "force-dynamic";

const FILE =
  process.env.DECISIONS_FILE ??
  path.join(process.cwd(), "..", "data", "review", "entscheidungen.csv");
const HEADER = "flag_id,entscheidung,person,datum,begruendung";
const CHOICES = new Set(["fehler", "ok", "korrigieren"]);

export type Decision = {
  flag_id: string;
  entscheidung: string;
  person: string;
  datum: string;
  begruendung: string;
};

function parseLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (q) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') q = false;
      else cur += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") { out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}

const cell = (v: string) => (/[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);

async function load(): Promise<Map<string, Decision>> {
  const map = new Map<string, Decision>();
  let text = "";
  try { text = await readFile(FILE, "utf8"); } catch { return map; }
  for (const line of text.split(/\r?\n/).slice(1)) {
    if (!line.trim()) continue;
    const [flag_id, entscheidung, person = "", datum = "", begruendung = ""] = parseLine(line);
    if (flag_id) map.set(flag_id, { flag_id, entscheidung, person, datum, begruendung });
  }
  return map;
}

async function save(map: Map<string, Decision>) {
  await mkdir(path.dirname(FILE), { recursive: true });
  const rows = [...map.values()]
    .sort((a, b) => a.flag_id.localeCompare(b.flag_id))
    .map((d) => [d.flag_id, d.entscheidung, d.person, d.datum, d.begruendung].map(cell).join(","));
  await writeFile(FILE, [HEADER, ...rows].join("\n") + "\n", "utf8");
}

// Einfache Sperre, damit gleichzeitige Klicks sich nicht überschreiben.
let queue: Promise<unknown> = Promise.resolve();
const locked = <T>(fn: () => Promise<T>) => {
  const run = queue.then(fn, fn);
  queue = run.catch(() => undefined);
  return run;
};

export async function GET(req: Request) {
  const map = await load();
  if (new URL(req.url).searchParams.get("format") === "csv") {
    let text = HEADER + "\n";
    try { text = await readFile(FILE, "utf8"); } catch {}
    return new Response(text, {
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": 'attachment; filename="entscheidungen.csv"',
      },
    });
  }
  return Response.json([...map.values()]);
}

export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try { body = await req.json(); } catch { return Response.json({ error: "kein JSON" }, { status: 400 }); }
  const flag_id = String(body.flag_id ?? "");
  const entscheidung = String(body.entscheidung ?? "");
  const person = String(body.person ?? "").trim().slice(0, 80);
  const begruendung = String(body.begruendung ?? "").replace(/\s+/g, " ").trim().slice(0, 600);
  if (!/^Q\d{4,6}$/.test(flag_id)) return Response.json({ error: "flag_id ungültig" }, { status: 400 });
  if (!CHOICES.has(entscheidung)) return Response.json({ error: "Entscheidung ungültig" }, { status: 400 });
  if (!person) return Response.json({ error: "Name fehlt" }, { status: 400 });
  const d: Decision = { flag_id, entscheidung, person, datum: new Date().toISOString().slice(0, 10), begruendung };
  await locked(async () => { const map = await load(); map.set(flag_id, d); await save(map); });
  return Response.json(d);
}

export async function DELETE(req: Request) {
  const flag_id = new URL(req.url).searchParams.get("flag_id") ?? "";
  if (!/^Q\d{4,6}$/.test(flag_id)) return Response.json({ error: "flag_id ungültig" }, { status: 400 });
  await locked(async () => { const map = await load(); map.delete(flag_id); await save(map); });
  return Response.json({ ok: true });
}
