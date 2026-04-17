"""
app/services/lead_intelligence.py
===================================
Lead Intelligence System — extraction and storage layer.

Public API
----------
normalize_text(text: str) -> str
    Pure normalization: lowercase, strip, collapse whitespace,
    strip trailing .,!;: — does NOT remove ?.

extract_insights(text: str) -> list[dict]
    Pure heuristic extraction. Splits text into candidate sentences,
    classifies each as question or objection. Returns structured dicts
    ready for storage. No I/O.

save_insights(insights, client_id, agent_id, source_type, source_record_id) -> list[dict]
    Async. Deduplicates against existing rows by (client_id, insight_type,
    normalized_text): increments frequency_count if found, inserts if not.
    Never raises — errors are logged.

NOTE (atomicity): The current read-then-write dedup is acceptable for
internal/low-volume use. For higher-volume ingestion replace with:
  ON CONFLICT (client_id, insight_type, normalized_text)
  DO UPDATE SET frequency_count = frequency_count + 1
"""

import logging
import os
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_TABLE = "lead_intelligence_insights"
_EXTRACTION_VERSION = "1.1"

_QUESTION_WORDS = {
    "מה", "איך", "כמה", "האם", "מתי", "למה",
    "what", "how", "when", "why", "is", "can", "do", "does",
}

_OBJECTION_CUES = [
    "יקר מדי", "יקר", "לא בטוח", "צריך לחשוב",
    "too expensive", "not sure", "need to think", "maybe later", "not interested",
]

# Intent signal rules — ordered list of (matched_rule_name, cue_phrases).
# First matching rule wins within each rule group.
# Designed for real BPM WhatsApp response patterns where users answer Maya's
# prompts rather than asking direct questions.
_INTENT_SIGNAL_RULES: list[tuple[str, list[str]]] = [
    # Interest / inquiry — user expresses interest in a service
    ("interest_cue", [
        "מתעניינת", "מתעניין",
        "לגבי בת מצווה", "לגבי שיעור", "לגבי ריקוד",
        "רוצה לדעת",
        "interested in",
    ]),
    # Hesitation — user is undecided or stalling
    ("hesitation_cue", [
        "מתלבטת", "מתלבט",
        "כרגע אין", "כרגע לא",
        "עדיין לא",
        "אין תאריך",
        "still deciding", "not sure yet",
    ]),
    # Context — factual user-state signals relevant to the service
    ("context_cue", [
        "אין לה ניסיון", "אין ניסיון",
        "לא מנוסה",
        "אין ניסיון קודם",
        "no experience", "no prior experience",
    ]),
]


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """
    Lowercase, strip, collapse whitespace, strip trailing .,!;:
    Does NOT remove ? — callers strip ? themselves when building
    normalized_text for dedup: normalize_text(s).rstrip("?")
    """
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(".,!;:")
    return text


# ── Extraction ────────────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Split on newlines and . / ! but NOT on ? to preserve question markers."""
    parts = re.split(r"[\n.!]+", text)
    return [p.strip() for p in parts if p.strip()]


def _first_word(text: str) -> str:
    words = text.strip().split()
    return words[0].lower() if words else ""


def _word_count(text: str) -> int:
    return len(text.strip().split())


def _make_title(normalized: str) -> str:
    words = normalized.split()
    if len(words) < 2:
        return "insight"
    return " ".join(words[:6])


def _detect_question(candidate: str) -> Optional[str]:
    """Return matched_rule string or None. Uses original candidate text. First match wins."""
    if candidate.rstrip().endswith("?"):
        return "ends_with_question_mark"
    if _first_word(candidate) in _QUESTION_WORDS:
        return "question_word"
    return None


def _detect_objection(candidate: str) -> bool:
    """Check original candidate text for objection cue phrases."""
    lower = candidate.lower()
    return any(cue in lower for cue in _OBJECTION_CUES)


def _detect_intent_signal(candidate: str) -> Optional[str]:
    """
    Return the first matching intent signal rule name, or None.
    Uses original candidate text. Checks rule groups in order — first match wins.
    """
    lower = candidate.lower()
    for rule_name, cues in _INTENT_SIGNAL_RULES:
        if any(cue in lower for cue in cues):
            return rule_name
    return None


def extract_insights(text: str) -> list[dict]:
    """
    Pure heuristic extraction from raw conversation text.
    Returns a list of insight dicts ready for storage.

    Detection uses the original candidate text.
    normalized_text = normalize_text(candidate).rstrip("?")

    Each candidate can produce multiple insights (e.g. question + objection,
    or objection + intent_signal) — each as a separate dict.
    """
    results = []

    for candidate in _split_sentences(text):
        question_rule = _detect_question(candidate)
        is_objection = _detect_objection(candidate)
        intent_rule = _detect_intent_signal(candidate)

        # Skip noise: fewer than 2 words and no pattern match at all
        if _word_count(candidate) < 2 and not question_rule and not is_objection and not intent_rule:
            continue

        normalized = normalize_text(candidate).rstrip("?")
        title = _make_title(normalized)

        if question_rule:
            results.append({
                "insight_type":    "question",
                "original_text":   candidate,
                "normalized_text": normalized,
                "title":           title,
                "metadata": {
                    "matched_rule":       question_rule,
                    "extraction_version": _EXTRACTION_VERSION,
                },
            })

        if is_objection:
            results.append({
                "insight_type":    "objection",
                "original_text":   candidate,
                "normalized_text": normalized,
                "title":           title,
                "metadata": {
                    "matched_rule":       "objection_cue",
                    "extraction_version": _EXTRACTION_VERSION,
                },
            })

        if intent_rule:
            results.append({
                "insight_type":    "intent_signal",
                "original_text":   candidate,
                "normalized_text": normalized,
                "title":           title,
                "metadata": {
                    "matched_rule":       intent_rule,
                    "extraction_version": _EXTRACTION_VERSION,
                },
            })

    return results


# ── Storage ───────────────────────────────────────────────────────────────────

def _is_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


def _headers() -> dict:
    return {
        "apikey":        _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


async def _find_existing(
    client: httpx.AsyncClient,
    client_id: str,
    insight_type: str,
    normalized_text: str,
) -> Optional[dict]:
    """Return existing row matching dedup key (client_id, insight_type, normalized_text), or None."""
    resp = await client.get(
        f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
        params={
            "client_id":       f"eq.{client_id}",
            "insight_type":    f"eq.{insight_type}",
            "normalized_text": f"eq.{normalized_text}",
            "limit":           "1",
        },
        headers=_headers(),
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


async def _increment_frequency(
    client: httpx.AsyncClient,
    row_id: str,
    current_count: int,
) -> dict:
    """Increment frequency_count on an existing row."""
    patch_headers = {**_headers(), "Prefer": "return=representation"}
    resp = await client.patch(
        f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
        params={"id": f"eq.{row_id}"},
        json={"frequency_count": current_count + 1},
        headers=patch_headers,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else {}


async def _insert_insight(client: httpx.AsyncClient, payload: dict) -> dict:
    """Insert a new insight row."""
    resp = await client.post(
        f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
        json=payload,
        headers=_headers(),
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else {}


async def save_insights(
    insights: list[dict],
    client_id: str,
    agent_id: Optional[str],
    source_type: str,
    source_record_id: Optional[str],
) -> list[dict]:
    """
    Persist extracted insights to lead_intelligence_insights.

    For each insight:
    - If (client_id, insight_type, normalized_text) already exists → increment frequency_count
    - Otherwise → insert new row

    All reads and writes are explicitly scoped by client_id.
    Never raises — errors are logged and the partial results list is returned.
    """
    if not _is_configured():
        logger.warning("[LEAD INTELLIGENCE] Supabase not configured — skipping save")
        return []

    if not insights:
        return []

    saved = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for insight in insights:
            try:
                existing = await _find_existing(
                    client,
                    client_id,
                    insight["insight_type"],
                    insight["normalized_text"],
                )
                if existing:
                    updated = await _increment_frequency(
                        client, existing["id"], existing["frequency_count"]
                    )
                    saved.append(updated)
                else:
                    payload = {
                        "client_id":        client_id,
                        "agent_id":         agent_id,
                        "source_type":      source_type,
                        "source_record_id": source_record_id,
                        "insight_type":     insight["insight_type"],
                        "title":            insight["title"],
                        "normalized_text":  insight["normalized_text"],
                        "original_text":    insight["original_text"],
                        "metadata":         insight.get("metadata"),
                    }
                    inserted = await _insert_insight(client, payload)
                    saved.append(inserted)
            except Exception as exc:
                logger.error(
                    "[LEAD INTELLIGENCE] Failed to save insight type=%s normalized=%r: %s",
                    insight.get("insight_type"), insight.get("normalized_text"), exc,
                )

    return saved
