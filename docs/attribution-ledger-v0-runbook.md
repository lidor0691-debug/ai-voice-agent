# Attribution Ledger v0 — Operator Runbook

Phase 2a spear tip. Single-touch WhatsApp attribution. BPM as v0 tenant.

## What this primitive does

When Maya sends a WhatsApp message and the recipient lead later books, the
ledger records: action → outcome → attribution edge with a recovered amount.
Goal: "Maya recovered ₪Y across N attributed bookings; M bookings were not
attributable to Maya."

## Architecture (one-line view)

```
WA reply  ─►  attribution_actions
                                      ┐
leads.status='booked' (trigger)  ─►   │  batch worker  ─►  attribution_edges
                                      ┘   (single-touch, 48h)
```

Three tables. One Postgres trigger. One Python service. One router with two
endpoints. No new infrastructure.

---

## Files

| File | What |
|---|---|
| `supabase/migrations/create_attribution_ledger.sql` | 3 tables + trigger function |
| `app/services/attribution.py` | Constants, action recording, batch worker, recovered-revenue read |
| `app/routes/attribution_api.py` | `POST /attribution/run-batch`, `GET /attribution/recovered` |
| `app/services/whatsapp_reply.py` | One `record_whatsapp_action()` call after history persist (step 6a) |
| `main.py` | Router registration |

## Economic constants (single source of truth)

In `app/services/attribution.py`:

```python
RECOVERED_AMOUNT_PER_BOOKING: float = 12000.0   # NIS per booked lead
ATTRIBUTION_WINDOW_HOURS: int = 48
```

Change here, redeploy, future attributions reflect the new value. Existing
edges are not rewritten — attribution snapshots at edge-write time.

---

## Operator tasks

### 1. Apply the migration

```bash
# Via Supabase Studio SQL editor or CLI:
psql $DATABASE_URL < supabase/migrations/create_attribution_ledger.sql
```

Verify three tables exist:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_name LIKE 'attribution_%';
-- expect: attribution_actions, attribution_outcomes, attribution_edges
```

Verify trigger exists:
```sql
SELECT tgname FROM pg_trigger WHERE tgname = 'trg_attribution_on_lead_booked';
```

### 2. Mark a lead as booked

The trigger fires on any `leads.status` transition into `'booked'`. Any path
works — Supabase Studio UI, dashboard write, SQL update, future endpoint.

```sql
UPDATE public.leads SET status = 'booked' WHERE id = '<lead-uuid>';
```

Verify outcome row appeared:
```sql
SELECT * FROM public.attribution_outcomes WHERE lead_id = '<lead-uuid>';
```

### 3. Run the batch worker

```bash
curl -X POST https://<your-railway-host>/attribution/run-batch
# → {"processed": N, "attributed": K, "unattributed": M}
```

Idempotent. Re-running is safe — outcomes that already have an edge are
skipped (UNIQUE on `attribution_edges.outcome_id`).

To run automatically: add a Make.com cron hitting this endpoint every
15 minutes (mirrors the existing `/followup/due` pattern).

### 4. Read recovered revenue

```bash
curl "https://<your-railway-host>/attribution/recovered?client_id=<client-uuid>"
# → {"recovered_total": 24000.0, "attributed_count": 2, "unattributed_count": 1}
```

Optional time filter:
```bash
curl "https://<your-railway-host>/attribution/recovered?client_id=<client-uuid>&since=2026-04-01T00:00:00Z"
```

### 5. Pair with an MRI scan

To compare actual recovered revenue against an MRI scan's forecast:

```sql
SELECT id, client_id, created_at, recoverable_monthly
FROM public.mri_scans WHERE id = '<scan-id>';
```

Then call `/attribution/recovered?client_id=<scan.client_id>&since=<scan.created_at>`.
Compare `recovered_total` from the response against `recoverable_monthly`
from the scan.

---

## End-to-end smoke test (BPM)

1. Send a WhatsApp through Maya to a BPM test lead (`+972524620550`).
   Verify a row in `attribution_actions` with `client_id=BPM`,
   `lead_id=<the lead>`, `channel='whatsapp'`.
2. Mark that lead as booked:
   `UPDATE leads SET status='booked' WHERE phone='+972524620550';`
3. Verify `attribution_outcomes` has a new row.
4. Run batch: `curl -X POST .../attribution/run-batch`.
5. Verify `attribution_edges` has a row with `action_id` populated and
   `attributed_amount = 12000`.
6. Read recovered: `curl ".../attribution/recovered?client_id=642d2881-..."`.
   Expect `recovered_total ≥ 12000`.

---

## What v0 explicitly does NOT do

| Capability | Status |
|---|---|
| Voice attribution | Deferred. WhatsApp only. |
| Multi-touch attribution | Deferred. Single-touch latest-in-window. |
| Per-client recovered amount | Deferred. Hardcoded constant. |
| Per-client window override | Deferred. Hardcoded 48h. |
| Re-attribution as model improves | Deferred. UNIQUE outcome_id prevents duplicate edges. |
| Confidence / proof source fields | Deferred. |
| Outcome states beyond `booked` | Deferred. No `showed`, `paid`. |
| Auto-detection of bookings from message text | Deferred. Manual status flip only. |
| Counterfactual baseline / probability adjustment | Deferred. |
| RLS on attribution tables | Deferred. Service-key writes only; no dashboard reads in v0. |

## Upgrade paths (not now, but when needed)

| Need | Change |
|---|---|
| Second client with different recovered amount | Replace `RECOVERED_AMOUNT_PER_BOOKING` constant with a lookup against `clients.metadata->>'recovered_amount_per_booking'` (or add `attribution_config` table). ~10 min. |
| Voice attribution | Add `record_voice_action()` to `attribution.py`, wire into voice routes. Reuse same tables. |
| Multi-touch | Add `recovered_amount` column to `attribution_outcomes`, allow multiple edges per outcome (drop UNIQUE), add `attribution_weight` column to edges. |
| Dashboard reads attribution tables | Add RLS policies matching `mri_scans` pattern (admin-all + client-own + service-key bypass). |
