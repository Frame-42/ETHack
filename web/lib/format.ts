// Reine Formatierungshilfen ohne Dateizugriff -- nutzbar im Server und im Browser.

/** Achsen des Modells, in der Reihenfolge, in der sie gezeigt werden. */
export const AXES: Record<string, { label: string; hint: string }> = {
  A: { label: "Kernnote", hint: "physisch gemessene Ergebnisse" },
  S: { label: "Sozial", hint: "Arbeitssicherheit und Lohnverstöße" },
  G: { label: "Governance", hint: "dokumentierte Regeltreue" },
  B: { label: "Glaubwürdigkeit", hint: "getrennt von der Kernnote gerechnet" },
  ergebnis: { label: "Ergebnis", hint: "Rangband über alle Methodenkombinationen" },
  vergleich: { label: "Vergleichsmaßstab", hint: "fremde Note, nur zum Gegenhalten" },
  meta: { label: "Bezugsgrößen", hint: "Nenner, Finanzen und Gütewerte, keine Bewertung" },
};

/** Zahl mit deutscher Tausendertrennung, sinnvoll gerundet. */
export function fmt(v: number | null | undefined, unit?: string): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const abs = Math.abs(v);
  if (unit === "ja/nein") return v ? "ja" : "nein";
  if (unit === "Jahr") return String(Math.round(v));
  if (unit === "%/Jahr") return (v * 100).toFixed(1).replace(".", ",") + " %";
  if (unit === "USD" && abs >= 1e6) {
    const [n, s] = abs >= 1e9 ? [v / 1e9, " Mrd."] : [v / 1e6, " Mio."];
    return n.toLocaleString("de-DE", { maximumFractionDigits: 1 }) + s;
  }
  let digits = 0;
  if (abs < 1) digits = 3;
  else if (abs < 10) digits = 2;
  else if (abs < 1000) digits = 1;
  return v.toLocaleString("de-DE", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
