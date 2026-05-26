# Client Setup Wizard — Design Spec

**Date:** 2026-05-25
**Status:** Approved for planning
**Scope owner:** Maya AI dashboard (`C:\Users\lidor\maya-ai\dashboard`)

## Problem

Onboarding a new business onto Maya (multi-tenant AI voice + WhatsApp agent platform) is
too manual and not plug-and-play. An admin needs a single, structured flow to create and
configure a new agent for a business end-to-end.

## Goal

A new admin-only route `/admin/client-setup` providing a 6-step wizard that creates a client
+ agent, attaches knowledge (services/pricing/FAQs) and assets (links/contracts/forms),
generates a clean `system_prompt`, surfaces a readiness checklist, and publishes the agent —
all using existing Supabase tables and existing API routes wherever possible.

## Hard constraints (from task brief)

- Do NOT redesign the dashboard, touch unrelated pages, or refactor existing architecture.
- Use existing tables: `clients`, `agents_config`, `knowledge_items`, `client_assets`.
- No analytics, no premium dashboard, no landing-page changes, no billing, no complex
  automation, no voice-runtime changes.
- Minimal, safe changes only.

## Decisions locked during brainstorming

1. **Reuse method:** Extract the shared UI primitives from `agent-form.tsx` into
   `components/agents/form-primitives.tsx` and import them in both the existing form and the
   new wizard (Option A). One behavior-preserving edit to the existing file; no duplication.
2. **Status field:** Propose a migration in this spec only — **do not apply it**. The
   implementation must not break when the `status` column is unavailable.
3. **DB writes:** Build the UI + API integration; the user tests. No live migrations or live
   writes performed as part of implementation.
4. **Prompt generation:** Auto-generate a clean prompt and show it in an **editable preview**
   on the Publish step; whatever the admin leaves there is saved.
5. **Test checklist:** Manual checkboxes with **derived hints** (auto-flag items already
   configured). No live API probes.
6. **No admin tab yet:** `/admin/client-setup` is a direct hidden route until the flow is
   stable. Do NOT add it to `admin/layout.tsx`.
7. **No assumed metadata column:** Do not assume `clients.metadata` / `agents_config.metadata`
   physically exists. Checklist is UI-only by default; persistence is an opt-in only if the
   column is confirmed to exist. No hidden schema additions.
8. **Draft vs Publish writes:** Save Draft persists only the client + agent draft. Knowledge
   items and client assets are written only on Publish (or a later explicit save once
   `agent_id`/`client_id` exist) — never on the first draft save.

## Existing facts the design relies on

- `POST /api/agents` (admin-only) creates a `clients` row (name derived from
  `business_name`/`agent_name`) **and** a linked `agents_config` row in one call, returning the
  agent with `id` and `client_id`. → natural publish entry point.
- `PATCH /api/agents/{id}` updates an agent (sends only changed fields).
- `POST /api/knowledge` inserts into `knowledge_items` (requires `agent_id`; fields:
  `category`, `title`, `content`, `priority`, `is_active`).
- `POST /api/clients/{client_id}/assets` inserts into `client_assets` (`asset_name`,
  `asset_type` ∈ `text|link|pdf|image|video`, `trigger_key`, `content`, `sort_order`, `enabled`).
- `/admin/*` is gated by `middleware.ts` (`user_metadata.role === "admin"`); pages additionally
  use `getUserContext(user).isAdmin`.
- UI conventions: Tailwind tokens `surface-*`, `brand-*`, `border-border`; `lucide-react`
  icons; RTL (`dir="rtl"`); strings via `useLanguage()` `t.*`. No shadcn.
- `agents_config` has **no `status` column** today — activity is `is_active` (boolean).
  `knowledge_items` link to `agent_id` (not client). `clients.metadata` is declared in
  `types/database.ts` but unverified physically.
- Backend `app/services/agent_config.py::build_supabase_system_prompt()` uses `system_prompt`
  verbatim when set, otherwise generates a default, then appends knowledge items at call time.

## Architecture

```
/admin/client-setup (server component, isAdmin gate)
        └─ <ClientSetupWizard />  (client component, holds all wizard state)
              ├─ form-primitives.tsx  (Field/Input/Textarea/Select/StepIndicator — shared)
              ├─ lib/generate-system-prompt.ts  (pure TS prompt builder)
              └─ orchestrates existing APIs:
                    POST/PATCH /api/agents          → clients + agents_config
                    POST       /api/knowledge        → knowledge_items (FAQs/services/pricing)
                    POST       /api/clients/{id}/assets → client_assets (links/contracts/forms)
```

### Components & units

| Unit | Purpose | Depends on |
|---|---|---|
| `app/admin/client-setup/page.tsx` | Server gate + render wizard | `supabase-server`, `user-context` |
| `components/admin/client-setup-wizard.tsx` | 6-step stateful wizard | primitives, prompt helper, fetch APIs |
| `components/agents/form-primitives.tsx` | Shared `Field/Input/Textarea/Select/StepIndicator` | — (presentational) |
| `lib/generate-system-prompt.ts` | Pure fn: wizard inputs → prompt string | — |

## Wizard steps

1. **Business details** — `business_name`, `agent_name` (required), `language`, `tone`.
   `clients.name` is derived by the existing `/api/agents` POST.
2. **Communication channels** — `channel` (`voice`/`whatsapp`), `phone_number` (voice/Twilio,
   E.164 validated), WhatsApp block (`whatsapp_enabled`, `whatsapp_number`, follow-up type),
   `lead_delivery_method` + `lead_delivery_target`.
3. **Services, pricing, FAQs, links/contracts/forms** — repeatable list editors:
   - Services → `knowledge_items` `category:"service"`
   - Pricing → `knowledge_items` `category:"pricing"`
   - FAQs → `knowledge_items` `category:"faq"` (`title` = question, `content` = answer)
   - Links/contracts/forms → `client_assets` (`asset_type` `link` or `pdf`, `trigger_key`,
     `content` = URL/text)
   Items are held in wizard state; not written until Publish (see write strategy).
4. **Agent behavior & handoff** — `tone`/`style_prompt`, `transfer_number`,
   handoff rules (`whatsapp_rules`), `whatsapp_required_fields`, free-text behavior notes that
   feed prompt generation.
5. **Test checklist** — manual checkboxes with derived hints; items:
   - WhatsApp number set, Voice/Twilio number set, WhatsApp follow-up configured,
     CRM/lead-delivery target set.
   - Each item auto-shows a ✓ hint when its source field is filled. UI-only by default.
6. **Publish** — editable generated-prompt preview (textarea), status selector
   (draft / ready_for_test / live), summary, and Save Draft / Publish buttons.

## Storage mapping

| Wizard input | Table / columns |
|---|---|
| Business, channels, behavior | `agents_config` (+ `clients.name` via POST) |
| Services | `knowledge_items` `category:"service"` |
| Pricing | `knowledge_items` `category:"pricing"` |
| FAQs | `knowledge_items` `category:"faq"` |
| Links / contracts / forms | `client_assets` `asset_type:'link'\|'pdf'` |
| Generated prompt | `agents_config.system_prompt` |
| Status | `agents_config.status` (after migration) + `is_active` mirror |
| Setup checklist | UI-only by default (opt-in `clients.metadata.setup_checklist` only if column confirmed) |

## Write strategy (Draft vs Publish)

- **Save Draft:**
  1. If no `agent_id` yet → `POST /api/agents` with the agent body, `status:'draft'` (omitted
     gracefully if unsupported), `is_active:false`. Capture returned `id` + `client_id`.
  2. If `agent_id` exists → `PATCH /api/agents/{id}` with changed fields.
  3. **Do NOT** write `knowledge_items` or `client_assets` on draft save.
- **Publish:**
  1. Ensure agent exists (create or patch) with `status:'live'`, `is_active:true`, and the
     final `system_prompt` from the editable preview.
  2. Write all Step-3 items: `POST /api/knowledge` per service/pricing/FAQ (using `agent_id`);
     `POST /api/clients/{client_id}/assets` per link/contract/form.
  3. On success → success state; optional redirect.
- **Later explicit save:** once `agent_id`/`client_id` exist, Step 3 may be saved explicitly
  without full publish (same per-item POST calls).

## Prompt generation

`lib/generate-system-prompt.ts` exports a pure function mirroring the section structure of the
backend `build_supabase_system_prompt()`: role, language, tone, services/pricing summary,
handoff rules, behavior notes. Output is a clean prompt string shown in the Publish-step
textarea (editable). Knowledge items are NOT inlined into the prompt — the backend appends them
at call time — so the preview includes a note: "FAQs / services are attached separately and
added automatically during calls." Whatever text is in the textarea is saved verbatim to
`system_prompt`.

## Status migration (PROPOSED — DO NOT APPLY)

```sql
ALTER TABLE agents_config
  ADD COLUMN status text NOT NULL DEFAULT 'draft'
  CHECK (status IN ('draft','ready_for_test','live'));

UPDATE agents_config SET status = 'live' WHERE is_active = true;
```

Until applied:
- `status` is added to the `AgentConfig` type as optional (`status?: ...`).
- The wizard always sends `is_active` (the source of truth that exists today) and
  *additionally* sends `status`. If the column is absent, the insert/patch must still succeed —
  achieved by sending `status` only when known-safe, or by tolerating the column's absence
  (e.g. the API ignores unknown keys / a follow-up patch). Implementation detail to be resolved
  in the plan, but the hard rule: **no broken writes when `status` is unavailable**, and
  `live` ⇔ `is_active = true`.

## Files

**New:**
- `app/admin/client-setup/page.tsx`
- `components/admin/client-setup-wizard.tsx`
- `components/agents/form-primitives.tsx`
- `lib/generate-system-prompt.ts`

**Edited (minimal, in-scope):**
- `components/agents/agent-form.tsx` — replace local primitive definitions with imports from
  `form-primitives.tsx` (behavior-preserving).
- `types/database.ts` — add optional `status?: 'draft'|'ready_for_test'|'live'` to `AgentConfig`.

**Explicitly NOT changed:**
- `admin/layout.tsx` (no new tab yet), voice runtime, other dashboard pages, public landing,
  billing, analytics. No applied migrations. No assumed metadata columns.

## i18n / RTL

New strings added to the existing `t.*` dictionary (`lib/i18n.ts` / language context), Hebrew +
English, consistent with existing `af_*` keys. Wizard uses `dir="rtl"` like `agent-form.tsx`.

## Testing strategy

- Prompt generator: unit-style assertions on the pure function (inputs → expected sections).
- Wizard flow: manual admin walkthrough (create draft → publish → verify rows). Live DB writes
  performed by the user, not during implementation.
- Verify Save Draft does not create knowledge/assets rows.
- Verify writes succeed with `status` column absent (graceful path) and present (post-migration).

## Out of scope / non-goals

Analytics, premium dashboard, landing page, billing, complex automation, live readiness probes,
voice-runtime changes, refactoring `agent-form.tsx` step logic, applying the status migration.

## Open items for the plan

- Exact mechanism for status tolerance (omit-when-unsupported vs separate patch).
- Whether Step 3 supports a mid-wizard explicit save or only Publish (default: Publish-only for
  v1; explicit save is a nice-to-have).
