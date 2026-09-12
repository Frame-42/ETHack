"""KI-Prüfung auffälliger Werte -- als Gutachter mit Belegen, nicht als Quelle.

Die Regelprüfung (``pipeline/quality.py``) findet Kandidaten. Dieses Modul legt
jeden Kandidaten einem Sprachmodell vor, zusammen mit einem Belegpaket:
der Wert selbst, seine Zeitreihe, Branchenvergleich, Rohdaten-Auszüge und die
bekannten Eigenheiten der Quelle. Das Modell soll *nicht* aus eigenem Wissen
Firmenzahlen liefern, sondern entscheiden, welche Erklärung die Belege am
besten stützen, und sagen, wann es das nicht kann.

Rückgabe je Kandidat, erzwungen über ein JSON-Schema:

``verdict``        fehler | plausibel | unklar
``cause``          Ursachenkategorie aus einer festen Liste
``explanation``    zwei bis drei Sätze, nur mit Bezug auf die Belege
``action``         unterdruecken | kennzeichnen | korrigieren | behalten
``confidence``     0 bis 1
``needs_human``    wahr, wenn die Belege nicht reichen oder viel davon abhängt

Menschliche Prüfung wird nicht dem Modell überlassen: Eine Regel in
``route()`` schickt Fälle unabhängig vom Modellurteil zur Person, wenn sie
viel Gewicht haben (große Emissionsmengen, Ranking-relevant) oder das Modell
unsicher ist. So bleibt die teure Aufmerksamkeit dort, wo sie zählt.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .config import OUT, _load_env  # noqa: F401  (lädt .env)

API = "https://api.openai.com/v1/responses"
MODEL = os.environ.get("OPENAI_REVIEW_MODEL", "gpt-5.4-mini")
# Schwellen der Weiterleitung. Startwerte, keine Kalibrierung -- sie werden
# belastbar, sobald genug menschliche Entscheidungen als Referenz vorliegen.
UNSICHER = 0.6   # darunter: an das staerkere Modell, danach an einen Menschen
SICHER = 0.85    # darueber: Wunsch nach einem Menschen zaehlt nicht mehr
ESCALATION_MODEL = os.environ.get("OPENAI_ESCALATION_MODEL", "gpt-5.5")
CACHE = OUT / "ai_review_cache"

CAUSES = [
    "null_statt_fehlend",
    "zuordnung_falsch",
    "doppelzaehlung",
    "definition_oder_einheit",
    "programm_misst_groesse_nicht",
    "konzernumbau_zeitlich",
    "meldefehler_quelle",
    "branchenstruktur_real",
    "echter_extremwert",
    "sonstiges",
]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "cause", "explanation", "action", "confidence", "needs_human"],
    "properties": {
        "verdict": {"type": "string", "enum": ["fehler", "plausibel", "unklar"]},
        "cause": {"type": "string", "enum": CAUSES},
        "explanation": {"type": "string"},
        "action": {"type": "string", "enum": ["unterdruecken", "kennzeichnen", "korrigieren", "behalten"]},
        "confidence": {"type": "number"},
        "needs_human": {"type": "boolean"},
    },
}

SYSTEM = """Du prüfst auffällige Werte in einem Nachhaltigkeitsdatensatz über US-Börsenfirmen.
Du bekommst je Fall ein Belegpaket. Regeln:
- Stütze dich ausschließlich auf die Belege im Paket. Ergänze keine Firmenzahlen aus eigenem Wissen.
- Allgemeines Wissen über Meldeprogramme und Konzernereignisse darfst du nutzen, musst es aber in der
  Erklärung als solches kenntlich machen ("laut allgemeinem Wissen ...").
- Die Frage ist immer: Darf dieser Wert so, wie er dasteht, als Messwert über die Firma verrechnet werden?
- "fehler": Nein. Der Wert ist falsch oder irreführend -- AUCH DANN, wenn die Ursache gut erklärbar ist
  (eine Null, weil ein Programm die Größe nicht misst, ist erklärt, aber als Messwert trotzdem falsch).
- "plausibel": Ja. Der Wert beschreibt die Firma richtig, er ist nur ungewöhnlich (z. B. echte Branchenstruktur).
- "unklar": Die Belege reichen nicht. Das ist eine gute Antwort, wenn es stimmt.
- needs_human=true, wenn eine Person mit Rohdaten- oder Dokumentenzugang das klären muss.
- confidence ist deine Wahrscheinlichkeit, dass verdict stimmt. Sei zurückhaltend.
Antworte auf Deutsch, knapp, sachlich."""


def _key() -> str:
    k = os.environ.get("OPENAI_API_KEY", "")
    if not k:
        raise RuntimeError("OPENAI_API_KEY fehlt in .env")
    return k


def _cache_path(packet: dict, model: str) -> Path:
    h = hashlib.sha256(json.dumps([packet, model, SYSTEM], sort_keys=True).encode()).hexdigest()[:24]
    return CACHE / f"{h}.json"


def review_one(packet: dict, model: str = MODEL, tries: int = 4) -> dict:
    """Ein Fall. Antworten werden zwischengespeichert: gleicher Fall, gleiche Antwort."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(packet, model)
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(packet, ensure_ascii=False, default=str)},
        ],
        "text": {"format": {"type": "json_schema", "name": "pruefung", "schema": SCHEMA, "strict": True}},
    }
    last = None
    for attempt in range(tries):
        try:
            r = requests.post(API, headers={"Authorization": f"Bearer {_key()}"}, json=body, timeout=180)
            if r.status_code == 200:
                data = r.json()
                text = next(
                    c["text"]
                    for item in data.get("output", [])
                    if item.get("type") == "message"
                    for c in item.get("content", [])
                    if c.get("type") == "output_text"
                )
                out = json.loads(text)
                out["model"] = model
                out["usage"] = data.get("usage", {})
                cp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
                return out
            last = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code in (400, 401, 403):
                break
        except (requests.RequestException, StopIteration, json.JSONDecodeError) as exc:
            last = str(exc)
        time.sleep(2 * (attempt + 1))
    return {"verdict": "unklar", "cause": "sonstiges", "explanation": f"Prüfung fehlgeschlagen: {last}",
            "action": "kennzeichnen", "confidence": 0.0, "needs_human": True, "model": model, "error": True}


def route(flag: dict, review: dict) -> str:
    """Wer entscheidet: automatisch, Eskalation an ein staerkeres Modell, Mensch.

    Menschen sind teuer, deshalb bekommen sie nur Grenzfaelle. Drei Stufen
    sorgen dafuer, dass wenige uebrig bleiben:

    1. Systematische Fehler werden gar nicht erst weitergereicht, sondern in
       der Pipeline repariert (Null statt fehlend, Programmfilter, Join-
       Kardinalitaet, Nenner, Gueltigkeitszeitraeume). Was hier ankommt, ist
       der Rest, den keine Regel entscheiden kann.
    2. Unsicheres geht erst an das staerkere Modell, nicht an einen Menschen.
    3. Ein Mensch kommt nur dran, wenn eine der vier Bedingungen unten gilt.

    Der Wunsch des Modells nach einem Menschen (``needs_human``) allein
    genuegt nicht mehr: Das Modell hat ihn in der ersten Fassung fast immer
    gesetzt und damit 246 von 382 Faellen an Menschen geschickt. Er zaehlt
    jetzt nur zusammen mit hoher Wirkung oder geringer Sicherheit.
    """
    if review.get("error"):
        return "mensch"
    verdict, conf = review["verdict"], float(review.get("confidence") or 0)
    ist_eskalation = review.get("model") == ESCALATION_MODEL

    # (1) Unsicher: erst das staerkere Modell, dann erst ein Mensch.
    if verdict == "unklar" or conf < UNSICHER:
        return "mensch" if ist_eskalation else "eskalation"

    hohe_wirkung = bool(flag.get("ranking_relevant")) or float(flag.get("impact_t") or 0) >= 1_000_000
    greift_ein = review["action"] in ("unterdruecken", "korrigieren")
    widerspruch = flag.get("severity") == "fehler" and verdict == "plausibel"

    # (2) Regel und Modell widersprechen sich -- das wertvollste Signal.
    if widerspruch:
        return "mensch"
    # (3) Eingriff mit grosser Wirkung: Rangfolge oder ab einer Megatonne.
    if greift_ein and hohe_wirkung:
        return "mensch"
    # (4) Das Modell verlangt Belege, die es nicht hat, und ist nicht sicher.
    if review.get("needs_human") and conf < SICHER:
        return "mensch"
    return "automatisch"


def review_many(items: list[tuple[dict, dict]], workers: int = 6) -> list[dict]:
    """items = [(flag, packet), ...]. Eskaliert unsichere Fälle einmal an das stärkere Modell."""

    def run(item):
        flag, packet = item
        rv = review_one(packet, MODEL)
        path = route(flag, rv)
        if path == "eskalation":
            rv2 = review_one(packet, ESCALATION_MODEL)
            rv2["first_pass"] = {k: rv[k] for k in ("verdict", "cause", "confidence")}
            rv, path = rv2, route(flag, rv2)
        return {**flag, **{f"ai_{k}": v for k, v in rv.items() if k != "usage"},
                "route": path, "tokens": (rv.get("usage") or {}).get("total_tokens")}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, items))
