# Client Assets & WhatsApp Delivery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a client-scoped asset system where trigger keys resolve structured assets (text, links, media) that Make.com delivers via WhatsApp — without touching the voice system.

**Architecture:** A new `clients` table sits above `agents_config` (1:1 at launch). A new `client_assets` table holds sendable assets keyed by `trigger_key`. A new `POST /assets/trigger` endpoint resolves and returns matching assets as JSON. Make.com calls this endpoint and handles WhatsApp delivery.

**Tech Stack:** FastAPI + httpx (backend), Supabase REST (data), Next.js App Router + TypeScript (dashboard), pytest + pytest-asyncio (tests), Make.com HTTP module (delivery)

---

## File Map

**New files (backend):**
- `app/services/client_assets.py` — Supabase query, returns assets by trigger
- `app/routes/assets.py` — `POST /assets/trigger` FastAPI route
- `tests/test_client_assets.py` — pytest unit tests for service + route

**New files (dashboard):**
- `dashboard/app/api/clients/[client_id]/assets/route.ts` — GET list + POST create
- `dashboard/app/api/clients/[client_id]/assets/[id]/route.ts` — PATCH + DELETE
- `dashboard/components/agents/agent-page-tabs.tsx` — tab bar client component
- `dashboard/components/agents/client-assets-tab.tsx` — Client Assets tab UI

**Modified files:**
- `dashboard/supabase/schema.sql` — append `clients`, `client_assets`, migrations
- `app/services/agent_config.py` — add `client_id` to returned dict (~line 304)
- `main.py` — register `/assets` router
- `dashboard/types/database.ts` — add `Client`, `ClientAsset`, extend `AgentConfig`
- `dashboard/app/dashboard/agents/[id]/page.tsx` — render `AgentPageTabs` instead of `AgentForm`
- `dashboard/app/api/agents/route.ts` — auto-create `clients` row on new agent

---

## Phase 1 — Database Migrations

**Risk: LOW** — all `ADD COLUMN IF NOT EXISTS`; existing data untouched until bootstrap step.

---

### Task 1: Create `clients` table and alter `agents_config`

**Files:**
- Modify: `dashboard/supabase/schema.sql`

- [ ] **Step 1: Append migration SQL to schema.sql**

Open `dashboard/supabase/schema.sql` and append at the bottom:

```sql
-- =============================================
-- Migration: clients table (multi-tenant root)
-- =============================================
create table if not exists public.clients (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  metadata   jsonb,
  created_at timestamptz not null default now()
);

alter table public.clients disable row level security;

-- =============================================
-- Migration: add client_id + channel to agents_config
-- =============================================
alter table public.agents_config
  add column if not exists client_id uuid references public.clients(id),
  add column if not exists channel   text default 'voice'
                                     check (channel in ('voice', 'whatsapp'));
```

- [ ] **Step 2: Run in Supabase SQL editor**

Copy the two SQL blocks above into the Supabase project SQL editor and click Run.

- [ ] **Step 3: Verify**

Run in SQL editor:
```sql
select column_name, data_type
from information_schema.columns
where table_name = 'agents_config'
  and column_name in ('client_id', 'channel');
```
Expected: 2 rows returned (`client_id uuid`, `channel text`).

---

### Task 2: Create `client_assets` table

**Files:**
- Modify: `dashboard/supabase/schema.sql`

- [ ] **Step 1: Append to schema.sql**

```sql
-- =============================================
-- Migration: client_assets table
-- =============================================
create table if not exists public.client_assets (
  id          uuid primary key default gen_random_uuid(),
  client_id   uuid not null references public.clients(id) on delete cascade,
  asset_name  text not null,
  asset_type  text not null check (asset_type in ('text', 'link', 'pdf', 'image', 'video')),
  trigger_key text not null,
  content     text not null,
  sort_order  int  not null default 0,
  enabled     boolean not null default true,
  created_at  timestamptz not null default now()
);

create index if not exists client_assets_client_id_idx
  on public.client_assets(client_id);

create index if not exists client_assets_trigger_key_idx
  on public.client_assets(trigger_key);

create index if not exists client_assets_lookup_idx
  on public.client_assets(client_id, trigger_key, enabled);

alter table public.client_assets disable row level security;
```

- [ ] **Step 2: Run in Supabase SQL editor**

- [ ] **Step 3: Verify**

```sql
select table_name from information_schema.tables
where table_schema = 'public' and table_name = 'client_assets';
```
Expected: 1 row.

---

### Task 3: Bootstrap migration — one client per existing agent

**Risk: MEDIUM** — modifies existing rows. Run only once. Verify row counts before and after.

**Files:**
- Modify: `dashboard/supabase/schema.sql`

- [ ] **Step 1: Check current agent count**

Run in SQL editor:
```sql
select count(*) from agents_config where client_id is null;
```
Note the number (e.g. 2). You will verify the same number of clients are created.

- [ ] **Step 2: Run bootstrap in SQL editor**

```sql
do $$
declare
  agent_row record;
  new_client_id uuid;
begin
  for agent_row in
    select id, coalesce(business_name, agent_name, 'Unknown') as client_name
    from public.agents_config
    where client_id is null
  loop
    insert into public.clients (name)
    values (agent_row.client_name)
    returning id into new_client_id;

    update public.agents_config
    set client_id = new_client_id
    where id = agent_row.id;
  end loop;
end $$;
```

- [ ] **Step 3: Verify bootstrap**

```sql
-- Should return 0 (no agents left without a client)
select count(*) from agents_config where client_id is null;

-- Should match the count from Step 1
select count(*) from clients;

-- Spot-check: each agent has a valid client
select a.agent_name, c.name as client_name
from agents_config a
join clients c on c.id = a.client_id;
```

- [ ] **Step 4: Append bootstrap note to schema.sql**

Append at the bottom of `dashboard/supabase/schema.sql`:

```sql
-- =============================================
-- Bootstrap: run once after clients table created
-- Creates one clients row per existing agent and back-fills client_id
-- (see do $$ block in implementation plan Task 3)
-- =============================================
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/supabase/schema.sql
git commit -m "feat(db): add clients, client_assets tables and bootstrap migration"
```

---

## Phase 2 — Backend Service + Endpoint

**Risk: LOW** — new files only; no existing files changed in this phase.

---

### Task 4: Backend service `app/services/client_assets.py`

**Files:**
- Create: `app/services/client_assets.py`
- Create: `tests/test_client_assets.py`

- [ ] **Step 1: Write the failing tests first**

Create `tests/test_client_assets.py`:

```python
"""
Tests for app/services/client_assets.py
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── service tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_empty_when_supabase_not_configured():
    from app.services.client_assets import get_assets_by_trigger
    with patch("app.services.client_assets._is_configured", return_value=False):
        result = await get_assets_by_trigger("client-123", "trial_booked")
    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_client_id_is_blank():
    from app.services.client_assets import get_assets_by_trigger
    with patch("app.services.client_assets._is_configured", return_value=True):
        result = await get_assets_by_trigger("", "trial_booked")
    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_trigger_key_is_blank():
    from app.services.client_assets import get_assets_by_trigger
    with patch("app.services.client_assets._is_configured", return_value=True):
        result = await get_assets_by_trigger("client-123", "")
    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_on_network_error():
    from app.services.client_assets import get_assets_by_trigger

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("app.services.client_assets._is_configured", return_value=True):
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_assets_by_trigger("client-123", "trial_booked")

    assert result == []


@pytest.mark.asyncio
async def test_returns_assets_list_on_success():
    from app.services.client_assets import get_assets_by_trigger

    mock_assets = [
        {"id": "a1", "asset_name": "confirm", "asset_type": "text",
         "content": "Hi!", "sort_order": 0, "enabled": True},
        {"id": "a2", "asset_name": "payment", "asset_type": "link",
         "content": "https://pay.example.com", "sort_order": 1, "enabled": True},
    ]

    mock_response = MagicMock()
    mock_response.json.return_value = mock_assets
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.client_assets._is_configured", return_value=True):
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_assets_by_trigger("client-123", "trial_booked")

    assert len(result) == 2
    assert result[0]["asset_name"] == "confirm"
    assert result[1]["asset_type"] == "link"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd c:/Users/lidor/maya-ai
pytest tests/test_client_assets.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'app.services.client_assets'`

- [ ] **Step 3: Create the service file**

Create `app/services/client_assets.py`:

```python
"""
app/services/client_assets.py
==============================
Supabase query service: resolve client_assets by trigger_key.

Public API
----------
get_assets_by_trigger(client_id, trigger_key) -> list[dict]
    Returns all enabled assets for a client + trigger, ordered by
    sort_order ASC, created_at ASC.  Never raises — returns [] on any failure.
"""

import os
import logging

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
_SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def _is_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_ANON_KEY)


def _headers() -> dict:
    return {
        "apikey":        _SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {_SUPABASE_ANON_KEY}",
        "Content-Type":  "application/json",
    }


async def get_assets_by_trigger(client_id: str, trigger_key: str) -> list[dict]:
    """
    Returns all enabled assets for client_id + trigger_key.
    Sorted by sort_order ASC, then created_at ASC.
    Returns [] on any error — never raises, never blocks the caller.
    """
    if not _is_configured():
        logger.warning("[ASSETS] Supabase not configured — skipping asset lookup")
        return []

    if not client_id or not trigger_key:
        logger.warning(
            "[ASSETS] get_assets_by_trigger called with empty client_id=%r or trigger_key=%r",
            client_id, trigger_key,
        )
        return []

    url = f"{_SUPABASE_URL}/rest/v1/client_assets"
    params = {
        "client_id":   f"eq.{client_id}",
        "trigger_key": f"eq.{trigger_key}",
        "enabled":     "eq.true",
        "order":       "sort_order.asc,created_at.asc",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params, headers=_headers())
            resp.raise_for_status()
            assets = resp.json()
            logger.info(
                "[ASSETS] Trigger '%s' → %d assets found for client %s",
                trigger_key, len(assets), client_id,
            )
            return assets
    except Exception as exc:
        logger.error(
            "[ASSETS] Error fetching assets for client %s: %s",
            client_id, exc,
        )
        return []
```

- [ ] **Step 4: Run tests — confirm all pass**

```bash
pytest tests/test_client_assets.py -v
```
Expected output:
```
PASSED tests/test_client_assets.py::test_returns_empty_when_supabase_not_configured
PASSED tests/test_client_assets.py::test_returns_empty_when_client_id_is_blank
PASSED tests/test_client_assets.py::test_returns_empty_when_trigger_key_is_blank
PASSED tests/test_client_assets.py::test_returns_empty_on_network_error
PASSED tests/test_client_assets.py::test_returns_assets_list_on_success
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add app/services/client_assets.py tests/test_client_assets.py
git commit -m "feat(assets): add client_assets service with trigger resolution"
```

---

### Task 5: Backend route `app/routes/assets.py`

**Files:**
- Create: `app/routes/assets.py`
- Modify: `tests/test_client_assets.py` (append route tests)

- [ ] **Step 1: Append route tests to test file**

Append to `tests/test_client_assets.py`:

```python
# ── route tests ───────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_test_client():
    from app.routes.assets import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_trigger_route_returns_200_with_empty_assets():
    with patch("app.routes.assets.get_assets_by_trigger", new=AsyncMock(return_value=[])):
        client = _make_test_client()
        resp = client.post("/trigger", json={
            "client_id":   "client-abc",
            "trigger_key": "trial_booked",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["assets"] == []
    assert body["client_id"] == "client-abc"
    assert body["trigger_key"] == "trial_booked"


def test_trigger_route_returns_assets_and_echoes_context():
    mock_assets = [
        {"id": "a1", "asset_name": "confirm", "asset_type": "text", "content": "Hi!"}
    ]
    with patch("app.routes.assets.get_assets_by_trigger", new=AsyncMock(return_value=mock_assets)):
        client = _make_test_client()
        resp = client.post("/trigger", json={
            "client_id":      "client-abc",
            "trigger_key":    "trial_booked",
            "trigger_source": "make",
            "event_id":       "evt-001",
            "context":        {"name": "David", "phone": "+972500000000"},
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["assets"][0]["asset_name"] == "confirm"
    assert body["trigger_source"] == "make"
    assert body["event_id"] == "evt-001"
    assert body["context"]["name"] == "David"


def test_trigger_route_requires_client_id():
    with patch("app.routes.assets.get_assets_by_trigger", new=AsyncMock(return_value=[])):
        client = _make_test_client()
        resp = client.post("/trigger", json={"trigger_key": "trial_booked"})
    assert resp.status_code == 422  # Pydantic validation error


def test_trigger_route_requires_trigger_key():
    with patch("app.routes.assets.get_assets_by_trigger", new=AsyncMock(return_value=[])):
        client = _make_test_client()
        resp = client.post("/trigger", json={"client_id": "client-abc"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run new tests — confirm they fail**

```bash
pytest tests/test_client_assets.py::test_trigger_route_returns_200_with_empty_assets -v
```
Expected: `ImportError` or `ModuleNotFoundError` for `app.routes.assets`

- [ ] **Step 3: Create the route file**

Create `app/routes/assets.py`:

```python
"""
app/routes/assets.py
====================
POST /assets/trigger — resolve client assets by trigger_key.

Returns a structured JSON payload of enabled assets for the given
client_id + trigger_key. Always 200 — count=0 is a valid empty result.
Make.com calls this endpoint and handles WhatsApp delivery.
"""

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.client_assets import get_assets_by_trigger

router = APIRouter()


class TriggerRequest(BaseModel):
    client_id:      str
    trigger_key:    str
    trigger_source: Optional[str] = None   # "voice" | "make" | "external"
    event_id:       Optional[str] = None   # caller-supplied idempotency key (echoed, not stored)
    context:        Optional[dict[str, Any]] = None  # free-form, passed through to response


@router.post("/trigger")
async def trigger_assets(req: TriggerRequest):
    """
    Resolve and return all enabled assets for a client + trigger key.
    Never 4xx for missing assets — count=0 means no assets configured.
    """
    assets = await get_assets_by_trigger(req.client_id, req.trigger_key)
    return {
        "client_id":      req.client_id,
        "trigger_key":    req.trigger_key,
        "trigger_source": req.trigger_source,
        "event_id":       req.event_id,
        "count":          len(assets),
        "assets":         assets,
        "context":        req.context or {},
    }
```

- [ ] **Step 4: Run all tests — confirm all pass**

```bash
pytest tests/test_client_assets.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add app/routes/assets.py tests/test_client_assets.py
git commit -m "feat(assets): add POST /assets/trigger route"
```

---

## Phase 3 — Backend Wiring

**Risk: LOW** — one line added to agent_config.py; one router registered in main.py.

---

### Task 6: Register `/assets` router in `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add router import and registration**

Edit `main.py` to match:

```python
from dotenv import load_dotenv
load_dotenv()  # must run before any os.getenv() calls in imported modules

from fastapi import FastAPI
from app.routes.voice_realtime import router as voice_ai_router
from app.routes.assets import router as assets_router

app = FastAPI()

app.include_router(voice_ai_router, prefix="/voice-ai")
app.include_router(assets_router, prefix="/assets")

@app.get("/")
def root():
    return {"status": "Maya AI Realtime is RUNNING"}

@app.get("/health")
def health():
    return {"ok": True}
```

- [ ] **Step 2: Start the dev server and verify the route exists**

```bash
uvicorn main:app --reload --port 8000
```

In a separate terminal:
```bash
curl -s -X POST http://localhost:8000/assets/trigger \
  -H "Content-Type: application/json" \
  -d '{"client_id":"test","trigger_key":"trial_booked"}' | python -m json.pp
```
Expected:
```json
{
  "client_id": "test",
  "trigger_key": "trial_booked",
  "trigger_source": null,
  "event_id": null,
  "count": 0,
  "assets": [],
  "context": {}
}
```
(0 assets because "test" is not a real client_id — that's correct.)

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat(assets): register /assets router in main.py"
```

---

### Task 7: Add `client_id` to `agent_config.py` return dict

**Files:**
- Modify: `app/services/agent_config.py` (line ~304, inside the return dict of `fetch_supabase_agent_config`)

- [ ] **Step 1: Add `client_id` to the return dict**

Find the return statement in `fetch_supabase_agent_config` (currently around line 304). Add `client_id` as the first field under `# Identity`:

```python
    return {
        # Identity
        "agent_id":              row.get("id", ""),
        "client_id":             row.get("client_id", ""),          # ← add this line
        "business_name":         business_name,
        "client_name":           agent_name,
        "assistant_name":        agent_name,
        # ... rest unchanged
    }
```

- [ ] **Step 2: Verify the server still starts**

```bash
uvicorn main:app --reload --port 8000
```
Expected: starts without error.

- [ ] **Step 3: Commit**

```bash
git add app/services/agent_config.py
git commit -m "feat(assets): expose client_id in agent_config returned dict"
```

---

## Phase 4 — Dashboard API Routes

**Risk: LOW** — new files following identical pattern to existing API routes.

---

### Task 8: TypeScript types

**Files:**
- Modify: `dashboard/types/database.ts`

- [ ] **Step 1: Add `Client` and `ClientAsset` interfaces, extend `AgentConfig`**

Edit `dashboard/types/database.ts`. After the existing imports at the top, add new interfaces:

```typescript
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
  sort_order: number;
  enabled: boolean;
  created_at: string;
}
```

In the `AgentConfig` interface, add two fields after `whatsapp_followup_template`:

```typescript
  // Multi-tenant
  client_id: string | null;
  channel: 'voice' | 'whatsapp' | null;
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/types/database.ts
git commit -m "feat(types): add Client, ClientAsset types; extend AgentConfig"
```

---

### Task 9: Dashboard API route — GET + POST assets

**Files:**
- Create: `dashboard/app/api/clients/[client_id]/assets/route.ts`

- [ ] **Step 1: Create the directory and file**

Create `dashboard/app/api/clients/[client_id]/assets/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { ClientAsset } from "@/types/database";

export async function GET(
  _: NextRequest,
  { params }: { params: Promise<{ client_id: string }> }
) {
  const { client_id } = await params;

  const { data, error } = await supabase
    .from("client_assets")
    .select("*")
    .eq("client_id", client_id)
    .order("sort_order", { ascending: true })
    .order("created_at", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ client_id: string }> }
) {
  const { client_id } = await params;
  const body = await req.json() as Omit<ClientAsset, "id" | "client_id" | "created_at">;

  const { data, error } = await supabase
    .from("client_assets")
    .insert({ ...body, client_id })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data, { status: 201 });
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors.

- [ ] **Step 3: Smoke-test GET with curl**

```bash
# Replace <client_id> with a real UUID from your clients table
curl -s http://localhost:3000/api/clients/<client_id>/assets
```
Expected: `[]` (empty array, no error).

- [ ] **Step 4: Commit**

```bash
git add dashboard/app/api/clients/
git commit -m "feat(api): add GET/POST /api/clients/[client_id]/assets"
```

---

### Task 10: Dashboard API route — PATCH + DELETE asset

**Files:**
- Create: `dashboard/app/api/clients/[client_id]/assets/[id]/route.ts`

- [ ] **Step 1: Create the file**

Create `dashboard/app/api/clients/[client_id]/assets/[id]/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { ClientAsset } from "@/types/database";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ client_id: string; id: string }> }
) {
  const { client_id, id } = await params;
  const body = await req.json() as Partial<ClientAsset>;

  const { data, error } = await supabase
    .from("client_assets")
    .update(body)
    .eq("id", id)
    .eq("client_id", client_id)   // ensure asset belongs to this client
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data);
}

export async function DELETE(
  _: NextRequest,
  { params }: { params: Promise<{ client_id: string; id: string }> }
) {
  const { client_id, id } = await params;

  const { error } = await supabase
    .from("client_assets")
    .delete()
    .eq("id", id)
    .eq("client_id", client_id);

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ success: true });
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/api/clients/
git commit -m "feat(api): add PATCH/DELETE /api/clients/[client_id]/assets/[id]"
```

---

### Task 11: Auto-create client on new agent

Ensure agents created after the bootstrap always get a `client_id`.

**Files:**
- Modify: `dashboard/app/api/agents/route.ts`

- [ ] **Step 1: Update POST handler to auto-create client**

Replace the `POST` function in `dashboard/app/api/agents/route.ts`:

```typescript
export async function POST(req: NextRequest) {
  const body = await req.json();

  // 1. Create a clients row for this new agent
  const clientName: string =
    (body.business_name as string | undefined) ||
    (body.agent_name as string | undefined) ||
    "Unknown";

  const { data: clientData, error: clientError } = await supabase
    .from("clients")
    .insert({ name: clientName })
    .select()
    .single();

  if (clientError) {
    return NextResponse.json({ error: clientError.message }, { status: 400 });
  }

  // 2. Create the agent with client_id set
  const { data, error } = await supabase
    .from("agents_config")
    .insert({ ...body, client_id: clientData.id })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data, { status: 201 });
}
```

The `GET` function is unchanged.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors.

- [ ] **Step 3: Create a test agent via the dashboard**

Start the dashboard (`npm run dev`), navigate to `/dashboard/agents/new`, create a new agent. Then verify in Supabase:
```sql
select a.agent_name, c.name as client_name, a.client_id
from agents_config a
left join clients c on c.id = a.client_id
order by a.created_at desc
limit 3;
```
Expected: the new agent has a non-null `client_id`.

- [ ] **Step 4: Commit**

```bash
git add dashboard/app/api/agents/route.ts
git commit -m "feat(api): auto-create clients row when creating a new agent"
```

---

## Phase 5 — Dashboard UI

**Risk: LOW for new component; MEDIUM for agent edit page (minimal change).** The wizard Steps 1–6 are not modified — only the page wrapper changes.

---

### Task 12: Tab bar wrapper component

**Files:**
- Create: `dashboard/components/agents/agent-page-tabs.tsx`

- [ ] **Step 1: Create the tab component**

Create `dashboard/components/agents/agent-page-tabs.tsx`:

```tsx
"use client";

import { useState } from "react";
import { AgentConfig } from "@/types/database";
import { AgentForm } from "./agent-form";
import { ClientAssetsTab } from "./client-assets-tab";

interface Props {
  agent: AgentConfig;
}

type Tab = "settings" | "assets";

export function AgentPageTabs({ agent }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("settings");

  return (
    <div className="flex-1 overflow-y-auto" dir="rtl">
      {/* Tab bar */}
      <div className="sticky top-0 z-20 bg-surface-0/95 backdrop-blur border-b border-border px-8">
        <div className="flex gap-1 pt-2">
          <button
            onClick={() => setActiveTab("settings")}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
              activeTab === "settings"
                ? "text-white border-brand-600 bg-surface-2"
                : "text-gray-500 border-transparent hover:text-gray-300"
            }`}
          >
            הגדרות נציגה
          </button>
          <button
            onClick={() => setActiveTab("assets")}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
              activeTab === "assets"
                ? "text-white border-brand-600 bg-surface-2"
                : "text-gray-500 border-transparent hover:text-gray-300"
            }`}
          >
            נכסי לקוח
          </button>
        </div>
      </div>

      {/* Tab content */}
      {activeTab === "settings" && (
        <AgentForm agentId={agent.id} initial={agent} />
      )}
      {activeTab === "assets" && (
        <ClientAssetsTab clientId={agent.client_id ?? ""} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Modify the agent edit page to use `AgentPageTabs`**

Replace the contents of `dashboard/app/dashboard/agents/[id]/page.tsx`:

```tsx
import { notFound } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { AgentConfig } from "@/types/database";
import { AgentPageTabs } from "@/components/agents/agent-page-tabs";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function EditAgentPage({ params }: Props) {
  const { id } = await params;

  const { data, error } = await supabase
    .from("agents_config")
    .select("*")
    .eq("id", id)
    .single();

  if (error || !data) notFound();

  const agent = data as AgentConfig;

  return <AgentPageTabs agent={agent} />;
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```
Expected: error about `ClientAssetsTab` not existing yet — this is expected; fix in Task 13.

- [ ] **Step 4: Create stub ClientAssetsTab to unblock compilation**

Create `dashboard/components/agents/client-assets-tab.tsx` with a stub (replace in Task 13):

```tsx
"use client";

export function ClientAssetsTab({ clientId }: { clientId: string }) {
  return (
    <div className="p-8">
      <p className="text-gray-500 text-sm">טוען נכסים…</p>
    </div>
  );
}
```

- [ ] **Step 5: Verify TypeScript compiles now**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors.

- [ ] **Step 6: Start dashboard, open an agent, verify tab bar appears**

```bash
cd dashboard && npm run dev
```
Navigate to `/dashboard/agents/<id>`. Verify:
- "הגדרות נציגה" tab shows the existing wizard
- "נכסי לקוח" tab shows "טוען נכסים…" placeholder

- [ ] **Step 7: Commit**

```bash
git add dashboard/components/agents/agent-page-tabs.tsx \
        dashboard/components/agents/client-assets-tab.tsx \
        dashboard/app/dashboard/agents/[id]/page.tsx
git commit -m "feat(ui): add agent page tab bar (settings / client assets)"
```

---

### Task 13: Client Assets tab — full implementation

**Files:**
- Modify: `dashboard/components/agents/client-assets-tab.tsx` (replace stub)

- [ ] **Step 1: Replace stub with full implementation**

Replace `dashboard/components/agents/client-assets-tab.tsx`:

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { ClientAsset } from "@/types/database";

const ASSET_TYPE_LABELS: Record<ClientAsset["asset_type"], string> = {
  text:  "טקסט",
  link:  "קישור",
  pdf:   "PDF",
  image: "תמונה",
  video: "וידאו",
};

const ASSET_TYPE_COLORS: Record<ClientAsset["asset_type"], string> = {
  text:  "bg-blue-500/20 text-blue-300",
  link:  "bg-purple-500/20 text-purple-300",
  pdf:   "bg-red-500/20 text-red-300",
  image: "bg-green-500/20 text-green-300",
  video: "bg-orange-500/20 text-orange-300",
};

const PRESET_TRIGGERS = [
  "trial_booked",
  "payment_request",
  "general_followup",
  "lead_qualified",
];

const EMPTY_FORM = {
  asset_name:  "",
  asset_type:  "text" as ClientAsset["asset_type"],
  trigger_key: "",
  content:     "",
  enabled:     true,
};

interface Props {
  clientId: string;
}

export function ClientAssetsTab({ clientId }: Props) {
  const [assets, setAssets]       = useState<ClientAsset[]>([]);
  const [loading, setLoading]     = useState(true);
  const [showForm, setShowForm]   = useState(false);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [form, setForm]           = useState(EMPTY_FORM);
  const [customTrigger, setCustomTrigger] = useState(false);

  const fetchAssets = useCallback(async () => {
    if (!clientId) { setLoading(false); return; }
    setLoading(true);
    try {
      const res = await fetch(`/api/clients/${clientId}/assets`);
      const data = await res.json();
      setAssets(Array.isArray(data) ? data : []);
    } catch {
      setAssets([]);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  const toggleEnabled = async (asset: ClientAsset) => {
    await fetch(`/api/clients/${clientId}/assets/${asset.id}`, {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ enabled: !asset.enabled }),
    });
    setAssets((prev) =>
      prev.map((a) => a.id === asset.id ? { ...a, enabled: !a.enabled } : a)
    );
  };

  const deleteAsset = async (asset: ClientAsset) => {
    if (!confirm(`למחוק את "${asset.asset_name}"?`)) return;
    await fetch(`/api/clients/${clientId}/assets/${asset.id}`, { method: "DELETE" });
    setAssets((prev) => prev.filter((a) => a.id !== asset.id));
  };

  const handleSubmit = async () => {
    if (!form.asset_name.trim()) { setError("יש להזין שם לנכס"); return; }
    if (!form.trigger_key.trim()) { setError("יש לבחור מפתח טריגר"); return; }
    if (!form.content.trim()) { setError("יש להזין תוכן או URL"); return; }

    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/clients/${clientId}/assets`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(form),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.error ?? "שמירה נכשלה");
      }
      const created = await res.json();
      setAssets((prev) => [...prev, created]);
      setForm(EMPTY_FORM);
      setShowForm(false);
      setCustomTrigger(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "שגיאה לא ידועה");
    } finally {
      setSaving(false);
    }
  };

  if (!clientId) {
    return (
      <div className="p-8 text-center">
        <p className="text-gray-500 text-sm">נכסי לקוח זמינים רק עבור נציגות קיימות.</p>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-2xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-white font-semibold text-base">נכסים לשליחה בוואטסאפ</h2>
          <p className="text-gray-500 text-sm mt-0.5">
            הגדר מה לשלוח אחרי כל טריגר — הודעות, קישורים, קבצים ומדיה
          </p>
        </div>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            + הוסף נכס
          </button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {/* Add asset form */}
      {showForm && (
        <div className="bg-surface-2 border border-border rounded-xl p-5 mb-6 space-y-4">
          <h3 className="text-white font-medium text-sm">נכס חדש</h3>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">שם הנכס *</label>
              <input
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                placeholder="לדוגמה: אישור ניסיון"
                value={form.asset_name}
                onChange={(e) => setForm((f) => ({ ...f, asset_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">סוג</label>
              <select
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-600"
                value={form.asset_type}
                onChange={(e) => setForm((f) => ({ ...f, asset_type: e.target.value as ClientAsset["asset_type"] }))}
              >
                <option value="text">טקסט</option>
                <option value="link">קישור</option>
                <option value="pdf">PDF</option>
                <option value="image">תמונה</option>
                <option value="video">וידאו</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">מפתח טריגר *</label>
            {!customTrigger ? (
              <select
                className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-600"
                value={form.trigger_key}
                onChange={(e) => {
                  if (e.target.value === "__custom__") {
                    setCustomTrigger(true);
                    setForm((f) => ({ ...f, trigger_key: "" }));
                  } else {
                    setForm((f) => ({ ...f, trigger_key: e.target.value }));
                  }
                }}
              >
                <option value="">-- בחר טריגר --</option>
                {PRESET_TRIGGERS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
                <option value="__custom__">אחר (הזן ידנית)</option>
              </select>
            ) : (
              <div className="flex gap-2">
                <input
                  className="flex-1 bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                  placeholder="trial_booked"
                  value={form.trigger_key}
                  onChange={(e) => setForm((f) => ({ ...f, trigger_key: e.target.value.toLowerCase().replace(/\s+/g, "_") }))}
                />
                <button
                  onClick={() => { setCustomTrigger(false); setForm((f) => ({ ...f, trigger_key: "" })); }}
                  className="px-3 py-2 text-xs text-gray-400 border border-border rounded-lg hover:text-white"
                >
                  חזור
                </button>
              </div>
            )}
            <p className="text-xs text-gray-600 mt-1">
              lowercase, underscore-separated — e.g. trial_booked, payment_request
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">
              {form.asset_type === "text" ? "תוכן ההודעה *" : "כתובת URL *"}
            </label>
            <textarea
              rows={3}
              className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 resize-none"
              placeholder={form.asset_type === "text"
                ? 'היי {{name}}! האימון הראשון שלך אושר.'
                : "https://example.com/file.pdf"}
              value={form.content}
              onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            />
          </div>

          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-400">פעיל</span>
            <div
              onClick={() => setForm((f) => ({ ...f, enabled: !f.enabled }))}
              className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${form.enabled ? "bg-brand-600" : "bg-surface-4"}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${form.enabled ? "translate-x-5" : "translate-x-0.5"}`} />
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {saving ? "שומר…" : "שמור נכס"}
            </button>
            <button
              onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setError(null); setCustomTrigger(false); }}
              className="px-4 py-2 text-sm text-gray-400 border border-border rounded-lg hover:text-white hover:bg-surface-3 transition-colors"
            >
              ביטול
            </button>
          </div>
        </div>
      )}

      {/* Asset list */}
      {loading ? (
        <p className="text-gray-600 text-sm text-center py-8">טוען נכסים…</p>
      ) : assets.length === 0 && !showForm ? (
        /* Empty state */
        <div className="text-center py-12 border border-dashed border-border rounded-xl">
          <p className="text-gray-500 text-sm leading-relaxed">
            עדיין אין נכסים מוגדרים.<br />
            הוסף נכס כדי להתחיל לשלוח הודעות אוטומטיות בוואטסאפ.
          </p>
          <button
            onClick={() => setShowForm(true)}
            className="mt-4 px-5 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            + הוסף נכס ראשון
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {assets.map((asset) => (
            <div
              key={asset.id}
              className="bg-surface-2 border border-border rounded-lg px-4 py-3 flex items-center gap-3"
            >
              {/* Type badge */}
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${ASSET_TYPE_COLORS[asset.asset_type]}`}>
                {ASSET_TYPE_LABELS[asset.asset_type]}
              </span>

              {/* Name + trigger */}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white font-medium truncate">{asset.asset_name}</p>
                <p className="text-xs text-gray-500 mt-0.5 font-mono">{asset.trigger_key}</p>
              </div>

              {/* Enabled toggle */}
              <div
                onClick={() => toggleEnabled(asset)}
                className={`relative shrink-0 w-10 h-5 rounded-full transition-colors cursor-pointer ${asset.enabled ? "bg-brand-600" : "bg-surface-4"}`}
              >
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${asset.enabled ? "translate-x-5" : "translate-x-0.5"}`} />
              </div>

              {/* Delete */}
              <button
                onClick={() => deleteAsset(asset)}
                className="text-gray-600 hover:text-red-400 transition-colors text-xs px-2 py-1 shrink-0"
              >
                מחק
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors.

- [ ] **Step 3: Smoke-test the full UI**

Start the dashboard. Navigate to `/dashboard/agents/<id>` → "נכסי לקוח" tab.
- Verify empty state shows with "הוסף נכס ראשון" button
- Click the button → form appears
- Add one asset (e.g. name: "test", type: text, trigger: trial_booked, content: "Hello!")
- Verify it appears in the list
- Toggle enabled off → verify toggle changes
- Delete it → verify list is empty again

- [ ] **Step 4: Commit**

```bash
git add dashboard/components/agents/client-assets-tab.tsx
git commit -m "feat(ui): implement Client Assets tab with full CRUD"
```

---

## Phase 6 — Make.com Scenario

**Risk: NONE** — configuration only; no code changes.

---

### Task 14: Make.com scenario setup

This task is a configuration guide, not code. No files are created.

**Pre-conditions:** Railway backend is deployed with the new `/assets` route (push all commits first).

- [ ] **Step 1: Deploy all backend changes to Railway**

```bash
git push origin main
```
Watch Railway deploy logs. Confirm `/assets/trigger` is reachable:
```bash
curl -s https://<your-railway-url>/assets/trigger \
  -X POST -H "Content-Type: application/json" \
  -d '{"client_id":"test","trigger_key":"trial_booked"}'
```
Expected: `{"count":0,"assets":[],...}`

- [ ] **Step 2: Add HTTP module to existing lead webhook scenario**

In Make.com, open the scenario that receives the post-call lead webhook.

After the existing lead processing step, add:

**Module:** HTTP → Make a request
```
URL:    https://<your-railway-url>/assets/trigger
Method: POST
Headers:
  Content-Type: application/json
Body (raw JSON):
  {
    "client_id":      "{{client_id}}",     ← from lead webhook payload
    "trigger_key":    "lead_qualified",    ← or map from call outcome
    "trigger_source": "voice",
    "context": {
      "name":  "{{lead_name}}",
      "phone": "{{caller_phone}}"
    }
  }
```
Set error handling: **Resume** (don't stop scenario on 5xx).

- [ ] **Step 3: Add Iterator over assets**

After the HTTP module, add:

**Module:** Flow Control → Iterator
```
Array: {{assets}}   ← from HTTP response body
```

- [ ] **Step 4: Add conditional routing for asset_type**

After the Iterator, add a **Router** with 3 paths:

**Path 1** (filter: `asset_type = text OR link`):
- Module: WhatsApp → Send a Message
- To: `{{context.phone}}`
- Message: `{{content}}`  (Make substitutes `{{name}}` from context automatically if mapped)

**Path 2** (filter: `asset_type = pdf`):
- Module: WhatsApp → Send a Document
- To: `{{context.phone}}`
- Document URL: `{{content}}`

**Path 3** (filter: `asset_type = image OR video`):
- Module: WhatsApp → Send Media
- To: `{{context.phone}}`
- Media URL: `{{content}}`

- [ ] **Step 5: Add delay between assets**

Between the Iterator and the Router, add:

**Module:** Flow Control → Sleep
```
Delay: 1 second
```

- [ ] **Step 6: Test with a real asset**

In the Supabase dashboard, insert a test asset:
```sql
insert into client_assets (client_id, asset_name, asset_type, trigger_key, content)
values (
  '<your-real-client-id>',
  'test message',
  'text',
  'lead_qualified',
  'היי {{name}}! קיבלנו את הפנייה שלך ונחזור אליך בקרוב.'
);
```

Trigger a test run in Make with that client's lead webhook payload.
Expected: WhatsApp message arrives on the test phone, log shows `count: 1`.

---

## Phase 7 — End-to-End Testing Checklist

**Risk: N/A** — verification only.

---

### Task 15: End-to-end verification

- [ ] **Backend: service layer**
  ```bash
  pytest tests/test_client_assets.py -v
  ```
  Expected: 9 passed, 0 failed.

- [ ] **Backend: route accessible**
  ```bash
  curl -s -X POST https://<railway-url>/assets/trigger \
    -H "Content-Type: application/json" \
    -d '{"client_id":"does-not-exist","trigger_key":"trial_booked"}'
  ```
  Expected: `{"count":0,"assets":[],"context":{}}` — no crash, no 4xx.

- [ ] **Backend: returns real assets**  
  Insert a test asset via Supabase dashboard (see Task 14 Step 6), then:
  ```bash
  curl -s -X POST https://<railway-url>/assets/trigger \
    -H "Content-Type: application/json" \
    -d "{\"client_id\":\"<real-client-id>\",\"trigger_key\":\"lead_qualified\"}"
  ```
  Expected: `count: 1`, `assets` array contains your test asset.

- [ ] **Backend: voice still works**  
  Make a test call. Confirm the call connects, Maya responds, lead is delivered. `voice_realtime.py` is unchanged — this should be green without any action.

- [ ] **Database: bootstrap complete**
  ```sql
  select count(*) from agents_config where client_id is null;
  ```
  Expected: `0`.

- [ ] **Dashboard: agent edit page**  
  Open `/dashboard/agents/<id>`. Verify:
  - "הגדרות נציגה" tab shows the 6-step wizard unchanged
  - "נכסי לקוח" tab shows empty state (or asset list if assets exist)

- [ ] **Dashboard: create asset**  
  In the "נכסי לקוח" tab:
  - Add an asset (type: text, trigger: trial_booked, content: "Hello!")
  - Verify it appears in the list immediately (no page refresh)

- [ ] **Dashboard: toggle + delete**  
  - Toggle enabled off → toggle changes to off
  - Delete the asset → list returns to empty state

- [ ] **Dashboard: new agent gets client_id**  
  Create a new agent via `/dashboard/agents/new`. In Supabase:
  ```sql
  select client_id from agents_config order by created_at desc limit 1;
  ```
  Expected: non-null UUID.

- [ ] **Make.com: end-to-end send**  
  With a real asset in Supabase and the Make scenario configured:
  - Manually trigger the Make scenario with a test payload containing a real `client_id` and `trigger_key: "lead_qualified"`
  - Verify: WhatsApp message received on test phone
  - Verify: Make execution log shows HTTP module returned `count: 1`
  - Verify: 1-second delay between messages if multiple assets exist

- [ ] **Make.com: empty trigger is a no-op**  
  Trigger the scenario with a `trigger_key` that has no assets configured.
  Expected: HTTP module returns `count: 0`, Iterator runs 0 times, no WhatsApp message sent, scenario completes without error.
