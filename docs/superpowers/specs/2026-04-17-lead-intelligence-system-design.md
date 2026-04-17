# Lead Intelligence System — Backend Foundation Design

**Date:** 2026-04-17
**Status:** Approved
**Scope:** Backend/data foundation only. No dashboard UI. No OpenAI. No production pipeline wiring.

---

## Overview

Extract reusable business intelligence from real conversations (WhatsApp, calls, chat).
Identifies recurring customer questions, objections, topics, and intent signals.
Stores structured insights in Supabase, scoped per client/tenant.

This first step builds the extraction service, storage layer, dedup logic, and an internal test API endpoint.
It is intentionally isolated from the live WhatsApp pipeline until extraction quality is validated.

---

## Schema: `public.lead_intelligence_insights`

```sql
CREATE TABLE public.lead_intelligence_insights (
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
```

**Indexes:**
- `(client_id)` — all queries scoped by client
- `(client_id, insight_type)` — dashboard filters
- The UNIQUE constraint on `(client_id, insight_type, normalized_text)` also serves as the dedup lookup index

**`agent_id`:** typed as `text`, nullable. Matches the opaque string identifier used for `agents_config.id` throughout the codebase. No FK enforced until the identifier type is stabilized.

**`updated_at`:** maintained by a `BEFORE UPDATE` trigger using `set_updated_at()`.

### Future RLS Note

This table uses `client_id` as a tenant scoping column. Before any non-service-key or direct dashboard DB access is introduced, add `ENABLE ROW LEVEL SECURITY` and a policy based on the actual user→client ownership model established in the project at that time (e.g., a `user_clients` join table or `profiles.client_id`). **Do not assume `client_id = auth.uid()`** — `client_id` is tenant scoping, not user identity.

---

## Service: `app/services/lead_intelligence.py`

### `normalize_text(text: str) → str`

Normalization rule (used for both extraction and dedup):
1. Lowercase
2. Strip leading/trailing whitespace
3. Collapse internal whitespace to single space
4. Strip trailing punctuation: `.,!;:` — **not** `?` during detection, but `?` is stripped when producing `normalized_text` for dedup consistency

### `extract_insights(text: str) → list[dict]`

Pure function. No I/O. No `source_type` param — extraction is source-agnostic.

**Sentence splitting:**
Split on `\n` and `.` / `!` only — **not** on `?`. This keeps `?` attached to its sentence so question detection by trailing marker is reliable.

**Per candidate sentence:**

Detection uses the **original candidate text** (before normalization).
Dedup key (`normalized_text`) uses the normalized form with trailing punctuation including `?` stripped.

| Pattern | Rule |
|---|---|
| **question** | candidate ends with `?` OR first word (lowercased) is in question word list |
| **objection** | candidate contains an objection cue phrase |

Question words: `מה`, `איך`, `כמה`, `האם`, `מתי`, `למה`, `what`, `how`, `when`, `why`, `is`, `can`, `do`, `does`

Objection cues: `יקר`, `לא בטוח`, `צריך לחשוב`, `too expensive`, `not sure`, `need to think`, `maybe later`, `not interested`

**Multi-pattern candidates:** if a sentence matches both question and objection patterns, emit two separate insight dicts with different `insight_type` values.

**Skip rule:** skip candidates with fewer than 2 words that do not match any pattern. Short candidates that do match a pattern are kept.

**Output per insight:**
```python
{
    "insight_type":     "question" | "objection",
    "original_text":    original candidate sentence,
    "normalized_text":  normalize_text(candidate),  # trailing ? also stripped here
    "title":            first_6_words(normalized_text) or fallback,
    "metadata": {
        "matched_rule":        "ends_with_question_mark" | "question_word" | "objection_cue",
        "extraction_version":  "1.0"
    }
}
```

**Title rule:** first 6 words of `normalized_text`. No casing transform (preserves Hebrew). Fallback: if fewer than 2 words remain after normalization, use `"insight"` as safe fallback label.

### `save_insights(insights, client_id, agent_id, source_type, source_record_id) → list[dict]`

Async. Uses `httpx.AsyncClient` + Supabase REST, matching `lead_capture.py` pattern exactly.

Per insight:
1. GET `lead_intelligence_insights` filtered by `(client_id, insight_type, normalized_text)`
2. If row exists → PATCH `frequency_count = existing + 1` by `id`
3. If not → POST insert full row including `client_id`, `agent_id`, `source_type`, `source_record_id`

Returns list of saved/updated rows. Never raises — errors logged.

**Atomicity note (docstring):** The current read-then-write path is acceptable for internal/low-volume use. For higher-volume ingestion, replace with a single atomic upsert:
`ON CONFLICT (client_id, insight_type, normalized_text) DO UPDATE SET frequency_count = frequency_count + 1`.

---

## API Route: `app/routes/lead_intelligence_api.py`

### `POST /lead-intelligence/test-extract`

Internal endpoint. Extracts insights from raw text and saves them to the DB.

**Request (Pydantic model):**
```json
{
  "client_id":        "uuid",
  "agent_id":         "string | null",
  "source_type":      "whatsapp | call | chat",
  "source_record_id": "string | null",
  "text":             "raw conversation text"
}
```

**Response:**
```json
{
  "extracted": [...],
  "saved":     [...]
}
```

`extracted` = output of `extract_insights` (pre-save, for debugging extraction quality).
`saved` = output of `save_insights` (what was actually written to DB).

---

## Migration: `supabase/migrations/create_lead_intelligence_insights.sql`

Single SQL file. Contains:
- `CREATE TABLE` with all constraints
- Indexes
- `set_updated_at()` trigger function (if not already defined in DB)
- `BEFORE UPDATE` trigger on the table

Follows the same plain SQL file pattern as `add_client_id_to_leads.sql`.

---

## Files Changed

| File | Action |
|---|---|
| `supabase/migrations/create_lead_intelligence_insights.sql` | New |
| `app/services/lead_intelligence.py` | New |
| `app/routes/lead_intelligence_api.py` | New |
| `main.py` | Register new router |

**Zero changes to existing routes, services, or pipeline files.**

---

## Future Wiring Point

When ready to ingest from the live WhatsApp pipeline, the clean hook is in
`app/services/whatsapp_reply.py` → `_generate_whatsapp_reply_inner()`, after step 6
(history persisted via `append_whatsapp_messages`). Call `save_insights` there,
non-blocking, wrapped in try/except, never raising.

---

## What This Does NOT Include

- Dashboard UI page
- OpenAI-based extraction
- Live pipeline wiring
- RLS policies
- Publishing, FAQ generation, or content creation
- Any changes to leads / calls / agents flows
