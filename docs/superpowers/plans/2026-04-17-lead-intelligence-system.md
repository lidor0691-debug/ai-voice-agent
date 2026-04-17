# Lead Intelligence System — Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Supabase table, heuristic extraction service, dedup/upsert storage layer, and internal test API endpoint for the Lead Intelligence System — isolated from all live production flows.

**Architecture:** A pure-Python extraction function splits conversation text into candidate sentences and classifies them as questions or objections using heuristics (trailing `?`, question-word prefixes, objection cue phrases). Extracted insights are stored in a new `lead_intelligence_insights` Supabase table, scoped by `client_id`, with read-then-write dedup that increments `frequency_count` on repeated normalized text. A single internal FastAPI route (`POST /lead-intelligence/test-extract`) exposes the full extract→save pipeline for validation.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, httpx (async), Supabase REST API (service key), pytest + pytest-asyncio

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/create_lead_intelligence_insights.sql` | Create | Table DDL, constraints, indexes, updated_at trigger |
| `app/services/lead_intelligence.py` | Create | `normalize_text`, `extract_insights`, `save_insights` |
| `app/routes/lead_intelligence_api.py` | Create | `POST /lead-intelligence/test-extract` route |
| `tests/test_lead_intelligence.py` | Create | Unit tests for extraction and save logic |
| `main.py` | Modify | Register the new router |

---

## Task 1: SQL Migration

**Files:**
- Create: `supabase/migrations/create_lead_intelligence_insights.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- supabase/migrations/create_lead_intelligence_insights.sql
-- Lead Intelligence System — initial schema
-- RLS NOTE: This table uses client_id for tenant scoping.
-- Before any non-service-key or direct dashboard DB access is introduced,
-- add ENABLE ROW LEVEL SECURITY and a policy based on the actual
-- user→client ownership model in the project at that time.
-- Do NOT assume client_id = auth.uid().

-- Reusable updated_at trigger function (create only if not already defined)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS public.lead_intelligence_insights (
    id                uuid        NOT NULL DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    client_id         uuid        NOT NULL REFERENCES clients(id),
    agent_id          text,
    source_type       text        NOT NULL,
    source_record_id  text,
    insight_type      text        NOT NULL,
    title             text        NOT NULL,
    normalized_text   text        NOT NULL,
    original_text     text        NOT NULL,
    intent_category   text,
    frequency_count   int         NOT NULL DEFAULT 1,
    status            text        NOT NULL DEFAULT 'new',
    metadata          jsonb,

    CONSTRAINT lead_intelligence_insights_pkey PRIMARY KEY (id),
    CONSTRAINT chk_source_type   CHECK (source_type  IN ('whatsapp', 'call', 'chat')),
    CONSTRAINT chk_insight_type  CHECK (insight_type IN ('question', 'objection', 'topic', 'faq_candidate', 'intent_signal', 'content_opportunity')),
    CONSTRAINT chk_status        CHECK (status       IN ('new', 'reviewed', 'dismissed')),
    CONSTRAINT chk_frequency     CHECK (frequency_count > 0),
    CONSTRAINT uq_dedup          UNIQUE (client_id, insight_type, normalized_text)
);

CREATE INDEX IF NOT EXISTS idx_lii_client_id
    ON public.lead_intelligence_insights (client_id);

CREATE INDEX IF NOT EXISTS idx_lii_client_insight_type
    ON public.lead_intelligence_insights (client_id, insight_type);

DROP TRIGGER IF EXISTS trg_lii_updated_at ON public.lead_intelligence_insights;
CREATE TRIGGER trg_lii_updated_at
    BEFORE UPDATE ON public.lead_intelligence_insights
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

- [ ] **Step 2: Apply the migration via Supabase dashboard or CLI**

If using Supabase CLI:
```bash
supabase db push
```

If applying manually, paste the SQL into the Supabase SQL editor and run it.

Verify by checking that the table `lead_intelligence_insights` appears in the Supabase table editor with all columns.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/create_lead_intelligence_insights.sql
git commit -m "feat(lead-intelligence): add lead_intelligence_insights migration"
```

---

## Task 2: Extraction Service — `normalize_text` + `extract_insights`

**Files:**
- Create: `app/services/lead_intelligence.py`
- Create: `tests/test_lead_intelligence.py`

- [ ] **Step 1: Write the failing tests for `normalize_text`**

Create `tests/test_lead_intelligence.py`:

```python
"""
Tests for app/services/lead_intelligence.py
"""
import pytest
from app.services.lead_intelligence import normalize_text, extract_insights


# ── normalize_text ────────────────────────────────────────────────────────────

def test_normalize_lowercase():
    assert normalize_text("Hello World") == "hello world"


def test_normalize_strips_whitespace():
    assert normalize_text("  hello  ") == "hello"


def test_normalize_collapses_internal_whitespace():
    assert normalize_text("hello   world") == "hello world"


def test_normalize_strips_trailing_punctuation_not_question_mark():
    # .,!;: are stripped — ? is NOT stripped by normalize_text
    assert normalize_text("hello world.") == "hello world"
    assert normalize_text("hello world,") == "hello world"
    assert normalize_text("hello world!") == "hello world"
    assert normalize_text("hello world;") == "hello world"
    assert normalize_text("hello world:") == "hello world"
    assert normalize_text("מה המחיר?") == "מה המחיר?"  # ? preserved


def test_normalize_empty_string():
    assert normalize_text("") == ""


def test_normalize_only_whitespace():
    assert normalize_text("   ") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd c:/Users/lidor/maya-ai
pytest tests/test_lead_intelligence.py -v
```

Expected: `ImportError` — `app.services.lead_intelligence` does not exist yet.

- [ ] **Step 3: Write failing tests for `extract_insights`**

Append to `tests/test_lead_intelligence.py`:

```python
# ── extract_insights ──────────────────────────────────────────────────────────

def test_extract_question_by_trailing_question_mark():
    results = extract_insights("כמה עולה המנוי?")
    assert len(results) == 1
    r = results[0]
    assert r["insight_type"] == "question"
    assert r["metadata"]["matched_rule"] == "ends_with_question_mark"
    assert r["original_text"] == "כמה עולה המנוי?"
    assert r["normalized_text"] == "כמה עולה המנוי"  # ? stripped by caller


def test_extract_question_by_question_word():
    results = extract_insights("מה כולל המחיר")
    assert len(results) == 1
    r = results[0]
    assert r["insight_type"] == "question"
    assert r["metadata"]["matched_rule"] == "question_word"


def test_extract_question_mark_takes_precedence_over_question_word():
    # sentence starts with question word AND ends with ? → ends_with_question_mark wins
    results = extract_insights("מה המחיר?")
    assert results[0]["metadata"]["matched_rule"] == "ends_with_question_mark"


def test_extract_objection():
    results = extract_insights("זה יקר מדי בשבילי")
    assert len(results) == 1
    assert results[0]["insight_type"] == "objection"
    assert results[0]["metadata"]["matched_rule"] == "objection_cue"


def test_extract_multi_pattern_emits_two_insights():
    # question word + objection cue in same sentence
    results = extract_insights("האם זה לא יקר מדי?")
    insight_types = {r["insight_type"] for r in results}
    assert "question" in insight_types
    assert "objection" in insight_types
    assert len(results) == 2


def test_extract_skips_noise_under_2_words_no_match():
    results = extract_insights("אוקי")
    assert results == []


def test_extract_keeps_short_question():
    # short but matches question pattern
    results = extract_insights("מחיר?")
    assert len(results) == 1
    assert results[0]["insight_type"] == "question"


def test_extract_title_is_first_6_words():
    results = extract_insights("מה כולל החבילה הזאת בדיוק ולמה היא עולה כל כך הרבה?")
    assert results[0]["title"] == "מה כולל החבילה הזאת בדיוק ולמה"


def test_extract_title_fallback_when_too_short():
    # Single-word candidate that matches (e.g. "למה?")
    results = extract_insights("למה?")
    # normalized_text after rstrip("?") → "למה" — 1 word — fallback applies
    assert results[0]["title"] == "insight"


def test_extract_splits_on_newline():
    text = "מה המחיר?\nאני לא בטוח שזה מתאים לי"
    results = extract_insights(text)
    types = {r["insight_type"] for r in results}
    assert "question" in types
    assert "objection" in types


def test_extract_does_not_split_on_question_mark():
    # Two questions in one string separated by space, not newline or .
    # Should be treated as one candidate sentence
    text = "מה המחיר? ומה כולל?"
    results = extract_insights(text)
    # Both are from the same unsplit string — at least one question detected
    assert any(r["insight_type"] == "question" for r in results)


def test_extract_english_question_word():
    results = extract_insights("How much does it cost")
    assert results[0]["insight_type"] == "question"
    assert results[0]["metadata"]["matched_rule"] == "question_word"


def test_extract_english_objection():
    results = extract_insights("I'm not sure this is the right fit for me")
    assert results[0]["insight_type"] == "objection"


def test_extract_metadata_has_extraction_version():
    results = extract_insights("מה המחיר?")
    assert results[0]["metadata"]["extraction_version"] == "1.0"
```

- [ ] **Step 4: Run new tests to confirm they fail**

```bash
pytest tests/test_lead_intelligence.py -v
```

Expected: `ImportError` still — implementation not written yet.

- [ ] **Step 5: Implement `app/services/lead_intelligence.py`**

Create `app/services/lead_intelligence.py`:

```python
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
_EXTRACTION_VERSION = "1.0"

_QUESTION_WORDS = {
    "מה", "איך", "כמה", "האם", "מתי", "למה",
    "what", "how", "when", "why", "is", "can", "do", "does",
}

_OBJECTION_CUES = [
    "יקר מדי", "יקר", "לא בטוח", "צריך לחשוב",
    "too expensive", "not sure", "need to think", "maybe later", "not interested",
]


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """
    Lowercase, strip, collapse whitespace, strip trailing .,!;:
    Does NOT remove ?  — callers strip ? themselves when building
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
    """Return matched_rule string or None. Checks original candidate text."""
    if candidate.rstrip().endswith("?"):
        return "ends_with_question_mark"
    if _first_word(candidate) in _QUESTION_WORDS:
        return "question_word"
    return None


def _detect_objection(candidate: str) -> bool:
    """Check original candidate text for objection cue phrases."""
    lower = candidate.lower()
    return any(cue in lower for cue in _OBJECTION_CUES)


def extract_insights(text: str) -> list[dict]:
    """
    Pure heuristic extraction from raw conversation text.
    Returns a list of insight dicts ready for storage.

    Detection uses the original candidate text.
    normalized_text = normalize_text(candidate).rstrip("?")
    """
    results = []

    for candidate in _split_sentences(text):
        question_rule = _detect_question(candidate)
        is_objection = _detect_objection(candidate)

        # Skip noise: fewer than 2 words and no pattern match
        if _word_count(candidate) < 2 and not question_rule and not is_objection:
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


async def _find_existing(client: httpx.AsyncClient, client_id: str, insight_type: str, normalized_text: str) -> Optional[dict]:
    """Return existing row matching dedup key, or None."""
    resp = await client.get(
        f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
        params={
            "client_id":      f"eq.{client_id}",
            "insight_type":   f"eq.{insight_type}",
            "normalized_text": f"eq.{normalized_text}",
            "limit":          "1",
        },
        headers=_headers(),
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


async def _increment_frequency(client: httpx.AsyncClient, row_id: str, current_count: int) -> dict:
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
                    updated = await _increment_frequency(client, existing["id"], existing["frequency_count"])
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
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/test_lead_intelligence.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/services/lead_intelligence.py tests/test_lead_intelligence.py
git commit -m "feat(lead-intelligence): add extraction service and tests"
```

---

## Task 3: API Route

**Files:**
- Create: `app/routes/lead_intelligence_api.py`

- [ ] **Step 1: Write the failing test for the route**

Append to `tests/test_lead_intelligence.py`:

```python
# ── API route ─────────────────────────────────────────────────────────────────

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_test_extract_route_returns_extracted_and_saved():
    from main import app

    mock_saved = [{"id": "abc", "insight_type": "question", "frequency_count": 1}]

    with patch("app.routes.lead_intelligence_api.save_insights", new=AsyncMock(return_value=mock_saved)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/lead-intelligence/test-extract", json={
                "client_id":  "00000000-0000-0000-0000-000000000001",
                "agent_id":   None,
                "source_type": "whatsapp",
                "source_record_id": None,
                "text": "מה המחיר?"
            })

    assert resp.status_code == 200
    body = resp.json()
    assert "extracted" in body
    assert "saved" in body
    assert len(body["extracted"]) >= 1
    assert body["extracted"][0]["insight_type"] == "question"
    assert body["saved"] == mock_saved


@pytest.mark.asyncio
async def test_test_extract_route_validates_source_type():
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/lead-intelligence/test-extract", json={
            "client_id":   "00000000-0000-0000-0000-000000000001",
            "source_type": "invalid_source",
            "text":        "מה המחיר?"
        })

    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_lead_intelligence.py::test_test_extract_route_returns_extracted_and_saved -v
pytest tests/test_lead_intelligence.py::test_test_extract_route_validates_source_type -v
```

Expected: FAIL — route does not exist.

- [ ] **Step 3: Implement the route**

Create `app/routes/lead_intelligence_api.py`:

```python
"""
app/routes/lead_intelligence_api.py
=====================================
POST /lead-intelligence/test-extract

Internal endpoint for validating Lead Intelligence extraction and storage.
Accepts raw conversation text + context, runs heuristic extraction,
saves to lead_intelligence_insights, and returns both extracted and saved results.

Not wired into any live production flow. Call manually or from tests only.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.lead_intelligence import extract_insights, save_insights

logger = logging.getLogger(__name__)
router = APIRouter()


class TestExtractRequest(BaseModel):
    client_id:        str
    agent_id:         Optional[str] = None
    source_type:      Literal["whatsapp", "call", "chat"]
    source_record_id: Optional[str] = None
    text:             str


@router.post("/lead-intelligence/test-extract")
async def test_extract(req: TestExtractRequest):
    """
    Extract insights from raw text and save to lead_intelligence_insights.

    Returns:
        extracted: list of insight dicts produced by extract_insights (pre-save)
        saved:     list of rows returned by save_insights (upserted to DB)
    """
    extracted = extract_insights(req.text)

    saved = await save_insights(
        insights=extracted,
        client_id=req.client_id,
        agent_id=req.agent_id,
        source_type=req.source_type,
        source_record_id=req.source_record_id,
    )

    return {"extracted": extracted, "saved": saved}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_lead_intelligence.py::test_test_extract_route_returns_extracted_and_saved -v
pytest tests/test_lead_intelligence.py::test_test_extract_route_validates_source_type -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routes/lead_intelligence_api.py tests/test_lead_intelligence.py
git commit -m "feat(lead-intelligence): add test-extract API route"
```

---

## Task 4: Register Router in `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add the import and router registration**

Open `main.py`. After the last existing `from app.routes...` import line, add:

```python
from app.routes.lead_intelligence_api import router as lead_intelligence_router
```

After the last existing `app.include_router(...)` call, add:

```python
app.include_router(lead_intelligence_router)
```

- [ ] **Step 2: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS. No regressions.

- [ ] **Step 3: Smoke-test the server locally (optional but recommended)**

```bash
uvicorn main:app --reload --port 8001
```

Then in a separate terminal:

```bash
curl -s -X POST http://localhost:8001/lead-intelligence/test-extract \
  -H "Content-Type: application/json" \
  -d '{"client_id":"<a real client_id uuid from your DB>","source_type":"whatsapp","text":"מה המחיר? אני לא בטוח שזה מתאים לי"}' \
  | python -m json.tool
```

Expected response shape:
```json
{
  "extracted": [
    {"insight_type": "question", "original_text": "מה המחיר?", ...},
    {"insight_type": "objection", "original_text": "אני לא בטוח שזה מתאים לי", ...}
  ],
  "saved": [...]
}
```

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(lead-intelligence): register router in main.py"
```

---

## Self-Review

**Spec coverage:**
- [x] `lead_intelligence_insights` table with all columns, constraints, indexes, trigger — Task 1
- [x] `normalize_text` — Task 2
- [x] `extract_insights` with question/objection detection, precedence, multi-pattern, skip rule, title, metadata — Task 2
- [x] `save_insights` with read-then-write dedup, frequency increment, never raises, atomicity note in docstring — Task 2
- [x] `POST /lead-intelligence/test-extract` route with `extracted` + `saved` response — Task 3
- [x] `source_type` validated via `Literal` at route level (Pydantic) — Task 3
- [x] Router registered in `main.py` — Task 4
- [x] Zero changes to existing production routes/services — verified: only `main.py` import added

**Future wiring point (from spec):** documented in spec; not implemented here by design.

**RLS note:** present in migration file as a comment — matches spec requirement.

---

## Follow-Up: Next Step

When ready to ingest from the live WhatsApp pipeline, wire in at:

`app/services/whatsapp_reply.py` → `_generate_whatsapp_reply_inner()`, **after line 229** (`await append_whatsapp_messages(...)`):

```python
try:
    from app.services.lead_intelligence import extract_insights, save_insights as _save_insights
    _insights = extract_insights(user_message)
    await _save_insights(
        insights=_insights,
        client_id=agent.get("client_id") or "",
        agent_id=agent.get("agent_id"),
        source_type="whatsapp",
        source_record_id=None,
    )
except Exception as _exc:
    logger.warning("[LEAD INTELLIGENCE] extraction failed: %s", _exc)
```
