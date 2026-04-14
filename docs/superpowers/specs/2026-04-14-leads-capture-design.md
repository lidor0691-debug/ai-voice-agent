# Leads Capture — Design Spec

**Date:** 2026-04-14
**Goal:** Single lead sink for voice and WhatsApp so no lead is lost. End-to-end from call/chat → Supabase → dashboard.

---

## 1. Data Layer

### `public.leads` table (Supabase)

```sql
CREATE TABLE IF NOT EXISTS public.leads (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  name        TEXT,
  phone       TEXT NOT NULL,
  source      TEXT NOT NULL CHECK (source IN ('voice', 'whatsapp')),
  service     TEXT,
  status      TEXT NOT NULL DEFAULT 'new',
  notes       TEXT,
  agent_id    UUID
);

ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_leads" ON public.leads FOR ALL USING (true) WITH CHECK (true);
```

**Notes:**
- `agent_id` has no FK — agents table may not exist in all deployments
- `status` values: `new` | `contacted` | `scheduled` | `closed`
- `service` = null is valid (WhatsApp first-message leads have no service yet)
- `name` = null is valid (WhatsApp first-message leads may have no name yet)

---

## 2. Backend Write Paths

### Shared function
**New file:** `app/services/lead_capture.py`

Single async function `save_lead(data: dict) -> None` used by both voice and WhatsApp.
Uses `SUPABASE_URL` + `SUPABASE_ANON_KEY` env vars (already present in the project).
Errors are logged but never raise — lead capture must not break existing flows.

### Voice → Supabase
**File:** `app/routes/voice.py`
**Trigger:** `lead.is_complete == True` (all questions answered, inside `gather_input`)
**Where:** After `enrich_lead(lead.to_dict())`, before `clear_session`

Data saved:
```python
{
    "name": enriched.get("name"),
    "phone": lead.phone_number,
    "source": "voice",
    "service": enriched.get("service"),
    "status": "new",
}
```

**Important:** `enrich_lead` currently sets `source = "phone_call"` — we do NOT pass that to Supabase. We hardcode `"voice"` in `lead_capture.py`.

### WhatsApp → Supabase
**File:** `app/services/whatsapp_reply.py`
**Trigger:** First message from customer — `row is None` after `_load_row(customer_phone)`
**Where:** Step 3, right after the `row = await _load_row(customer_phone)` line

Data saved:
```python
{
    "phone": customer_phone,
    "source": "whatsapp",
    "status": "new",
}
```

No name/service — those are unknown at first contact. Can be enriched later.

---

## 3. Dashboard — Leads Page

### Existing components we REUSE (no changes needed)
- `LeadDetailPanel` — slide-over panel already exists and works perfectly
- `StatCard` — stat card component already exists
- `LeadsTable` — table component already exists

### New `Lead` type for Supabase leads
The existing `Lead` type in `dashboard/types/lead.ts` is built for Google Sheets (has `model`, `intents`, `mileage`, `sms_sent`, `calendar_booked`).

We add a new type alongside it:
```ts
export interface SupabaseLead {
  id: string;
  created_at: string;
  name: string | null;
  phone: string;
  source: "voice" | "whatsapp";
  service: string | null;
  status: string;
  notes: string | null;
  agent_id: string | null;
}
```

### API Route
**New file:** `dashboard/app/api/leads/route.ts`

Reads from Supabase `public.leads`, returns:
```ts
{
  leads: SupabaseLead[],  // sorted by created_at DESC
  stats: {
    total: number,
    today: number,
    new: number,       // status = 'new'
    contacted: number, // status = 'contacted'
    voice: number,
    whatsapp: number,
  }
}
```

Uses existing `dashboard/lib/supabase.ts` client directly.

### Leads Page UI

**File:** `dashboard/app/dashboard/leads/page.tsx` — replace Google Sheets fetch with `/api/leads`

**File:** `dashboard/app/dashboard/leads/LeadsClientPage.tsx` — replace with new component

New layout:
1. **Stats bar (row 1):** 4 `StatCard` components — סה"כ · היום · חדשים · בטיפול
2. **Source row (row 2):** 2 small inline badges — Voice N · WhatsApp N
3. **Table:** new `SupabaseLeadsTable` component (separate file)
4. **Slide-over:** reuse existing `LeadDetailPanel` — adapted to accept `SupabaseLead`

### New table component
**New file:** `dashboard/components/leads/supabase-leads-table.tsx`

Columns: שם · טלפון · מקור (badge) · שירות · סטטוס (badge) · תאריך
- Source badge: voice = blue, whatsapp = green
- Status badge: new = yellow, contacted = blue, scheduled = purple, closed = gray
- Search: name or phone
- Pagination: 50 rows
- Row click: opens `LeadDetailPanel`

**Why separate component:** existing `LeadsTable` is tightly coupled to the old `Lead` type with `model`, `intents`, `sms_sent` etc. Touching it risks breaking the dashboard home page which also uses it.

---

## 4. Files Changed

| File | Action | Notes |
|------|--------|-------|
| Supabase SQL | Migration | Create `public.leads` table |
| `app/services/lead_capture.py` | Create | Shared `save_lead()` function |
| `app/routes/voice.py` | Modify | Call `save_lead()` on complete |
| `app/services/whatsapp_reply.py` | Modify | Call `save_lead()` on first message |
| `dashboard/types/lead.ts` | Modify | Add `SupabaseLead` type |
| `dashboard/app/api/leads/route.ts` | Create | Supabase query + stats |
| `dashboard/app/dashboard/leads/page.tsx` | Modify | Fetch from `/api/leads` |
| `dashboard/app/dashboard/leads/LeadsClientPage.tsx` | Modify | New stats + table layout |
| `dashboard/components/leads/supabase-leads-table.tsx` | Create | New table for Supabase leads |

Total: 9 files. No other files touched.

---

## 5. What We Don't Touch

- Existing `LeadsTable` component (used on home dashboard)
- Existing `Lead` type (used by home dashboard)
- `app/integrations/google_sheets.py` (left intact, not removed)
- WhatsApp conversation flow logic
- Voice TwiML flow
- Any other dashboard page

---

## 6. Success Criteria

- Voice call completes → row in `public.leads` with `source=voice`, `status=new`
- WhatsApp first message → row in `public.leads` with `source=whatsapp`, `status=new`
- No duplicate rows on repeated WhatsApp messages from same phone
- `/dashboard/leads` shows stats bar + table with Supabase data
- Row click opens slide-over with lead details
- No existing flows broken (voice still works, WhatsApp still replies)
