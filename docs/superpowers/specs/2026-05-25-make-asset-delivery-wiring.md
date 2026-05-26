# Make.com Asset Delivery — Wiring Spec

**Date:** 2026-05-25
**Status:** Spec only — not implemented. No code/DB/runtime changes.
**Scope:** Configure a Make.com scenario that fires asset triggers and delivers `client_assets` to the lead over Twilio WhatsApp. The backend endpoint already exists; this is pure Make.com wiring + configuration.

## Background (verified)

- Maya's runtime exposes a **pull** endpoint only: `POST /assets/trigger` ([app/routes/assets.py](../../app/routes/assets.py)) → `get_assets_by_trigger()` ([app/services/client_assets.py](../../app/services/client_assets.py)). It returns enabled `client_assets`; it does **not** send anything.
- Nothing in the voice/WhatsApp runtime fires asset triggers today. Delivery is Make.com's job (by design).
- Therefore Make must: (1) decide when an event happens, (2) call `/assets/trigger` with the right `client_id` + `trigger_key`, (3) send each returned asset over WhatsApp.

## 1. Endpoint and request body

**Endpoint:** `POST {BASE_URL}/assets/trigger`
`{BASE_URL}` = Maya backend public URL (the same host Twilio/Make already use; from the deployment's `BASE_URL`).

**Headers:** `Content-Type: application/json` (no auth header required by the route today — it is an internal/trusted endpoint; keep `{BASE_URL}` non-public or add network-level protection).

**Request body** (fields per `TriggerRequest` in [app/routes/assets.py](../../app/routes/assets.py)):
```json
{
  "client_id": "<clients.id UUID>",
  "trigger_key": "trial_booked",
  "trigger_source": "make",
  "event_id": "<optional idempotency key, echoed back>",
  "context": { "lead_phone": "+9725XXXXXXXX", "lead_name": "..." }
}
```
- `client_id` (**required**) — the Supabase **`clients.id` UUID** (NOT the runtime `client_name` like "Maya BPM"). See §6 for the gap.
- `trigger_key` (**required**) — one of the configured keys (§4).
- `trigger_source` — free string for tracing; use `"make"`.
- `event_id` — optional; pass a unique id for your own idempotency/dedup (echoed, not stored).
- `context` — free-form object, passed straight through to the response. Use it to carry the lead phone/name so the downstream WhatsApp module can read them from the same bundle.

## 2. Expected response shape

Always HTTP **200** (even with zero assets). Body:
```json
{
  "client_id": "<uuid>",
  "trigger_key": "trial_booked",
  "trigger_source": "make",
  "event_id": "<echoed or null>",
  "count": 2,
  "assets": [
    {
      "id": "<uuid>",
      "client_id": "<uuid>",
      "asset_name": "Intake form",
      "asset_type": "link",
      "trigger_key": "trial_booked",
      "content": "https://example.com/intake",
      "sort_order": 0,
      "enabled": true,
      "created_at": "..."
    }
  ],
  "context": { "lead_phone": "+9725XXXXXXXX" }
}
```
- `count` = number of enabled assets. `count: 0` is a valid empty result (§8).
- `assets[]` are pre-sorted by `sort_order` then `created_at`.
- `asset_type` ∈ `text | link | pdf | image | video`. (The wizard only creates `link`/`pdf`; the old Assets tab can create all five.)

## 3. Make scenario steps

```
[1] Trigger module (event source)
      e.g. Webhook from the lead flow, or a Router branch after the lead is created,
      or a Data Store watch — whatever signals "payment_request / trial_booked / lead_qualified".
        ▼
[2] (Optional) Resolve client_id   → see §6 (constant per scenario, or lookup by phone/client_name)
        ▼
[3] HTTP > Make a request
      Method: POST
      URL:    {BASE_URL}/assets/trigger
      Headers: Content-Type: application/json
      Body (raw JSON):
        { "client_id": "{{client_id}}", "trigger_key": "{{trigger_key}}",
          "trigger_source": "make", "event_id": "{{event_id}}",
          "context": { "lead_phone": "{{lead_phone}}" } }
      Parse response: Yes (JSON)
        ▼
[4] Router / Filter on {{count}}
      ├─ count = 0  → stop branch / log "no assets" (§8)
      └─ count > 0  → continue
        ▼
[5] Iterator over {{assets[]}}
        ▼
[6] Router by {{item.asset_type}}
      ├─ text         → Twilio: Send WhatsApp, Body = {{item.content}}
      ├─ link         → Twilio: Send WhatsApp, Body = "{{item.asset_name}}: {{item.content}}"
      └─ pdf/image/video → Twilio: Send WhatsApp, MediaUrl = {{item.content}} (+ optional Body caption)
        ▼
[7] (Optional) Error handler / log per send (§8)
```

## 4. Mapping `trigger_key` values

`trigger_key` is a free-text string; the agreed presets (from the dashboard UI) are:

| Business event | `trigger_key` to send |
|---|---|
| Trial / appointment booked | `trial_booked` |
| Payment / deposit requested | `payment_request` |
| Generic follow-up nudge | `general_followup` |
| Lead qualified / handoff-ready | `lead_qualified` |

Rules:
- The `trigger_key` Make sends **must exactly match** the `trigger_key` saved on the asset (case-sensitive, snake_case). Mismatch ⇒ `count: 0` ⇒ nothing sent.
- Where the event originates determines the key: map each Make trigger branch to exactly one `trigger_key` constant.
- Custom triggers are allowed — any string the admin set on an asset works, as long as Make sends the identical value.

## 5. Sending each asset type over Twilio WhatsApp

Use the **Twilio > Send a WhatsApp message** module (or "Send a Message" with WhatsApp from/to). Per `asset_type`:

| `asset_type` | Twilio field mapping |
|---|---|
| `text` | `Body` = `{{item.content}}` |
| `link` | `Body` = `"{{item.asset_name}}: {{item.content}}"` (URL inline; WhatsApp auto-previews) |
| `pdf` | `MediaUrl` = `{{item.content}}` (must be a public HTTPS URL Twilio can fetch); optional `Body` caption = `{{item.asset_name}}` |
| `image` | `MediaUrl` = `{{item.content}}`; optional `Body` caption |
| `video` | `MediaUrl` = `{{item.content}}`; optional `Body` caption |

Constraints:
- `To` = `whatsapp:{{lead_phone}}` (E.164). `From` = your Twilio WhatsApp sender (`whatsapp:+...`).
- Media (`pdf/image/video`) requires a **publicly reachable HTTPS URL** and a Twilio-supported MIME/size. Private links won't render — send them as `link` text instead.
- WhatsApp 24-hour session rules apply: outside an open session you must use an approved **template**; inside it, free-form is fine. Booking/payment follow-ups often fall outside the window → plan a template for those `trigger_key`s.

## 6. Data Make needs from the existing lead flow

The current studio lead webhook payload (`_build_studio_payload` in [app/routes/voice_realtime.py](../../app/routes/voice_realtime.py)) provides:
- `parent_phone` / `followup_target_phone` → use as the WhatsApp **destination** (`lead_phone`).
- `parent_name`, `service_type`, `trial1_status`, etc. → optional context.

**Gap to resolve (important):** the lead payload does **NOT** include the Supabase `clients.id` UUID. The runtime keys clients by `client_name` ("Maya BPM"), which is *not* the `clients.id` that `client_assets` is filtered by. So Make must obtain `client_id` itself, by one of:
- **(a) Per-scenario constant (simplest):** if a scenario serves one business, hard-code that business's `clients.id` UUID in step [2]. Recommended for the first rollout.
- **(b) Lookup:** add a Make step querying Supabase `clients` (by name/phone) to resolve the UUID. More general, more moving parts.
- **(c) Future, needs code (out of scope):** include `client_id` in the lead webhook payload — a runtime change, explicitly deferred.

Until (c), use (a) or (b). Do not assume the lead payload carries `client_id`.

## 7. Safe test procedure (fake asset)

1. In `/admin/client-setup` (or the old Assets tab), on a **disposable/staging** client, add one asset:
   `asset_name = "__TEST__ welcome"`, `asset_type = link`, `trigger_key = trial_booked`, `content = https://example.com/test`, enabled = on.
2. Note that client's `clients.id` UUID (Supabase Table Editor).
3. Manually call the endpoint (no Make yet) to confirm retrieval — e.g. from your machine:
   `POST {BASE_URL}/assets/trigger` body `{ "client_id": "<uuid>", "trigger_key": "trial_booked", "trigger_source": "make" }` → expect `count: 1` and your asset in `assets[]`.
4. Build the Make scenario (§3) with `To` set to **your own** WhatsApp number (not a real lead). Run once.
5. Confirm you receive the WhatsApp message. Check Twilio logs for delivery status.
6. Flip the asset `enabled = off` (old tab toggle) → re-run → expect `count: 0` and no message (validates the enabled filter).
7. Clean up the test asset (old Assets tab delete, or `delete from client_assets where asset_name like '\_\_TEST\_\_%'`). Keep this on staging only.

## 8. Failure handling

- **`count: 0`** (no matching/enabled assets): expected, not an error. Filter on `count > 0` before the Iterator; on the zero branch, just stop or log — never error the scenario, never message the lead.
- **HTTP error from `/assets/trigger`** (5xx/timeout — the service itself returns `[]`/200 on its own internal errors, so this is mainly network/host down): add Make error handling (retry with backoff a couple of times, then log/alert). Do not block the rest of the lead flow.
- **Per-asset Twilio send failure** (bad media URL, template/session rejection): handle inside the Iterator with a Make error handler — log the failing `asset_id`, continue to the next asset (don't abort the whole batch). Mirrors the backend's "partial success" philosophy.
- **Idempotency:** pass a unique `event_id` and/or guard in Make (Data Store of sent `event_id`s) so a re-run doesn't double-send.

## Out of scope / non-goals
Voice-runtime changes, adding `client_id` to the lead payload, auto-firing triggers from Maya, any backend code, DB writes, or commits. This spec is configuration guidance for Make.com only.
```