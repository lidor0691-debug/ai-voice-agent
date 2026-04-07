# Client Assets & WhatsApp Delivery — Design Spec

**Date:** 2026-04-07  
**Status:** Approved  
**Approach:** B — Backend as data/trigger layer, Make.com as delivery layer

---

## 1. Problem

The system needs a structured way to associate assets (text messages, links, PDFs, images, videos) with clients, and trigger sending them via WhatsApp when key events occur (trial booked, payment requested, lead qualified, etc.).

**Constraints:**
- Assets must be client-scoped, not agent-scoped
- Prompts must NOT contain links or documents — prompts decide *when* to trigger, assets table owns *what* to send
- Do not break the existing voice system
- Do not introduce a queue or backend-direct WhatsApp sending

---

## 2. Architecture Overview

```
[Voice call end]                [External system / Make]
       │                                  │
       │  lead webhook to Make            │  direct POST
       ▼                                  ▼
  Make.com scenario ──── POST /assets/trigger ────► FastAPI
                                                        │
                                              fetch client_assets
                                              (by client_id + trigger_key)
                                                        │
                                              return assets[]  + context
                                                        │
                                    ◄───────────────────┘
                         Make iterates assets[]
                                │
                    ┌───────────┼───────────┐
                  text/link    pdf        image/video
                    │           │              │
              WA message    WA media       WA media
```

**Separation of concerns:**
- Backend: source of truth for client assets, trigger resolution
- Make.com: WhatsApp delivery, template substitution, ordering
- Prompts: signal trigger intent only — no links, no documents

---

## 3. Data Model

### 3.1 New: `clients` table

```sql
CREATE TABLE clients (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT NOT NULL,
  metadata   JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 3.2 Update: `agents_config`

```sql
ALTER TABLE agents_config
  ADD COLUMN client_id UUID REFERENCES clients(id),
  ADD COLUMN channel   TEXT DEFAULT 'voice'
    CHECK (channel IN ('voice', 'whatsapp'));
```

### 3.3 Bootstrap migration (run once)

For each existing `agents_config` row that has no `client_id`, create a corresponding `clients` row and back-fill the FK. This creates a 1:1 client-per-agent starting point. Clients can be merged later when one business owns multiple agents.

```sql
-- Step 1: insert one client per agent (no client_id yet)
INSERT INTO clients (id, name)
SELECT gen_random_uuid(), COALESCE(business_name, agent_name, 'Unknown')
FROM agents_config
WHERE client_id IS NULL;

-- Step 2: back-fill client_id on agents_config
-- (done via a scripted migration that matches by insertion order or name;
--  see implementation plan for the exact script)
```

### 3.4 New: `client_assets` table

```sql
CREATE TABLE client_assets (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  asset_name  TEXT NOT NULL,
  asset_type  TEXT NOT NULL
    CHECK (asset_type IN ('text', 'link', 'pdf', 'image', 'video')),
  trigger_key TEXT NOT NULL,
  content     TEXT NOT NULL,   -- message template OR URL
  enabled     BOOLEAN NOT NULL DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_client_assets_client_id   ON client_assets(client_id);
CREATE INDEX idx_client_assets_trigger_key ON client_assets(trigger_key);
CREATE INDEX idx_client_assets_lookup      ON client_assets(client_id, trigger_key, enabled);
```

**`trigger_key` convention:**
- lowercase only
- underscore-separated words
- examples: `trial_booked`, `payment_request`, `general_followup`, `lead_qualified`
- a `sort_order` column can be added later if per-asset ordering is needed beyond `created_at`

---

## 4. Backend

### 4.1 `app/services/client_assets.py` (new file)

```python
async def get_assets_by_trigger(client_id: str, trigger_key: str) -> list[dict]:
    """
    Returns all enabled assets for client_id + trigger_key, ordered by created_at ASC.
    Returns [] on any error — never raises, never blocks the caller.
    """
```

- Uses `httpx` + Supabase REST (same pattern as `agent_config.py`)
- Filters: `client_id=eq.{client_id}&trigger_key=eq.{trigger_key}&enabled=eq.true&order=created_at.asc`
- Logs:
  ```
  [ASSETS] Trigger 'trial_booked' → 3 assets found for client {client_id}
  [ASSETS] Trigger 'trial_booked' → 0 assets (no match or Supabase not configured)
  ```
- If Supabase not configured → logs warning, returns `[]`
- If network error → logs error, returns `[]`

### 4.2 `app/routes/assets.py` (new file)

```
POST /assets/trigger
```

**Request body:**

```json
{
  "client_id": "uuid",            // required
  "trigger_key": "trial_booked",  // required, lowercase_underscore
  "trigger_source": "voice",      // optional: "voice" | "make" | "external"
  "context": {                    // optional, free-form
    "phone": "+972543033010",
    "name": "David"
  }
}
```

**Response (always 200):**

```json
{
  "client_id": "uuid",
  "trigger_key": "trial_booked",
  "trigger_source": "voice",
  "count": 2,
  "assets": [
    {
      "id": "uuid",
      "asset_name": "trial confirmation",
      "asset_type": "text",
      "content": "היי {{name}}! האימון הראשון שלך אושר."
    },
    {
      "id": "uuid",
      "asset_name": "payment link",
      "asset_type": "link",
      "content": "https://pay.example.com/trial/abc"
    }
  ],
  "context": { "phone": "+972543033010", "name": "David" }
}
```

- `count: 0` + `assets: []` is a valid result — not an error
- `context` is passed through unchanged — Make.com performs `{{name}}` substitution, not the backend
- Assets returned in `created_at ASC` order (deterministic, matches UI order)

**Registered in `main.py`:**
```python
from app.routes.assets import router as assets_router
app.include_router(assets_router, prefix="/assets")
```

### 4.3 `app/services/agent_config.py` — one-line addition

The returned dict from `fetch_supabase_agent_config` adds:
```python
"client_id": row.get("client_id", ""),
```
This makes `client_id` available in the lead webhook payload to Make, so Make can call `/assets/trigger` without an extra lookup.

---

## 5. Make.com Delivery Flow

### Trigger entry points

**Path A — External / Make-initiated event**  
Make scenario detects event (booking, form, CRM update) → calls `POST /assets/trigger` directly with `trigger_source: "make"`.

**Path B — Voice call end**  
Existing lead webhook fires to Make with call payload (now includes `client_id` from agent config). Make scenario calls `POST /assets/trigger` with `trigger_source: "voice"`.

Both paths hit the same endpoint. Same schema regardless of source.

### Make scenario structure

```
[Webhook or Watch trigger]
        │
        ▼
[HTTP module: POST /assets/trigger]
        │
        ▼  response: { assets: [...], context: {...} }
[Iterator: assets[]]  ← preserve backend order, do not re-sort
        │
        ├─ asset_type == "text"              → WhatsApp: Send Message
        │                                       body = asset.content (with {{name}} substitution from context)
        │
        ├─ asset_type == "link"              → WhatsApp: Send Message
        │                                       body = asset.content
        │
        └─ asset_type IN (pdf, image, video) → WhatsApp: Send Media Message
                                                media_url = asset.content
```

**Ordering:** Make must preserve the array order returned by the backend (`created_at ASC`). Do not sort or re-order inside the scenario.

**Error handling:** HTTP module on `/assets/trigger` should be set to "ignore errors" or "resume" — a 5xx from the backend should not kill the scenario, but should log.

**Sandbox:** Current WhatsApp sender may be in Twilio sandbox mode — acceptable for development/demo. Swap to production sender when going live.

---

## 6. Dashboard

### Page: `/dashboard/agents/[id]`

The existing page gains a **tab bar** at the top:

| Tab (Hebrew) | Content |
|---|---|
| הגדרות נציגה | Existing 6-step wizard — no changes |
| נכסי לקוח | New CRUD section (see below) |

Steps 1–6 of the wizard are untouched.

### Client Assets tab

**API routes (Next.js):**
```
GET    /api/clients/[client_id]/assets
POST   /api/clients/[client_id]/assets
PATCH  /api/clients/[client_id]/assets/[id]
DELETE /api/clients/[client_id]/assets/[id]
```
`client_id` is read from the agent row (already fetched by the page server component).

**Asset list:**
- Columns: asset name, type badge, trigger_key, enabled toggle, delete button
- Ordered by `created_at ASC` — matches backend order
- Enabled toggle fires inline PATCH on change

**Empty state:**
When no assets exist, show:
> "עדיין אין נכסים מוגדרים. הוסף נכס כדי להתחיל לשלוח הודעות אוטומטיות בוואטסאפ."
Primary "הוסף נכס" button below the message.

**Add asset inline form** (collapsed by default, opened by "הוסף נכס"):

| Field (Hebrew label) | Control |
|---|---|
| שם הנכס | Text input, required |
| סוג | Dropdown: טקסט / קישור / PDF / תמונה / וידאו |
| מפתח טריגר | Dropdown (trial_booked, payment_request, general_followup, lead_qualified) + free-text option |
| תוכן / URL | Textarea |
| פעיל | Toggle, default on |

Hint under trigger_key: `"lowercase, underscore-separated — e.g. trial_booked, payment_request"`

### TypeScript additions (`dashboard/types/database.ts`)

```ts
export interface Client {
  id: string;
  name: string;
  metadata: Json | null;
  created_at: string;
}

export interface ClientAsset {
  id: string;
  client_id: string;
  asset_name: string;
  asset_type: 'text' | 'link' | 'pdf' | 'image' | 'video';
  trigger_key: string;
  content: string;
  enabled: boolean;
  created_at: string;
}
```

`AgentConfig` interface gains:
```ts
client_id: string | null;
channel: 'voice' | 'whatsapp' | null;
```

---

## 7. Logging

Backend logs for every trigger resolution:

```
[ASSETS] Trigger 'trial_booked' → 2 assets found for client {client_id}
[ASSETS] Trigger 'payment_request' → 0 assets (no match)
[ASSETS] Supabase not configured — skipping asset lookup
[ASSETS] Error fetching assets for client {client_id}: {error}
```

---

## 8. Safety Rules

- `count: 0` is valid — Make does nothing, no error
- `/assets/trigger` never returns 4xx for "no assets found"
- `get_assets_by_trigger` never raises — always returns a list
- Voice call flow is unaffected if this service errors (Supabase down, etc.)
- `voice_realtime.py` is not modified

---

## 9. Out of Scope

- Backend-direct WhatsApp sending (no Twilio/Meta API calls from Python)
- `{{name}}` template substitution in the backend
- Message queuing or retry infrastructure
- Multi-client merge UI (assets are 1:1 with agents at launch, mergeable later)
- `sort_order` column (use `created_at ASC` for now)
