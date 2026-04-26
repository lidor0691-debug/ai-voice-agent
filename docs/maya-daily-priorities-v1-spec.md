# Maya's Daily Priorities — V1 Technical & Product Spec

**Status:** Deployed & Live
**Version:** 1.0
**Date:** 2026-04-26
**Commits:** 4da5db8, f572666, e99cd45

---

## 1. What It Is

Maya's Daily Priorities is the first wedge product in the Conversion Leak Intelligence system.
It surfaces leads that are leaking through the funnel after capture, and gives the business
owner a daily triage list with one-tap action.

**Product surface:** Action Queue card on the main dashboard.
**Engine behind it:** Deterministic leak detection scan running daily via cron.

This is NOT:
- Autonomous messaging (user must approve every send)
- Predictive analytics
- A general playbook engine
- A CRM replacement

---

## 2. Architecture

```
Make.com cron (daily)
       |
       v
GET /api/action-queue/scan          (FastAPI, secret-protected)
       |
       v
leak_scanner.py                     (Python, deterministic)
  |-- _detect_noshow()
  |-- _detect_conversation_drop()
  |-- _save_signals()
  |-- _auto_resolve()
       |
       v
conversion_leak_signals             (Supabase table, RLS-protected)
       |
       v
GET /api/action-queue               (Next.js API route, auth-gated)
       |
       v
ActionQueueCard                     (Dashboard component)
  |-- [Act] -> ActionCard -> /api/actions/send-whatsapp -> Twilio
  |-- [Dismiss] -> PATCH /api/action-queue/:id
```

### File Map

| Layer | File | Purpose |
|-------|------|---------|
| DB | `supabase/migrations/create_conversion_leak_signals.sql` | Table + indexes + RLS |
| Service | `app/services/leak_scanner.py` | Detection logic + save + auto-resolve |
| Backend route | `app/routes/action_queue_api.py` | Cron trigger endpoint |
| Backend registration | `main.py` | Router include (2 lines) |
| Dashboard API | `dashboard/app/api/action-queue/route.ts` | Read open signals |
| Dashboard API | `dashboard/app/api/action-queue/[id]/route.ts` | Update signal status |
| Dashboard UI | `dashboard/components/dashboard/action-queue-card.tsx` | Action Queue card |
| Dashboard wiring | `dashboard/app/dashboard/DashboardClientPage.tsx` | Card placement |

---

## 3. Signals

### Signal 1: noshow_not_reactivated

| Attribute | Detail |
|-----------|--------|
| Trigger | `appointment_at` is 4h-14d in the past, status != closed, no customer activity after appointment |
| Detection | Deterministic: SQL filter + Python timestamp comparison |
| Data sources | `leads` (appointment_at, status, last_whatsapp_inbound_at) |
| LLM | None |
| Confidence | High — binary check (appointment existed, time passed, no follow-up) |
| False positive risk | Appointment rescheduled outside Maya (phone/in-person). Mitigated by 14-day staleness guard. |
| Suggested action | Hebrew template: "לא הגיע/ה לתור ב-{date} — שווה לשלוח הודעה לקביעה מחדש" |

### Signal 2: conversation_drop

| Attribute | Detail |
|-----------|--------|
| Trigger | Lead status new/contacted, last WhatsApp message is from customer (role=user), conversation updated_at >48h ago |
| Detection | Deterministic: parse messages_json, check last role + timestamp |
| Data sources | `leads` (status, phone), `whatsapp_conversations` (messages_json, updated_at) |
| LLM | None |
| Confidence | High for "customer sent, no reply" pattern. Uses updated_at as proxy since individual messages lack timestamps. |
| False positive risk | Customer contacted business via phone/in-person after WhatsApp. Mitigated by framing as "check this" not "do this." |
| Suggested action | "הלקוח/ה שלח/ה הודעה ולא קיבל/ה מענה — כדאי לחזור אליו/ה" |

### Deferred: high_intent_no_booking

Not implemented. Requires `metadata.customer_phone` on `lead_intelligence_insights` to link win_signals to specific leads. Planned for v2.

---

## 4. Database Schema

### Table: conversion_leak_signals

```sql
id              uuid        PK, gen_random_uuid()
created_at      timestamptz default now()
updated_at      timestamptz default now(), auto-trigger
client_id       uuid        FK -> clients(id), NOT NULL
lead_id         uuid        NOT NULL (no FK, loose reference)
lead_phone      text        NOT NULL
lead_name       text        nullable
signal_type     text        CHECK: noshow_not_reactivated | conversation_drop | high_intent_no_booking
detail          jsonb       signal-specific context
suggested_action text       Hebrew template string
status          text        CHECK: open | acted | dismissed | resolved
acted_at        timestamptz set on act/resolve
scan_date       date        default CURRENT_DATE (UTC)

UNIQUE (client_id, lead_id, signal_type, scan_date)  -- one signal per type per lead per day
```

### Indexes
- `(client_id, status)` — queue fetch
- `(client_id) WHERE status = 'open'` — partial index for dashboard reads

### RLS Policies
- `cls_admin_all` — role=admin sees all rows (SELECT, INSERT, UPDATE, DELETE)
- `cls_client_own` — client sees rows where client_id matches JWT user_metadata.client_id

Scanner writes via service key (bypasses RLS). Dashboard reads via anon key + JWT (respects RLS).

---

## 5. State Flow

```
Signal lifecycle:

  [detected by scan]
         |
         v
       OPEN  ----[user clicks דחה]----> DISMISSED (terminal)
         |
         |----[user clicks טפל]-------> ACTED (terminal for queue)
         |                                 |
         |                                 v
         |                          ActionCard shown
         |                          User sends or cancels
         |
         |----[lead status changes]---> RESOLVED (auto, next scan)
         |    (scheduled or closed)
```

- `open` — visible in Action Queue
- `acted` — user engaged, removed from queue, acted_at set
- `dismissed` — user reviewed and dismissed, removed from queue
- `resolved` — auto-resolved by scanner when lead progresses

---

## 6. API Contracts

### GET /api/action-queue/scan (FastAPI)

Trigger: Make.com daily cron
Auth: `X-Followup-Secret` header (reuses FOLLOWUP_SECRET env var)
Scope: clients listed in `LEAK_SCAN_CLIENTS` env var

Response:
```json
{
  "scanned_clients": 1,
  "signals_created": 3,
  "signals_resolved": 1,
  "scanned_at": "2026-04-26T04:00:00Z"
}
```

### GET /api/action-queue (Next.js)

Auth: Supabase JWT (auto via cookies)
Scoping: RLS + getUserContext (admin=all, client=own)

Response:
```json
{
  "signals": [
    {
      "id": "uuid",
      "created_at": "iso",
      "lead_id": "uuid",
      "lead_phone": "+972...",
      "lead_name": "שם" | null,
      "signal_type": "noshow_not_reactivated",
      "detail": { "appointment_at": "iso", "hours_since": 38, "lead_status": "new" },
      "suggested_action": "Hebrew text",
      "status": "open"
    }
  ],
  "count": 1
}
```

### PATCH /api/action-queue/:id (Next.js)

Auth: Supabase JWT
Body: `{ "status": "dismissed" | "acted" }`
Guards: only updates rows where current status = "open"

Response: `{ "ok": true }`

---

## 7. UI Flow

### Dashboard Placement

ActionQueueCard sits above the Lead Intelligence row on the main dashboard.
It is a client-side component (useEffect + fetch), not server-rendered.

### States

| State | Display |
|-------|---------|
| Loading | Spinner |
| Empty (0 signals) | "אין לידים שדורשים טיפול כרגע" + green checkmark |
| Signals exist | List of up to 5 signal cards, "+N נוספים" if more |

### Per-Signal Card

- Type badge with icon (CalendarX for noshow, MessageSquareOff for drop)
- Lead name (or masked phone if no name)
- Human-readable description with context from detail JSON
- Suggested action line
- [טפל] button — marks acted, removes from list, opens ActionCard
- [דחה] button — marks dismissed, removes from list

### [טפל] -> ActionCard Flow

1. Signal removed from queue (optimistic)
2. PATCH fires: status -> acted, acted_at -> now
3. ActionCard renders inline with prefilled: agent_id, lead_id, lead_name, message
4. User can: edit message, send (via existing Twilio flow), or cancel
5. No auto-send. Human approval required for every message.

---

## 8. Environment Variables

| Var | Where | Purpose |
|-----|-------|---------|
| `LEAK_SCAN_CLIENTS` | Railway (backend) | Comma-separated client UUIDs to scan |
| `FOLLOWUP_SECRET` | Railway (backend) | Shared secret for cron endpoints (existing) |
| `SUPABASE_URL` | Both | Existing |
| `SUPABASE_SERVICE_KEY` | Backend only | Existing, used by scanner (bypasses RLS) |

---

## 9. Limitations (Known & Accepted for V1)

1. **No per-message timestamps in WhatsApp.** Conversation drop uses `updated_at` as proxy.
2. **N+1 queries in conversation_drop detector.** Each lead triggers a separate conversation fetch. Fine at BPM scale.
3. **No revenue estimation.** Queue shows lead count only, not estimated value.
4. **No notification.** User must open dashboard to see signals.
5. **Signal 3 (high_intent) deferred.** Needs metadata pipeline change.
6. **No backfill scan on first open.** First scan runs on cron schedule only.
7. **24h WhatsApp window may be closed** when user tries to act on a signal. Handled by existing ActionCard window_closed state.

---

## 10. V2 Opportunities

| Feature | Effort | Value | Dependency |
|---------|--------|-------|------------|
| Signal 3: high_intent_no_booking | 2-3 days | High — intelligence differentiator | Add customer_phone to insight metadata |
| Auto-resolve celebration | 1 day | Trust building — "Maya helped recover this lead" | Needs first real resolved signal |
| Weekly summary card | 2 days | Retention metric — "X leaks detected, Y acted, Z recovered" | 30+ days of signal data |
| LLM-composed re-engagement messages | 2 days | Higher conversion on [טפל] sends | Conversation history context |
| Per-message timestamps in WhatsApp | 1 day | Improves conversation_drop accuracy | Change append_whatsapp_messages |
| Configurable thresholds per agent | 2 days | Different sales cycles per vertical | New config UI |
| Push notification for new signals | 2 days | Drive daily engagement without dashboard open | Web push or WhatsApp alert |
| Revenue attribution tracking | 1-2 weeks | Proves ROI — "Maya recovered ₪X" | Outcome data (deal values) |
| Funnel stage auto-progression | 2 weeks | Enables all signals to be more accurate | Conversation analysis |
| Leak pattern trends | 1 week | Strategic insight — "your #1 leak type is X" | 60+ days of signal data |

---

## 11. Validation Results (Pre-Launch Testing)

| Test | Result |
|------|--------|
| Detector query finds backdated noshow | Pass |
| Python filter (last_wa < appointment) | Pass |
| Signal insert | Pass |
| Duplicate prevention (same lead+type+day) | Pass |
| Auto-resolve (lead -> scheduled) | Pass |
| RLS: admin sees all signals | Pass |
| RLS: client sees own signals only | Pass |
| Dashboard empty state | Pass |
| Dashboard signal display | Pass |
| [דחה] removes signal + updates DB | Pass |
| [טפל] opens ActionCard prefilled | Pass |
| No auto-send on [טפל] | Pass |
| TypeScript build | Pass (zero errors) |
