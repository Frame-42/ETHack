"""Optional model review of quality-rule evidence packets.

Packets contain the observation, its history, sector context, and available source evidence. The model supplies a verdict, cause, explanation, suggested action, confidence, and request for human review. It must not invent company figures. Routing rules separately escalate uncertain or high-impact cases. Model confidence is self-reported and uncalibrated."""
from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .config import OUT, _load_env  # noqa: F401 (loads .env)

API = "https://api.openai.com/v1/responses"
MODEL = os.environ.get("OPENAI_REVIEW_MODEL", "gpt-5.4-mini")
# Routing thresholds are initial assumptions, not calibrated confidence levels.
# Below this: escalate, then request human review.
UNCERTAIN = 0.6   # Above this: an unsupported request for human review alone is insufficient.
CONFIDENT = 0.85    #
ESCALATION_MODEL = os.environ.get("OPENAI_ESCALATION_MODEL", "gpt-5.5")
CACHE = OUT / "ai_review_cache"

CAUSES = [
    "zero_instead_of_missing",
    "incorrect_attribution",
    "double_counting",
    "definition_or_unit",
    "program_does_not_measure_metric",
    "corporate_restructuring_timing",
    "source_reporting_error",
    "real_sector_structure",
    "real_extreme",
    "other",
]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "cause", "explanation", "action", "confidence", "needs_human"],
    "properties": {
        "verdict": {"type": "string", "enum": ["error", "plausible", "unclear"]},
        "cause": {"type": "string", "enum": CAUSES},
        "explanation": {"type": "string"},
        "action": {"type": "string", "enum": ["suppress", "flag", "correct", "keep"]},
        "confidence": {"type": "number"},
        "needs_human": {"type": "boolean"},
    },
}

SYSTEM = """Review unusual values in a sustainability dataset of US listed companies.
Use only the supplied evidence for company-specific figures. If you use general
knowledge about reporting programs or corporate events, identify it as general
knowledge rather than evidence from the packet.
Decide whether the observation can represent the company as currently attributed.
- error: the value or attribution is wrong or misleading, even if its cause is understood.
- plausible: the evidence supports an unusual but credible observation.
- unclear: the evidence is insufficient.
Set needs_human when source documents or raw-data access are needed.
Confidence is your uncalibrated confidence in the verdict; be conservative.
Reply concisely in English. Never invent replacement numerical values."""


def _key() -> str:
    k = os.environ.get("OPENAI_API_KEY", "")
    if not k:
        raise RuntimeError("OPENAI_API_KEY is missing from .env")
    return k


def _cache_path(packet: dict, model: str) -> Path:
    h = hashlib.sha256(json.dumps([packet, model, SYSTEM], sort_keys=True).encode()).hexdigest()[:24]
    return CACHE / f"{h}.json"


def review_one(packet: dict, model: str = MODEL, tries: int = 4) -> dict:
    """Review one packet, caching responses by packet, model, and prompt."""
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
        "text": {"format": {"type": "json_schema", "name": "quality_review", "schema": SCHEMA, "strict": True}},
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
    return {"verdict": "unclear", "cause": "other", "explanation": f"Review failed: {last}",
            "action": "flag", "confidence": 0.0, "needs_human": True, "model": model, "error": True}


def route(flag: dict, review: dict) -> str:
    """Route advice to automatic handling or human review. Uncertain cases first receive a second model review. Rule disagreement, ranking impact, large emissions impact, and unresolved evidence requests can trigger human review. Thresholds are design choices."""
    if review.get("error"):
        return "human"
    verdict, conf = review["verdict"], float(review.get("confidence") or 0)
    is_escalated = review.get("model") == ESCALATION_MODEL

    # Uncertain cases go to the stronger model before a human.
    if verdict == "unclear" or conf < UNCERTAIN:
        return "human" if is_escalated else "escalation"

    high_impact = bool(flag.get("ranking_relevant")) or float(flag.get("impact_t") or 0) >= 1_000_000
    intervenes = review["action"] in ("suppress", "correct")
    disagreement = flag.get("severity") == "error" and verdict == "plausible"

    # Rule/model disagreement is a reason for human review.
    if disagreement:
        return "human"
    # High-impact interventions affect a ranking or at least one million tonnes.
    if intervenes and high_impact:
        return "human"
    # The model requests evidence it lacks and remains uncertain.
    if review.get("needs_human") and conf < CONFIDENT:
        return "human"
    return "automatic"


def review_many(items: list[tuple[dict, dict]], workers: int = 6) -> list[dict]:
    """Review (flag, packet) pairs, escalating uncertain cases once."""

    def run(item):
        flag, packet = item
        rv = review_one(packet, MODEL)
        path = route(flag, rv)
        if path == "escalation":
            rv2 = review_one(packet, ESCALATION_MODEL)
            rv2["first_pass"] = {k: rv[k] for k in ("verdict", "cause", "confidence")}
            rv, path = rv2, route(flag, rv2)
        return {**flag, **{f"ai_{k}": v for k, v in rv.items() if k != "usage"},
                "route": path, "tokens": (rv.get("usage") or {}).get("total_tokens")}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, items))
