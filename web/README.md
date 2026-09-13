# Datenbrowser

Kleine Next.js-Oberfläche zum Durchsehen des gesammelten Datensatzes. Flach
gehalten: rechte Winkel, Haarlinien, keine Schatten, keine Kartenoptik.

## Seiten

| Pfad | Inhalt |
|---|---|
| `/` | Firmenliste mit Suche, Branchenfilter und Sortierung |
| `/firma/<kürzel>` | alle Werte einer Firma, nach Achse gruppiert, **mit Quelle je Zeile** |
| `/kennzahlen` | alle Kennzahlen nach Datentyp, mit Einheit, Richtung und Abdeckung |
| `/quellen` | Quellenregister: Adresse, Zugang, Lizenz, Abdeckung, Grenze |
| `/vergleich` | Firmen nebeneinander (absolut oder 0–1) |
| `/belastbarkeit` | E/S/G-Beweisstärke je Firma + gemeinsames Ranking |
| `/pruefung` | QA-Flags mit Beleg + Menschen-Entscheid |
| `/downloads` | Export-Dateien (CSV/JSON/PDF) |

## Starten

```bash
cd web
npm ci
npm run dev        # http://localhost:3000 (Node 20+, Next 15.5)
```

Die Daten liegen als statisches JSON in `public/data/` und werden beim Bauen
gelesen — die App braucht keinen laufenden Dienst. Nach einem neuen
Pipeline-Lauf aktualisiert `python scripts/07_dataset.py` (plus
`09_belastbarkeit.py` für Belastbarkeit) die Dateien in `public/data/`
(`companies/sources/metrics/belastbarkeit/pruefung/flags*.json|csv`) und
`public/downloads/` automatisch. Frischer Clone: erst 07+09 laufen lassen,
Logos via `08_logos.py`.

## Was die Oberfläche bewusst zeigt

- **Quelle an jedem Wert**, nicht nur an der Tabelle. Eine CO₂-Zahl kann am
  Schornstein gemessen, aus Brennstoffmengen gerechnet oder aus einem
  Geschäftsbericht abgeschrieben sein.
- **Rangbänder statt Platzziffern.** Die Spalte zeigt das Intervall vom 10.
  bis zum 90. Perzentil über 1500 Zufallsdraws (144 diskrete Kombis + LOO/Noise,
  Details: `docs/ONBOARDING.md`).
- **Teiljahre sind gekennzeichnet.** Werte aus dem laufenden Jahr tragen ein
  Kennzeichen; die Übersicht wählt das jüngste vollständige Jahr.
- **Firmen ohne Daten** (36 ohne Wert im Export, 67 ohne Daten in dieser Sicht)
  erscheinen nicht als Null, sondern fehlen ausdrücklich (Zählweise: ONBOARDING §2).
