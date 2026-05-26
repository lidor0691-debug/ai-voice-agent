# Make.com Asset Delivery — Build & Test Checklist

**Date:** 2026-05-25
**Companion to:** [../specs/2026-05-25-make-asset-delivery-wiring.md](../specs/2026-05-25-make-asset-delivery-wiring.md)
**Status:** Configuration checklist only — no code, no DB writes, no commit.

> ⚠️ **The `client_id` gap (read first).** The existing lead webhook payload
> (`_build_studio_payload` in `app/routes/voice_realtime.py`) does **NOT** contain the
> Supabase `clients.id` UUID. The runtime identifies clients by `client_name` (e.g. "Maya BPM"),
> which is *not* the `clients.id` that `client_assets` is filtered by. `/assets/trigger` needs
> the UUID.
>
> **Recommended temporary solution:** **hard-code the `clients.id` UUID per business** as a
> constant inside each Make scenario (one scenario per business). Do this until/unless
> `client_id` is added to the lead payload later (a deferred runtime change). Do NOT assume the
> lead webhook carries `client_id`.

---

## A. Prerequisites
- [ ] You have the Maya backend public base URL (`{BASE_URL}`).
- [ ] You have a working Twilio WhatsApp sender number (`whatsapp:+...`) connected in Make.
- [ ] You can read the Supabase `clients` table (Table Editor) to copy a business's `clients.id` UUID.
- [ ] You are testing against a **disposable/staging** client + your **own** WhatsApp number (never a real lead).

## B. Get the client_id (temporary hard-code approach)
- [ ] Open Supabase → Table Editor → `clients`.
- [ ] Find the test business row; copy its `id` (UUID).
- [ ] Note it for use as a constant in step C-2. (One UUID per business = one scenario.)

## C. Exact Make module sequence
- [ ] **C-1. Trigger module** — the event source that means "send assets now"
      (e.g. inbound Webhook from the lead flow, a Router branch after lead creation, or a
      Data Store watch). One branch → one `trigger_key`.
- [ ] **C-2. Set Variables module** — define constants for this scenario:
      - `client_id` = `<hard-coded clients.id UUID>`  ← the temporary solution
      - `trigger_key` = one of `trial_booked` | `payment_request` | `general_followup` | `lead_qualified`
      - `lead_phone` = mapped from `{{parent_phone}}` / `{{followup_target_phone}}` (E.164)
      - `event_id` = a unique value (e.g. lead id + trigger_key) for idempotency
- [ ] **C-3. HTTP "Make a request"**
      - Method: `POST`
      - URL: `{BASE_URL}/assets/trigger`
      - Headers: `Content-Type: application/json`
      - Body type: Raw / JSON:
        ```json
        { "client_id": "{{client_id}}", "trigger_key": "{{trigger_key}}",
          "trigger_source": "make", "event_id": "{{event_id}}",
          "context": { "lead_phone": "{{lead_phone}}" } }
        ```
      - Parse response: **Yes** (JSON)
- [ ] **C-4. Filter** after the HTTP module: continue only if `{{count}} > 0`
      (on the `0` branch: stop or log — never message the lead).
- [ ] **C-5. Iterator** over `{{assets[]}}`.
- [ ] **C-6. Router** by `{{item.asset_type}}` → **Twilio: Send a WhatsApp message** in each route:
      - `text`  → `Body` = `{{item.content}}`
      - `link`  → `Body` = `"{{item.asset_name}}: {{item.content}}"`
      - `pdf` / `image` / `video` → `MediaUrl` = `{{item.content}}` (public HTTPS) + optional `Body` caption `{{item.asset_name}}`
      - All routes: `To` = `whatsapp:{{lead_phone}}`, `From` = your Twilio WhatsApp sender.
- [ ] **C-7. Error handler** on the Twilio module(s): log the failing `{{item.id}}` and
      **continue** to the next asset (partial success — don't abort the batch).

## D. Test procedure (with your own WhatsApp number)
- [ ] **D-1.** In `/admin/client-setup` (or the old Assets tab) on the staging client, add a fake asset:
      `asset_name = "__TEST__ welcome"`, `asset_type = link`, `trigger_key = trial_booked`,
      `content = https://example.com/test`, enabled = on.
- [ ] **D-2.** Confirm retrieval WITHOUT Make first — call the endpoint manually:
      `POST {BASE_URL}/assets/trigger`
      body `{ "client_id": "<staging UUID>", "trigger_key": "trial_booked", "trigger_source": "make" }`
      → expect HTTP 200, `count: 1`, your asset in `assets[]`.
- [ ] **D-3.** In the Make scenario, set `To` to **your own** WhatsApp number (E.164, `whatsapp:+...`).
- [ ] **D-4.** Run the scenario once (manual run). Confirm you receive the WhatsApp message.
- [ ] **D-5.** Check Twilio Message logs for delivery status (sent/delivered/failed).
- [ ] **D-6.** Toggle the asset `enabled = off` (old Assets tab) → re-run → expect `count: 0` and
      **no** message (validates the enabled filter + the `count > 0` filter in C-4).
- [ ] **D-7.** (Optional) Test a `pdf` asset with a real public HTTPS file to confirm `MediaUrl` rendering.
- [ ] **D-8.** (Optional) Re-run with the same `event_id` to confirm your idempotency guard prevents a double-send.

## E. Gotchas to verify during test
- [ ] `trigger_key` sent by Make **exactly matches** the saved asset key (case-sensitive, snake_case) — mismatch ⇒ `count: 0`.
- [ ] `client_id` is the **UUID**, not the runtime `client_name`.
- [ ] WhatsApp 24-hour session: outside an open session, free-form messages may be blocked — an
      approved **template** may be required for `trial_booked` / `payment_request` follow-ups.
- [ ] Media URLs for `pdf/image/video` must be **publicly reachable HTTPS** and Twilio-supported; private links should be sent as `link` text instead.

## F. Cleanup
- [ ] Delete the test asset: old Assets tab → delete, **or** SQL on staging:
      `delete from client_assets where asset_name like '\_\_TEST\_\_%' escape '\';`
- [ ] If you created a staging `clients`/`agents_config` row only for this test, remove children first
      (`knowledge_items` by `agent_id`, `client_assets` by `client_id`), then the agent, then the client.
- [ ] Disable or archive the test Make scenario run; reset `To` away from your personal number before any real use.
- [ ] Confirm nothing test-related points at production (`{BASE_URL}`, Supabase target, Twilio sender).

## Out of scope
Voice-runtime changes, adding `client_id` to the lead payload, auto-firing triggers from Maya,
backend code, DB writes, commits.
