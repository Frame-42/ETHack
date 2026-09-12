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

## Starten

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

Die Daten liegen als statisches JSON in `public/data/` und werden beim Bauen
gelesen — die App braucht keinen laufenden Dienst. Nach einem neuen
Pipeline-Lauf aktualisiert `python scripts/07_dataset.py` die drei Dateien
`companies.json`, `sources.json` und `metrics.json` automatisch.

## Was die Oberfläche bewusst zeigt

- **Quelle an jedem Wert**, nicht nur an der Tabelle. Eine CO₂-Zahl kann am
  Schornstein gemessen, aus Brennstoffmengen gerechnet oder aus einem
  Geschäftsbericht abgeschrieben sein.
- **Rangbänder statt Platzziffern.** Die Spalte zeigt das Intervall vom 10.
  bis zum 90. Perzentil über 1500 Methodenkombinationen.
- **Teiljahre sind gekennzeichnet.** Werte aus dem laufenden Jahr tragen ein
  Kennzeichen; die Übersicht wählt das jüngste vollständige Jahr.
- **67 Firmen ohne Daten** erscheinen nicht als Null, sondern fehlen
  ausdrücklich.
