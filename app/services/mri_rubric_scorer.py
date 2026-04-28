"""
app/services/mri_rubric_scorer.py
==================================
Maya Revenue MRI — Hybrid Rubric Scorer foundation.

Computes a normalized rubric for an executed probe and persists it to
mri_probes.rubric_scores_json + evidence_quotes_json.

Hybrid design (foundation only — LLM path inactive in this version):
- Deterministic checks always run from probe.metadata_json fields.
- LLM-based dimensions are wired into the score-object shape but
  NOT computed here, because reply capture (P1) and recording/
  transcription (P2) are not yet implemented. As soon as those land,
  the LLM path can be enabled without changing this module's interface.

The scorer is intentionally humble:
- No score is invented for dimensions whose source data is missing.
  Their `source` is "not_available" and `score` is null.
- evidence_quotes_json is empty until real conversation text exists
  (no fabrication).
- analysis_limitations explicitly lists what is missing.

Supabase access matches the rest of the backend (service-key + httpx REST,
service key bypasses RLS).

Logging tags:
    [MRI-SCORE] score_start
    [MRI-SCORE] score_complete
    [MRI-SCORE] score_error
"""

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_T_PROBES = "mri_probes"
_T_SCANS = "mri_scans"
_REST_TIMEOUT = 10.0

SCORING_VERSION = "v1"
SCORING_VERSION_V2 = "v2"
SUPPORTED_PROBE_TYPES = ("P1_wa_offhours", "P2_call_peak")

# ─────────────────────────────────────────────────────────────
# V2 LLM-rubric config (used only when reply text exists for P1)
# ─────────────────────────────────────────────────────────────

_OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
    .replace("", "")
    .replace("", "")
    .replace("\r", "")
    .replace("\n", "")
)
_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_LLM_MODEL = "gpt-4o"
_LLM_TIMEOUT_SEC = 30

_LLM_RUBRIC_SYSTEM_PROMPT = """\
You are an expert clinical-funnel auditor. You will read a WhatsApp
interaction between a prospective implant patient (the "prospect") and a
boutique premium dental clinic. Score the CLINIC's responses on three
dimensions, each 0-20.

Replies may be in English, Hebrew, or other languages — score the substance,
not the language.

Dimensions:
- qualification_quality (0-20): Did the clinic ask qualifying questions
  about case complexity, budget, treatment readiness, or medical history?
  Did they show genuine intent-handling rather than canned response?
- booking_conversion (0-20): Did the clinic actively close toward a
  committed next step? Use this calibration:
    LOW (0-6):       "contact us" / generic invitation / no next step.
    MODERATE (7-13): mentioning availability alone, e.g. "we have Tuesday
                     slots" or "the doctor is in on Mondays" — informative
                     but the clinic has not yet closed or advanced.
    HIGH (14-20):    explicit consult-closing or advancing to a COMMITTED
                     next step, e.g. "I'm booking you for Tuesday 10am,
                     please confirm", "send your X-rays here so we can
                     schedule", "the doctor will call you at 14:00",
                     "click this link to confirm the slot".
- warmth (0-20): Human tone, empathy, professional politeness, attentive
  reading of what the prospect said. Personal vs. canned/robotic.

Be conservative: weak or absent evidence → low score. Do NOT invent
strengths the text does not show.

evidence_quotes: 0-4 short verbatim quotes (under 100 chars) from the
clinic reply that justify your scores. Each quote points to one dimension
and explains why it supports that score. Use empty list if no quote-worthy
evidence.

Return STRICT JSON ONLY (no prose, no markdown, no commentary):
{
  "qualification_quality": {"score": <int 0-20>, "reason": "<short>"},
  "booking_conversion":    {"score": <int 0-20>, "reason": "<short>"},
  "warmth":                {"score": <int 0-20>, "reason": "<short>"},
  "evidence_quotes": [
    {"dimension": "...", "quote": "...", "why_it_matters": "..."}
  ]
}
"""


class RubricScorerError(Exception):
    """Validation / configuration error preventing scoring."""


def _sb_headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


# ─────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────

async def _load_probe_with_scan(probe_id: str) -> tuple[dict, dict]:
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        raise RubricScorerError("Supabase env not configured")

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        r = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_PROBES}",
            params={"id": f"eq.{probe_id}", "select": "*"},
            headers=_sb_headers("count=none"),
        )
        if r.status_code >= 400:
            raise RubricScorerError(f"probe lookup failed: {r.status_code} {r.text}")
        rows = r.json()
        if not rows:
            raise RubricScorerError("probe not found")
        probe = rows[0]

        r2 = await client.get(
            f"{_SUPABASE_URL}/rest/v1/{_T_SCANS}",
            params={"id": f"eq.{probe['scan_id']}", "select": "*"},
            headers=_sb_headers("count=none"),
        )
        if r2.status_code >= 400:
            raise RubricScorerError(f"scan lookup failed: {r2.status_code} {r2.text}")
        scans = r2.json()
        if not scans:
            raise RubricScorerError("parent scan not found")
        scan = scans[0]

    return probe, scan


# ─────────────────────────────────────────────────────────────
# Score-object skeleton
# ─────────────────────────────────────────────────────────────

def _empty_dimensions() -> dict:
    return {
        "responsiveness":        {"score": None, "max": 20, "source": "not_available"},
        "qualification_quality": {"score": None, "max": 20, "source": "not_available"},
        "booking_conversion":    {"score": None, "max": 20, "source": "not_available"},
        "warmth":                {"score": None, "max": 20, "source": "not_available"},
        "evidence_quality":      {"score": None, "max": 20, "source": "not_available"},
    }


def _compute_overall(dims: dict) -> tuple[Optional[int], Optional[int]]:
    """
    Returns (deterministic_score_0_100, overall_score_0_100).

    deterministic_score: normalized over dimensions whose source == "metadata"
                         (i.e. dimensions actually scored).
    overall_score: same as deterministic_score until LLM scoring is enabled.
                   Returns (None, None) if no dimension was scored.
    """
    scored_pts = 0
    scored_max = 0
    for d in dims.values():
        if d.get("source") == "metadata" and isinstance(d.get("score"), (int, float)):
            scored_pts += d["score"]
            scored_max += d["max"]
    if scored_max == 0:
        return None, None
    det = round((scored_pts / scored_max) * 100)
    return det, det


# ─────────────────────────────────────────────────────────────
# P1 — WhatsApp off-hours (deterministic only)
# ─────────────────────────────────────────────────────────────

def _score_p1(probe: dict) -> dict:
    md = probe.get("metadata_json") or {}

    sent_successfully = (
        probe.get("status") == "executed"
        and bool(md.get("twilio_sid"))
        and not md.get("error")
    )
    delivery_status_available = bool(md.get("twilio_status"))
    persona_present = bool(md.get("persona_name"))
    target_present  = bool(md.get("twilio_to"))
    body_chars      = md.get("body_chars") or 0

    # responsiveness (max 20): did the message reach Twilio's queue?
    #   12 — send actually succeeded
    #    4 — Twilio returned a delivery status
    #    4 — body had non-trivial content
    resp_score = 0
    if sent_successfully:
        resp_score += 12
    if delivery_status_available:
        resp_score += 4
    if isinstance(body_chars, int) and body_chars >= 20:
        resp_score += 4

    # evidence_quality (max 20): is enough metadata captured for later analysis?
    #    5 each — persona, target, twilio_sid, sent_at
    ev_score = 0
    if persona_present:
        ev_score += 5
    if target_present:
        ev_score += 5
    if md.get("twilio_sid"):
        ev_score += 5
    if md.get("sent_at"):
        ev_score += 5

    dims = _empty_dimensions()
    dims["responsiveness"]   = {"score": resp_score, "max": 20, "source": "metadata"}
    dims["evidence_quality"] = {"score": ev_score,   "max": 20, "source": "metadata"}

    deterministic, overall = _compute_overall(dims)

    return {
        "scoring_version":    SCORING_VERSION,
        "probe_type":         "P1_wa_offhours",
        "signal_integrity_score":  overall,
        "deterministic_score": deterministic,
        "llm_score":          None,
        "diagnostic_confidence": "preliminary",
        "dimensions":         dims,
        "analysis_limitations": [
            "reply not captured yet",
            "qualification_quality, booking_conversion, warmth dimensions require reply text",
        ],
        "deterministic_facts": {
            "sent_successfully":         sent_successfully,
            "delivery_status_available": delivery_status_available,
            "persona_present":           persona_present,
            "target_present":            target_present,
        },
    }


# ─────────────────────────────────────────────────────────────
# P2 — outbound voice peak-hour (deterministic only)
# ─────────────────────────────────────────────────────────────

def _score_p2(probe: dict) -> dict:
    md = probe.get("metadata_json") or {}

    call_sid = md.get("twilio_call_sid")
    call_placed_successfully = (
        probe.get("status") == "executed"
        and bool(call_sid)
        and not md.get("error")
    )
    call_sid_present        = bool(call_sid)
    twilio_status_available = bool(md.get("twilio_status"))
    persona_present         = bool(md.get("persona_name"))
    target_present          = bool(md.get("twilio_to"))

    # responsiveness (max 20)
    resp_score = 0
    if call_placed_successfully:
        resp_score += 12
    if twilio_status_available:
        resp_score += 4
    if call_sid_present:
        resp_score += 4

    # evidence_quality (max 20)
    ev_score = 0
    if persona_present:
        ev_score += 5
    if target_present:
        ev_score += 5
    if call_sid_present:
        ev_score += 5
    if md.get("placed_at"):
        ev_score += 5

    dims = _empty_dimensions()
    dims["responsiveness"]   = {"score": resp_score, "max": 20, "source": "metadata"}
    dims["evidence_quality"] = {"score": ev_score,   "max": 20, "source": "metadata"}

    deterministic, overall = _compute_overall(dims)

    return {
        "scoring_version":    SCORING_VERSION,
        "probe_type":         "P2_call_peak",
        "signal_integrity_score":  overall,
        "deterministic_score": deterministic,
        "llm_score":          None,
        "diagnostic_confidence": "preliminary",
        "dimensions":         dims,
        "analysis_limitations": [
            "call recording/transcript not captured yet",
            "qualification_quality, booking_conversion, warmth dimensions require transcript",
        ],
        "deterministic_facts": {
            "call_placed_successfully": call_placed_successfully,
            "call_sid_present":         call_sid_present,
            "twilio_status_available":  twilio_status_available,
            "persona_present":          persona_present,
            "target_present":           target_present,
        },
    }


# ─────────────────────────────────────────────────────────────
# V2 — LLM rubric for P1 with captured reply text
# ─────────────────────────────────────────────────────────────

def _has_reply_text(probe: dict) -> bool:
    md = probe.get("metadata_json") or {}
    replies = md.get("reply_messages")
    if not isinstance(replies, list) or not replies:
        return False
    return any(
        isinstance(r, dict) and (r.get("body") or "").strip()
        for r in replies
    )


def _clamp_int(v, lo: int, hi: int) -> int:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return lo
    return int(round(max(lo, min(hi, x))))


def _build_llm_user_prompt(probe: dict) -> str:
    md = probe.get("metadata_json") or {}
    persona_name = md.get("persona_name") or "the prospect"
    outbound = (md.get("outbound_body") or "(outbound body not captured)").strip()
    replies = [
        r for r in (md.get("reply_messages") or [])
        if isinstance(r, dict) and (r.get("body") or "").strip()
    ]

    parts: list[str] = [
        f"OUTBOUND MESSAGE FROM {persona_name} (a prospective implant patient):",
        outbound,
        "",
        f"CLINIC REPLIES ({len(replies)} message(s)):",
    ]
    for i, r in enumerate(replies, 1):
        parts.append(f"--- Reply {i} ---")
        parts.append((r.get("body") or "").strip())
    parts.append("")
    parts.append("Score now. Return JSON only.")
    return "\n".join(parts)


def _call_openai_rubric_sync(system: str, user: str) -> str:
    """Sync OpenAI chat completion for rubric scoring. Caller wraps in to_thread."""
    payload = {
        "model": _LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    body = json.dumps(payload, ensure_ascii=True).encode("ascii", errors="ignore")
    req = urllib.request.Request(
        _OPENAI_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {_OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_LLM_TIMEOUT_SEC) as resp:
        raw = resp.read()
    data = json.loads(raw)
    return data["choices"][0]["message"]["content"]


async def _llm_score_p1(probe: dict) -> Optional[dict]:
    """
    Call the LLM to score the three rubric dimensions for a P1 probe with
    captured replies. Returns the parsed rubric dict on success, or None
    on any failure (caller falls back to v1 deterministic-only).
    Never raises.
    """
    if not _OPENAI_API_KEY:
        logger.warning(
            "[MRI-SCORE] llm_score_skipped probe_id=%s reason=no_openai_api_key",
            probe.get("id"),
        )
        return None

    logger.info("[MRI-SCORE] llm_score_start probe_id=%s", probe.get("id"))

    user_prompt = _build_llm_user_prompt(probe)

    try:
        content = await asyncio.to_thread(
            _call_openai_rubric_sync, _LLM_RUBRIC_SYSTEM_PROMPT, user_prompt,
        )
        rubric = json.loads(content)
    except Exception as exc:
        logger.error(
            "[MRI-SCORE] llm_score_error probe_id=%s error=%s",
            probe.get("id"), exc,
        )
        return None

    required_dims = ("qualification_quality", "booking_conversion", "warmth")
    for d in required_dims:
        if not isinstance(rubric.get(d), dict) or "score" not in rubric[d]:
            logger.error(
                "[MRI-SCORE] llm_score_error probe_id=%s reason=bad_shape missing=%s",
                probe.get("id"), d,
            )
            return None

    if not isinstance(rubric.get("evidence_quotes"), list):
        rubric["evidence_quotes"] = []

    for d in required_dims:
        rubric[d]["score"] = _clamp_int(rubric[d].get("score"), 0, 20)
        reason = rubric[d].get("reason")
        rubric[d]["reason"] = (reason if isinstance(reason, str) else "")[:300]

    logger.info(
        "[MRI-SCORE] llm_score_complete probe_id=%s qq=%s bc=%s w=%s evidence=%d",
        probe.get("id"),
        rubric["qualification_quality"]["score"],
        rubric["booking_conversion"]["score"],
        rubric["warmth"]["score"],
        len(rubric["evidence_quotes"]),
    )
    return rubric


def _merge_v2_p1(deterministic_rubric: dict, llm_rubric: dict) -> dict:
    """
    Blend the LLM-scored dimensions into the v1 deterministic rubric and
    update headline numbers + confidence + scoring_version.
    """
    out = dict(deterministic_rubric)
    dims = dict(out.get("dimensions") or {})

    for d in ("qualification_quality", "booking_conversion", "warmth"):
        score = _clamp_int(llm_rubric[d].get("score"), 0, 20)
        reason = llm_rubric[d].get("reason") or ""
        dims[d] = {
            "score":  score,
            "max":    20,
            "source": "llm",
            "reason": reason,
        }
    out["dimensions"] = dims

    llm_total = sum(
        dims[d]["score"]
        for d in ("qualification_quality", "booking_conversion", "warmth")
    )
    llm_score = round((llm_total / 60) * 100)
    out["llm_score"] = llm_score

    deterministic_score = out.get("deterministic_score")
    if deterministic_score is None:
        out["signal_integrity_score"] = llm_score
    else:
        out["signal_integrity_score"] = round(
            0.4 * deterministic_score + 0.6 * llm_score
        )

    evidence_count = len(llm_rubric.get("evidence_quotes") or [])
    out["diagnostic_confidence"] = "high" if evidence_count >= 2 else "medium"

    out["analysis_limitations"] = []
    out["scoring_version"] = SCORING_VERSION_V2

    return out


# ─────────────────────────────────────────────────────────────
# Persist
# ─────────────────────────────────────────────────────────────

async def _persist_score(
    probe: dict,
    rubric: dict,
    evidence_quotes: list,
) -> dict:
    scored_at = datetime.now(timezone.utc).isoformat()

    # Merge into existing metadata_json — don't lose Twilio fields.
    existing_md = probe.get("metadata_json") or {}
    new_md = {
        **existing_md,
        "scored_at":        scored_at,
        "scoring_version":  rubric.get("scoring_version") or SCORING_VERSION,
    }

    body = {
        "rubric_scores_json":   rubric,
        "evidence_quotes_json": evidence_quotes,
        "metadata_json":        new_md,
    }

    async with httpx.AsyncClient(timeout=_REST_TIMEOUT) as client:
        r = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/{_T_PROBES}",
            params={"id": f"eq.{probe['id']}"},
            json=body,
            headers=_sb_headers(),
        )
        if r.status_code >= 400:
            raise RubricScorerError(f"persist failed: {r.status_code} {r.text}")
        rows = r.json()
        return rows[0] if rows else {}


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

_DISPATCH = {
    "P1_wa_offhours": _score_p1,
    "P2_call_peak":   _score_p2,
}


async def score_probe(probe_id: str) -> dict:
    """
    Compute and persist the rubric for an executed probe.

    Behavior:
      - Loads probe + parent scan.
      - Validates probe.status == 'executed' (else RubricScorerError).
      - Validates probe_type ∈ SUPPORTED_PROBE_TYPES (else RubricScorerError).
      - Computes deterministic dimensions only (LLM path not active).
      - Persists rubric_scores_json, evidence_quotes_json (empty until
        text exists), and merges scored_at + scoring_version into
        metadata_json.
      - Allows re-scoring (overwrites prior result, refreshes scored_at).

    Returns the updated probe row.
    """
    logger.info("[MRI-SCORE] score_start probe_id=%s", probe_id)

    probe, _scan = await _load_probe_with_scan(probe_id)

    if probe.get("status") != "executed":
        raise RubricScorerError(
            f"probe must be executed before scoring (status={probe.get('status')!r})"
        )

    probe_type = probe.get("probe_type") or ""
    if probe_type not in _DISPATCH:
        raise RubricScorerError(
            f"unsupported probe_type: {probe_type!r} "
            f"(scorer supports: {list(_DISPATCH.keys())})"
        )

    try:
        rubric = _DISPATCH[probe_type](probe)
    except Exception as exc:
        logger.error(
            "[MRI-SCORE] score_error probe_id=%s probe_type=%s error=%s",
            probe_id, probe_type, exc,
        )
        raise RubricScorerError(f"scoring computation failed: {exc}") from exc

    evidence_quotes: list = []

    # V2 — LLM rubric scoring for P1 with captured reply text.
    # On any failure (no API key, network, bad shape), _llm_score_p1
    # returns None and we fall through with the v1 deterministic-only
    # rubric — partial result is better than no result.
    if probe_type == "P1_wa_offhours" and _has_reply_text(probe):
        llm_rubric = await _llm_score_p1(probe)
        if llm_rubric is not None:
            rubric = _merge_v2_p1(rubric, llm_rubric)
            evidence_quotes = llm_rubric.get("evidence_quotes") or []

    updated = await _persist_score(probe, rubric, evidence_quotes)

    logger.info(
        "[MRI-SCORE] score_complete probe_id=%s probe_type=%s "
        "overall=%s deterministic=%s confidence=%s",
        probe_id, probe_type,
        rubric.get("signal_integrity_score"),
        rubric.get("deterministic_score"),
        rubric.get("diagnostic_confidence"),
    )
    return updated
