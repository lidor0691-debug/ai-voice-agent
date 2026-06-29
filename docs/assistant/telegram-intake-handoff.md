# Maya — Owner-only Telegram Intake (Handoff)

> ⚠️ **LIVE BUT LOCKED IN DRY-RUN.** The assistant is deployed and can parse Hebrew owner commands, but it **cannot send anything to anyone**. There is **no dispatcher and no customer-messaging path**. `ASSISTANT_TELEGRAM_DRY_RUN` **must stay `true`** for all demos.

- **main:** `5f58225` (PR #51 deployed)
- **Scope of this delivery:** owner-only Telegram intake — understand a Hebrew command, resolve a recipient, and **prepare** a scheduled action. Preview-only in demos.
- **Calendar integration:** **Phase 2 — NOT included** (see §10).

---

## 1. Current production state

- **Platform:** Railway · **Domain:** `https://ai-voice-agent-production-0a55.up.railway.app` · entry `uvicorn main:app`.
- **Route:** `POST /assistant/telegram/webhook` (mounted only when intake is enabled).
- **Secret header:** `X-Telegram-Bot-Api-Secret-Token` (constant-time compare; fail-closed → neutral `200`).
- **Mode:** `ASSISTANT_TELEGRAM_INTAKE_ENABLED=true`, `ASSISTANT_TELEGRAM_DRY_RUN=true`.
- **Owner mapping:** the owner's Telegram numeric id → `clients.id 642d2881-9e7d-47cb-8cae-2d6b58a062de` (**מאיה BPM**). Verified read-only.
- **Test contact:** `דנה` (recipient_type `client`, **phone NULL**, id `87b9aea9-aa95-408c-bc94-f4bb91f01376`).
- **Persist test:** one controlled `DRY_RUN=false` test was run and the resulting scheduled row was **soft-cancelled** (status `cancelled`). Tables otherwise empty of real data.
- **Shipped PRs:** #42 NLP contract+resolver · #43/#44 Supabase schema + hardened grants · #45 Command Core · #46 Claude Stage-1 parser (`claude-sonnet-4-6`) · #47 Hebrew eval harness · #48 unicode fix · #49 teacher-inference tuning · #50 Telegram intake · #51 scheduled_at UTC fix.

## 2. What is verified

- `/health` → `200`; route mounted (present in `openapi.json`).
- **Auth chain (fail-closed):** wrong/missing secret → neutral `200`, no processing; non-allowlisted / unmapped user → no parser, no DB, no reply.
- **Owner-map** resolves to `מאיה BPM`.
- **Parser** healthy in production (live Claude; extracts recipient + time from Hebrew).
- **Dry-run paths both work:** scheduled-preview (`🧪 בדיקה — ✅ נקבע …`) and clarification (`🧪 בדיקה — ❓ …`).
- **One persist write** produced exactly 1 scheduled (`manual_fallback`) + 2 audit rows, then soft-cancelled.
- **Zero customer sends**, zero Twilio/WhatsApp/Make activity (none possible).
- **Timezone fix** (#51): a 10:00 Israel command persists as the correct UTC instant.

## 3. What is intentionally NOT implemented

- **No dispatcher / no sending** — nothing reads scheduled rows to deliver them.
- **No customer messaging** of any kind (no WhatsApp/Twilio/Make on this path).
- **No persist-by-default** — persist runs only when both `INTAKE_ENABLED=true` and `DRY_RUN=false`.
- **No self-reminder intent** — `תזכיר לי …` ("remind me") returns "who to send to?" (only send-to-contact is modeled).
- **No multi-user** — single owner via static env map.
- **No contact management UI** — contacts are seeded directly in the DB.
- **No calendar integration** — Phase 2 (§10).
- **PR7 not started.**

## 4. Required Railway env vars (names only — never commit values)

On the **backend FastAPI service**:

| Variable | Purpose | Demo value |
|---|---|---|
| `ASSISTANT_TELEGRAM_INTAKE_ENABLED` | mounts the route | `true` |
| `ASSISTANT_TELEGRAM_DRY_RUN` | preview-only; **keep true for demos** | `true` |
| `ASSISTANT_TELEGRAM_BOT_TOKEN` | BotFather token (secret) | *(set, not shown)* |
| `ASSISTANT_TELEGRAM_WEBHOOK_SECRET` | webhook header secret (secret) | *(set, not shown)* |
| `ASSISTANT_TELEGRAM_ALLOWED_USER_IDS` | CSV of allowed Telegram ids | owner's id |
| `ASSISTANT_TELEGRAM_OWNER_MAP` | `<tg_id>:<owner_uuid>` | owner → `מאיה BPM` |
| `ANTHROPIC_API_KEY` | Stage-1 parser (secret) | *(set, not shown)* |
| `ASSISTANT_PARSER_MODEL` | optional override | unset → defaults to `claude-sonnet-4-6` |

> Never paste secret **values** into docs, chat, or commits. A **missing `ANTHROPIC_API_KEY`** silently degrades the parser to "❓ למי לשלוח?" for every message.

## 5. Safety checklist before any demo

1. `GET /health` → `200`.
2. `openapi.json` contains `/assistant/telegram/webhook` (route mounted).
3. `ASSISTANT_TELEGRAM_DRY_RUN=true` (confirm in Railway).
4. `getWebhookInfo` clean: correct URL, `allowed_updates=["message"]`, `pending_update_count` low, no `last_error_message`.
5. Send **only** from the **whitelisted owner account**.
6. `ANTHROPIC_API_KEY` present on the backend service.
7. Expect every reply to start with `🧪 בדיקה —` (proof dry-run is on). **If a reply has no `🧪` prefix, stop the demo** — dry-run is off.

## 6. Dry-run demo script (preview-only)

Send these from the owner's Telegram account; all replies are owner-facing previews, nothing is sent or persisted.

1. **Scheduled preview** — `שלח לדנה מחר ב-10:00 הודעה: היי דנה, מזכירים לך לגבי שיעור הניסיון שקבענו 🙏`
   → `🧪 בדיקה — ✅ נקבע: הודעה לדנה — שליחה <מחר> 10:00 (ידני).`
2. **Missing-time clarification** — `שלח לדנה הודעה`
   → `🧪 בדיקה — ❓ מתי לשלוח? …`
3. **Missing-recipient clarification** — `שלח תזכורת מחר ב-10:00`
   → `🧪 בדיקה — ❓ למי לשלוח?`

> All three are **previews only** — zero Supabase writes, zero sends.

## 7. Known limitations

- **No send layer** — "scheduled" is terminal; a dispatcher (Phase later) is required to ever deliver.
- **Send plan:** the test contact has no phone and `custom` isn't template-backed → plan resolves to `manual_fallback` (owner sends by hand, conceptually).
- **Exact-name contact match** — the parser's recipient string must exactly equal the contact `name` (e.g. `דנה`).
- **Idempotency** is in-memory/best-effort per `update_id` (resets on redeploy).
- **Audit is append-only** — scheduled rows and activity-log rows **cannot be deleted** (block-delete triggers); scheduled rows can only be **soft-cancelled** (`status='cancelled'`).
- **Self-reminders not modeled** (see §3).
- **Startup logs** print some config diagnostics (Twilio phone number, key-presence/length checks). **No raw API key is exposed**, but trimming this is on the backlog (§9).

## 8. Rollback / safety steps

- **Already-safe default:** `DRY_RUN=true` → previews only, no writes.
- **Unmount the route:** set `ASSISTANT_TELEGRAM_INTAKE_ENABLED=false` and redeploy → endpoint 404s, no intake code loads.
- **Stop deliveries at source:** Telegram `deleteWebhook`.
- **Cancel a scheduled row** (DELETE is blocked by trigger; UPDATE only):
  ```sql
  UPDATE public.assistant_scheduled_messages SET status='cancelled' WHERE id='<row-id>';
  ```
- **No DB migration to revert** (no schema change in the recent fix).
- For demos: **leave dry-run on**; never flip it off in front of a client.

## 9. Next gated backlog (each a separate, explicitly-approved PR)

1. **Dispatcher** — the first component that actually sends; requires approval-to-send gates, owner confirmation flow, and careful safety rules. (tz prerequisite met by #51.)
2. **Anthropic SDK version pin** — `requirements.txt` currently pins a loose `anthropic>=0.40.0`; tighten so `messages.parse` can't regress on a rebuild.
3. **Parser-failure observability** — distinguish a swallowed `safe_clarification` (e.g. auth/SDK failure) from a genuine missing-recipient.
4. **Reduce startup config logging** — trim the Twilio-phone / key-presence diagnostics.

## 10. Calendar integration — Phase 2 (NOT in tomorrow's delivery)

**Tomorrow's delivery is owner-only Telegram intake only.** It understands Hebrew commands and **prepares** actions safely in dry-run. It does **not**:

- connect to the owner's calendar,
- read calendar availability,
- create or update calendar events.

**Calendar integration is a separate, gated phase** because it involves:

- **OAuth / permissions** to the owner's calendar account,
- **privacy** handling of calendar data,
- **availability** reading and conflict logic,
- **event creation/update** logic,
- **audit & safety rules** for any write to a real calendar.

It must be designed and approved deliberately — not bundled into the v1 intake.

### How to explain this to Maya / BPM (client-facing wording)

> "Version 1 is live in Telegram and safely prepares actions. Calendar connection is the next phase and should be implemented carefully, not rushed."

---

## ⚠️ Final warning

**No customer sending exists yet. No dispatcher exists. `ASSISTANT_TELEGRAM_DRY_RUN` MUST stay `true` for demos.** Every demo reply should begin with `🧪 בדיקה —`; if it doesn't, dry-run is off — stop immediately.
