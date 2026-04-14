# Leads Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save every voice and WhatsApp lead to `public.leads` in Supabase and display them in the dashboard.

**Architecture:** A shared Python function `save_lead()` is called by voice and WhatsApp flows. The dashboard reads directly from Supabase via a Next.js API route. The existing Google Sheets integration and all existing flows are untouched.

**Tech Stack:** Python (httpx, already in use), Next.js App Router, Supabase (REST API on backend, JS client on frontend), shadcn/ui components

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| Supabase SQL | Migration | Create `public.leads` table |
| `app/services/lead_capture.py` | Create | Shared async `save_lead(data)` — only file that writes to `public.leads` |
| `app/routes/voice.py` | Modify | Call `save_lead()` when voice lead is complete |
| `app/services/whatsapp_reply.py` | Modify | Call `save_lead()` on first WhatsApp message from a phone |
| `dashboard/types/lead.ts` | Modify | Add `SupabaseLead` and `LeadsStats` types |
| `dashboard/app/api/leads/route.ts` | Replace | Query Supabase `public.leads` directly, return leads + stats |
| `dashboard/app/dashboard/leads/page.tsx` | Modify | Fetch from `/api/leads`, pass to new client component |
| `dashboard/app/dashboard/leads/LeadsClientPage.tsx` | Replace | Stats bar + source badges + table |
| `dashboard/components/leads/supabase-leads-table.tsx` | Create | Table for `SupabaseLead[]` with slide-over |

---

## Task 1: Create `public.leads` table in Supabase

**Files:**
- No code files — Supabase SQL only

- [ ] **Step 1: Apply migration via Supabase MCP or dashboard SQL editor**

Run this SQL:

```sql
CREATE TABLE IF NOT EXISTS public.leads (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  name       TEXT,
  phone      TEXT NOT NULL,
  source     TEXT NOT NULL CHECK (source IN ('voice', 'whatsapp')),
  service    TEXT,
  status     TEXT NOT NULL DEFAULT 'new',
  notes      TEXT,
  agent_id   UUID
);

ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_leads" ON public.leads FOR ALL USING (true) WITH CHECK (true);
```

- [ ] **Step 2: Verify table exists**

Run in Supabase SQL editor:
```sql
SELECT id, phone, source, status, created_at FROM public.leads LIMIT 1;
```
Expected: empty result set, no error.

---

## Task 2: Create `app/services/lead_capture.py`

**Files:**
- Create: `app/services/lead_capture.py`

- [ ] **Step 1: Create the file**

```python
"""
app/services/lead_capture.py
=============================
Writes a lead row to public.leads in Supabase.

Used by:
  - app/routes/voice.py       (when voice lead is complete)
  - app/services/whatsapp_reply.py  (on first WhatsApp message)

Never raises — errors are logged so callers are not interrupted.
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
_TABLE = "leads"


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {_SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


async def save_lead(data: dict) -> None:
    """
    Insert a row into public.leads.

    Accepted keys (all optional except phone and source):
        phone   : str  — required
        source  : str  — required, 'voice' or 'whatsapp'
        name    : str  — optional
        service : str  — optional
        status  : str  — optional, defaults to 'new' via DB default
        notes   : str  — optional
        agent_id: str  — optional UUID

    Never raises. Errors are logged.
    """
    if not _SUPABASE_URL or not _SUPABASE_ANON_KEY:
        logger.warning("[LEAD CAPTURE] Supabase env vars not set — skipping lead save")
        return

    payload = {k: v for k, v in data.items() if v is not None}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                json=payload,
                headers=_headers(),
            )
            resp.raise_for_status()
        logger.info("[LEAD CAPTURE] Saved lead phone=%s source=%s", data.get("phone"), data.get("source"))
    except Exception as exc:
        logger.error("[LEAD CAPTURE] Failed to save lead: %s | data=%s", exc, data)
```

- [ ] **Step 2: Verify import works**

```bash
cd c:\Users\lidor\maya-ai
venv\Scripts\python -c "from app.services.lead_capture import save_lead; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/lead_capture.py
git commit -m "feat(leads): add shared save_lead() function"
```

---

## Task 3: Wire voice → Supabase

**Files:**
- Modify: `app/routes/voice.py`

- [ ] **Step 1: Add import at top of `app/routes/voice.py`**

After the existing imports, add:
```python
from app.services.lead_capture import save_lead
```

- [ ] **Step 2: Call `save_lead` inside `gather_input`**

Find this block in `gather_input` (around line 101):
```python
    if lead.is_complete:
        enriched = enrich_lead(lead.to_dict())

        # Fire-and-forget integrations (errors are logged, not raised)
        await send_lead_to_make(enriched)
        await send_sms(
```

Replace with:
```python
    if lead.is_complete:
        enriched = enrich_lead(lead.to_dict())

        # Fire-and-forget integrations (errors are logged, not raised)
        await send_lead_to_make(enriched)
        await save_lead({
            "name": enriched.get("name"),
            "phone": lead.phone_number,
            "source": "voice",
            "service": enriched.get("service"),
            "status": "new",
        })
        await send_sms(
```

- [ ] **Step 3: Verify import resolves**

```bash
cd c:\Users\lidor\maya-ai
venv\Scripts\python -c "
from dotenv import load_dotenv; load_dotenv()
from app.routes.voice import router
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/routes/voice.py
git commit -m "feat(leads): save voice lead to Supabase on call complete"
```

---

## Task 4: Wire WhatsApp → Supabase

**Files:**
- Modify: `app/services/whatsapp_reply.py`

- [ ] **Step 1: Add import at top of `app/services/whatsapp_reply.py`**

After the existing imports, add:
```python
from app.services.lead_capture import save_lead
```

- [ ] **Step 2: Call `save_lead` on first message**

Find this block in `_generate_whatsapp_reply_inner` (around line 200):
```python
    # ── 3. Load history via customer_phone ────────────────────────────────────
    try:
        print("DEBUG history lookup using customer_phone:", repr(customer_phone), flush=True)
        row = await _load_row(customer_phone)
        history = _normalize_messages(row.get("messages_json") if row else None)
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP3_FAIL: {exc}"), "messages": []}
```

Replace with:
```python
    # ── 3. Load history via customer_phone ────────────────────────────────────
    try:
        print("DEBUG history lookup using customer_phone:", repr(customer_phone), flush=True)
        row = await _load_row(customer_phone)
        history = _normalize_messages(row.get("messages_json") if row else None)
        # First message from this phone — save as a new lead
        if row is None:
            await save_lead({
                "phone": customer_phone,
                "source": "whatsapp",
                "status": "new",
            })
    except Exception as exc:
        return {"reply": strict_sanitize(f"DIAG_STEP3_FAIL: {exc}"), "messages": []}
```

- [ ] **Step 3: Verify import resolves**

```bash
cd c:\Users\lidor\maya-ai
venv\Scripts\python -c "
from dotenv import load_dotenv; load_dotenv()
from app.services.whatsapp_reply import generate_whatsapp_reply
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/services/whatsapp_reply.py
git commit -m "feat(leads): save WhatsApp lead to Supabase on first message"
```

---

## Task 5: Add `SupabaseLead` type to dashboard

**Files:**
- Modify: `dashboard/types/lead.ts`

- [ ] **Step 1: Append new types to `dashboard/types/lead.ts`**

Add at the end of the file (do not remove existing types):
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

export interface LeadsApiResponse {
  leads: SupabaseLead[];
  stats: {
    total: number;
    today: number;
    new: number;
    contacted: number;
    voice: number;
    whatsapp: number;
  };
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd c:\Users\lidor\maya-ai\dashboard
npx tsc --noEmit 2>&1 | head -20
```
Expected: no new errors related to `lead.ts`

- [ ] **Step 3: Commit**

```bash
git add dashboard/types/lead.ts
git commit -m "feat(leads): add SupabaseLead and LeadsApiResponse types"
```

---

## Task 6: Replace `/api/leads` route to query Supabase

**Files:**
- Replace: `dashboard/app/api/leads/route.ts`

- [ ] **Step 1: Rewrite `dashboard/app/api/leads/route.ts`**

```ts
import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import type { SupabaseLead, LeadsApiResponse } from "@/types/lead";

export async function GET(): Promise<NextResponse<LeadsApiResponse | { error: string }>> {
  const { data, error } = await supabase
    .from("leads")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(200);

  if (error) {
    console.error("[/api/leads] Supabase error:", error.message);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const leads = (data ?? []) as SupabaseLead[];

  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayISO = todayStart.toISOString();

  const stats = {
    total: leads.length,
    today: leads.filter((l) => l.created_at >= todayISO).length,
    new: leads.filter((l) => l.status === "new").length,
    contacted: leads.filter((l) => l.status === "contacted").length,
    voice: leads.filter((l) => l.source === "voice").length,
    whatsapp: leads.filter((l) => l.source === "whatsapp").length,
  };

  return NextResponse.json({ leads, stats });
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd c:\Users\lidor\maya-ai\dashboard
npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/api/leads/route.ts
git commit -m "feat(leads): replace API route to query Supabase directly"
```

---

## Task 7: Create `SupabaseLeadsTable` component

**Files:**
- Create: `dashboard/components/leads/supabase-leads-table.tsx`

- [ ] **Step 1: Create directory and file**

```bash
mkdir -p dashboard/components/leads
```

Create `dashboard/components/leads/supabase-leads-table.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Search, Phone, MessageSquare } from "lucide-react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { LeadDetailPanel } from "@/components/dashboard/lead-detail-panel";
import { formatDate } from "@/lib/utils";
import type { SupabaseLead } from "@/types/lead";

const STATUS_STYLES: Record<string, string> = {
  new:       "bg-yellow-100 text-yellow-800",
  contacted: "bg-blue-100 text-blue-800",
  scheduled: "bg-purple-100 text-purple-800",
  closed:    "bg-slate-100 text-slate-600",
};

const STATUS_LABELS: Record<string, string> = {
  new:       "חדש",
  contacted: "בטיפול",
  scheduled: "תור נקבע",
  closed:    "סגור",
};

const COLUMNS = ["שם", "טלפון", "מקור", "שירות", "סטטוס", "תאריך"];

interface Props {
  leads: SupabaseLead[];
}

export function SupabaseLeadsTable({ leads }: Props) {
  const [query, setQuery] = useState("");
  const [selectedLead, setSelectedLead] = useState<SupabaseLead | null>(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const filtered = leads.filter((l) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      (l.name ?? "").toLowerCase().includes(q) ||
      l.phone.includes(q)
    );
  });

  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  // Adapt SupabaseLead to the shape LeadDetailPanel expects
  const adaptedLead = selectedLead
    ? {
        id: selectedLead.id,
        name: selectedLead.name ?? "—",
        phone: selectedLead.phone,
        model: selectedLead.service ?? "—",
        intents: [],
        mileage: "",
        appointment_time: null,
        created_at: selectedLead.created_at,
        status: selectedLead.status,
        source: selectedLead.source,
        sms_sent: false,
        calendar_booked: false,
      }
    : null;

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-slate-800 font-semibold text-sm">כל הלידים</h2>
            <div className="relative">
              <Search className="absolute end-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setPage(0); }}
                placeholder="חיפוש שם או טלפון..."
                className="pe-9 ps-3 py-1.5 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 w-52"
              />
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {COLUMNS.map((col) => (
                    <th
                      key={col}
                      className="text-start text-xs font-medium text-slate-400 uppercase tracking-wider px-6 py-3 whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {paged.length === 0 ? (
                  <tr>
                    <td colSpan={COLUMNS.length} className="px-6 py-10 text-center text-slate-400 text-sm">
                      לא נמצאו לידים
                    </td>
                  </tr>
                ) : (
                  paged.map((lead) => (
                    <tr
                      key={lead.id}
                      onClick={() => setSelectedLead(lead)}
                      className="hover:bg-slate-50 transition-colors cursor-pointer group"
                    >
                      {/* Name */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-semibold text-xs flex-shrink-0">
                            {(lead.name ?? "?").charAt(0).toUpperCase()}
                          </div>
                          <span className="font-medium text-slate-900 group-hover:text-brand-600 transition-colors">
                            {lead.name ?? <span className="text-slate-400">—</span>}
                          </span>
                        </div>
                      </td>
                      {/* Phone */}
                      <td className="px-6 py-4 text-slate-500 font-mono text-xs">
                        {lead.phone}
                      </td>
                      {/* Source */}
                      <td className="px-6 py-4">
                        {lead.source === "voice" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            <Phone className="w-3 h-3" />
                            Voice
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            <MessageSquare className="w-3 h-3" />
                            WhatsApp
                          </span>
                        )}
                      </td>
                      {/* Service */}
                      <td className="px-6 py-4 text-slate-700">
                        {lead.service ?? <span className="text-slate-400">—</span>}
                      </td>
                      {/* Status */}
                      <td className="px-6 py-4">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[lead.status] ?? "bg-slate-100 text-slate-600"}`}>
                          {STATUS_LABELS[lead.status] ?? lead.status}
                        </span>
                      </td>
                      {/* Date */}
                      <td className="px-6 py-4 text-slate-400 text-xs whitespace-nowrap">
                        {formatDate(lead.created_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-6 py-3 border-t border-slate-100">
              <span className="text-xs text-slate-400">
                מציג {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} מתוך {filtered.length}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="px-3 py-1 text-xs rounded-md border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >
                  הקודם
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page === totalPages - 1}
                  className="px-3 py-1 text-xs rounded-md border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >
                  הבא
                </button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {adaptedLead && (
        <LeadDetailPanel
          lead={adaptedLead}
          onClose={() => setSelectedLead(null)}
        />
      )}
    </>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd c:\Users\lidor\maya-ai\dashboard
npx tsc --noEmit 2>&1 | head -30
```
Expected: no errors in new file

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/leads/supabase-leads-table.tsx
git commit -m "feat(leads): add SupabaseLeadsTable component"
```

---

## Task 8: Replace `LeadsClientPage` with stats + table

**Files:**
- Replace: `dashboard/app/dashboard/leads/LeadsClientPage.tsx`

- [ ] **Step 1: Rewrite `dashboard/app/dashboard/leads/LeadsClientPage.tsx`**

```tsx
"use client";

import { Users, CalendarDays, Sparkles, Clock } from "lucide-react";
import { Header } from "@/components/layout/header";
import { StatCard } from "@/components/dashboard/stat-card";
import { SupabaseLeadsTable } from "@/components/leads/supabase-leads-table";
import type { LeadsApiResponse } from "@/types/lead";

interface Props {
  data: LeadsApiResponse;
}

export function LeadsClientPage({ data }: Props) {
  const { leads, stats } = data;

  return (
    <>
      <Header title="לידים" subtitle={`${stats.total} לידים בסך הכל`} />
      <main className="flex-1 overflow-y-auto p-8 space-y-6" dir="rtl">

        {/* Stats Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="סה״כ לידים"
            value={stats.total}
            icon={Users}
            iconBg="bg-brand-50"
            iconColor="text-brand-600"
          />
          <StatCard
            title="היום"
            value={stats.today}
            icon={CalendarDays}
            iconBg="bg-green-50"
            iconColor="text-green-600"
          />
          <StatCard
            title="חדשים"
            value={stats.new}
            icon={Sparkles}
            iconBg="bg-yellow-50"
            iconColor="text-yellow-600"
          />
          <StatCard
            title="בטיפול"
            value={stats.contacted}
            icon={Clock}
            iconBg="bg-blue-50"
            iconColor="text-blue-600"
          />
        </div>

        {/* Source breakdown */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-medium">מקור:</span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            📞 Voice — {stats.voice}
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
            💬 WhatsApp — {stats.whatsapp}
          </span>
        </div>

        {/* Table */}
        <SupabaseLeadsTable leads={leads} />
      </main>
    </>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd c:\Users\lidor\maya-ai\dashboard
npx tsc --noEmit 2>&1 | head -30
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/dashboard/leads/LeadsClientPage.tsx
git commit -m "feat(leads): replace LeadsClientPage with stats + Supabase table"
```

---

## Task 9: Update leads `page.tsx` to use new API

**Files:**
- Modify: `dashboard/app/dashboard/leads/page.tsx`

- [ ] **Step 1: Rewrite `dashboard/app/dashboard/leads/page.tsx`**

```tsx
export const dynamic = "force-dynamic";

import { LeadsClientPage } from "./LeadsClientPage";
import type { LeadsApiResponse } from "@/types/lead";

const EMPTY: LeadsApiResponse = {
  leads: [],
  stats: { total: 0, today: 0, new: 0, contacted: 0, voice: 0, whatsapp: 0 },
};

export default async function LeadsPage() {
  let data: LeadsApiResponse = EMPTY;

  try {
    // Import directly to avoid HTTP round-trip in server component
    const { supabase } = await import("@/lib/supabase");

    const { data: rows, error } = await supabase
      .from("leads")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(200);

    if (error) throw error;

    const leads = rows ?? [];
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const todayISO = todayStart.toISOString();

    data = {
      leads,
      stats: {
        total: leads.length,
        today: leads.filter((l) => l.created_at >= todayISO).length,
        new: leads.filter((l) => l.status === "new").length,
        contacted: leads.filter((l) => l.status === "contacted").length,
        voice: leads.filter((l) => l.source === "voice").length,
        whatsapp: leads.filter((l) => l.source === "whatsapp").length,
      },
    };
  } catch (err) {
    console.error("[LeadsPage] Failed to fetch leads:", err);
  }

  return <LeadsClientPage data={data} />;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd c:\Users\lidor\maya-ai\dashboard
npx tsc --noEmit 2>&1 | head -30
```
Expected: no errors

- [ ] **Step 3: Start dev server and verify page loads**

```bash
cd c:\Users\lidor\maya-ai\dashboard
npm run dev
```

Open `http://localhost:3000/dashboard/leads`
Expected: page loads with stats bar (all zeros if no leads yet), empty table, no crash

- [ ] **Step 4: Commit**

```bash
git add dashboard/app/dashboard/leads/page.tsx
git commit -m "feat(leads): leads page reads from Supabase"
```

---

## Task 10: End-to-end smoke test

**Files:**
- No code changes — verification only

- [ ] **Step 1: Insert a test lead directly in Supabase**

Run in Supabase SQL editor:
```sql
INSERT INTO public.leads (phone, source, status, name, service)
VALUES ('+972500000001', 'voice', 'new', 'בדיקה בדיקה', 'test-service');

INSERT INTO public.leads (phone, source, status)
VALUES ('+972500000002', 'whatsapp', 'new');
```

- [ ] **Step 2: Verify dashboard shows the leads**

Open `http://localhost:3000/dashboard/leads`
Expected:
- Stats: סה"כ = 2, חדשים = 2, Voice = 1, WhatsApp = 1
- Table shows both rows
- Clicking a row opens the slide-over panel

- [ ] **Step 3: Clean up test leads**

```sql
DELETE FROM public.leads WHERE phone IN ('+972500000001', '+972500000002');
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git status
# Should be clean — if any uncommitted changes, commit them
git commit -m "feat(leads): end-to-end lead capture voice + whatsapp → Supabase → dashboard" --allow-empty
```

---

## Self-Review

**Spec coverage:**
- ✅ `public.leads` table with all required columns (Task 1)
- ✅ Voice write path (Task 3)
- ✅ WhatsApp write path (Task 4)
- ✅ No duplicate WhatsApp leads — `row is None` check only fires on first message
- ✅ Default status `new` — set via DB default AND in payload
- ✅ Stats bar: total / today / new / contacted (Task 8)
- ✅ Source breakdown: voice / whatsapp (Task 8)
- ✅ Table with all required columns (Task 7)
- ✅ Slide-over panel on row click (Task 7)
- ✅ Existing flows untouched — `save_lead` never raises
- ✅ `agent_id` column exists, nullable, no FK constraint

**Type consistency check:**
- `SupabaseLead` defined in Task 5, used in Tasks 6, 7, 8 ✅
- `LeadsApiResponse` defined in Task 5, used in Tasks 6, 8, 9 ✅
- `save_lead(data: dict)` defined in Task 2, called in Tasks 3, 4 ✅
- `adaptedLead` in Task 7 maps all fields `LeadDetailPanel` requires ✅
