# Role-Based UI Separation Plan

**Date:** 2026-04-25  
**Status:** SPEC — not yet implemented  
**Goal:** Hide admin/technical UI from client users. Minimal, safe changes using existing auth infrastructure.

---

## 1. Current State

Already working:
- `getUserContext()` returns `{ isAdmin: true }` or `{ isAdmin: false, clientId }` from Supabase user_metadata
- Middleware blocks `/admin/*` routes for non-admins
- Sidebar conditionally shows Admin link
- Most data queries already filter by `client_id` for non-admins

**The foundation exists.** This plan is about hiding UI elements, not building new auth.

---

## 2. Proposed Separation Model

### CLIENT-FACING (business owners see)

| Page | What they see |
|------|---------------|
| `/dashboard` | Stats, recent calls, leads, insights — already scoped |
| `/dashboard/agents` | Their agents list |
| `/dashboard/agents/[id]` | **Restricted view** — name, greeting, personality, language, schedule, knowledge, assets. NO provider/model/webhook/temperature |
| `/dashboard/calls` | Their call logs — already scoped |
| `/dashboard/leads` | Their leads — already scoped |
| `/dashboard/knowledge` | Their knowledge items — **needs client_id filter** |
| `/dashboard/settings` | **Business settings only** — workspace name, language, timezone. NO Supabase URL, backend URL, schema section |
| Voice preview | Keep — it's a product feature |
| Dashboard assistant | Keep — product feature |

### ADMIN-ONLY (operator sees)

| Area | Details |
|------|---------|
| `/admin/*` | Already protected — clients, users, audit |
| Agent technical fields | voice_provider, model_provider, model_name, temperature, post_call_webhook_url, lead_delivery_target, system_prompt |
| Settings: Integrations | Supabase URL, backend URL, schema docs link |
| Agent create (`/dashboard/agents/new`) | Admin-only — clients shouldn't create agents |
| Analytics page | Admin-only for now (mock data, dev tool) |
| Archived agents / restore | Admin-only |

---

## 3. What You Listed vs What I'm Adding

### Things you missed that should be admin-only:

| Item | Why |
|------|-----|
| **System prompt** (agent form) | Reveals full AI instruction logic. Client shouldn't see/edit the raw LLM prompt |
| **Agent creation** (`/agents/new`) | Agents are provisioned by operator, not self-service |
| **Temperature / model_name** | Technical tuning parameters, meaningless to business users |
| **post_call_webhook_url** | Infrastructure wiring, security-sensitive |
| **lead_delivery_target** (webhook mode) | Email/WhatsApp targets are OK; raw webhook URLs are not |
| **Knowledge page — missing client_id filter** | Currently uses admin Supabase client, shows ALL knowledge across tenants |
| **Analytics page** | Currently mock data / dev tool, not production-ready |
| **Test call / test agent API** | `POST /api/test-call` and `/api/test-agent` have no ownership check — any auth'd user can test any agent_id |
| **WebSocket voice endpoint** | Agent ID is passed as query param — should validate ownership server-side |
| **Client assets trigger keys** | The trigger key vocabulary (trial_booked, payment_request, etc.) is implementation detail |

### Hidden risks / exposures:

1. **Knowledge page has no tenant isolation** — `knowledge/page.tsx` fetches all items with admin client
2. **`/api/test-call` and `/api/test-agent`** — no agent ownership check, any user can invoke with any agent_id
3. **WebSocket `/ws/voice-browser`** — backend doesn't validate that the caller owns the agent_id
4. **Settings page exposes infra URLs** — Supabase URL and backend URL visible to all users
5. **Agent form shows webhook URLs** — post_call_webhook_url is visible and editable
6. **Lead delivery target in webhook mode** — raw endpoint URL visible

---

## 4. Implementation Plan — Files to Change

### Phase 1: Agent form field visibility (highest impact, lowest risk)

**Files:**
- `dashboard/components/agents/agent-form.tsx` — wrap admin-only fields in `{isAdmin && ...}` blocks
- `dashboard/app/dashboard/agents/[id]/page.tsx` — pass `isAdmin` prop from server context
- `dashboard/app/dashboard/agents/new/page.tsx` — redirect non-admins to `/dashboard/agents`

**Fields to hide from clients:**
- voice_provider, voice_id
- model_provider, model_name
- temperature
- post_call_webhook_url
- lead_delivery_target (webhook URL mode only — email/whatsapp OK)
- system_prompt (full prompt editor)
- scheduling JSON (show friendly schedule UI later, hide raw JSON now)

**What clients still see:**
- Agent name, greeting message, first message
- Language
- WhatsApp number, goals, required fields, rules
- Client assets tab
- Voice preview (listen-only, pre-configured voice)

### Phase 2: Settings page cleanup

**Files:**
- `dashboard/app/dashboard/settings/page.tsx` — hide Integrations + Schema sections for non-admins

**Client sees:** Workspace name, language, about  
**Admin sees:** Full settings including Supabase URL, backend URL, schema link

### Phase 3: Knowledge tenant isolation

**Files:**
- `dashboard/app/dashboard/knowledge/page.tsx` — filter by `client_id` for non-admins
- Verify API routes for knowledge also filter

### Phase 4: Route guards for admin-only pages

**Files:**
- `dashboard/middleware.ts` — add `/dashboard/agents/new` and `/dashboard/analytics` to admin-only redirects
- OR: check `isAdmin` server-side in those pages and redirect

### Phase 5: API hardening

**Files:**
- `dashboard/app/api/test-call/route.ts` — validate agent ownership
- `dashboard/app/api/test-agent/route.ts` — validate agent ownership
- Backend: `/ws/voice-browser` — validate agent ownership server-side

### Phase 6 (future): Client-friendly agent editor

- Replace raw system prompt with structured personality/tone/instructions UI
- Replace raw scheduling JSON with visual schedule picker
- Add client-facing "My Settings" (business name, notification prefs)

---

## 5. Phased Rollout

| Phase | Scope | Risk | Effort |
|-------|-------|------|--------|
| **1** | Agent form field hiding | Very low — UI-only, conditional rendering | ~1 hour |
| **2** | Settings page cleanup | Very low — hide sections | ~20 min |
| **3** | Knowledge tenant isolation | Low — add WHERE clause | ~30 min |
| **4** | Route guards (agents/new, analytics) | Very low — middleware addition | ~20 min |
| **5** | API ownership validation | Medium — backend changes | ~1 hour |
| **6** | Client-friendly editors | Medium — new UI components | Future |

**Recommended order:** 1 → 2 → 4 → 3 → 5 → 6

Phase 1 eliminates the biggest exposure (technical agent config visible to clients). Phases 2-4 are quick wins. Phase 5 is backend hardening. Phase 6 is product polish.

---

## 6. Implementation Pattern

The pattern is consistent across all phases:

```tsx
// Server component (page.tsx)
const ctx = getUserContext(user);
const isAdmin = ctx?.isAdmin ?? false;

// Pass to client component
<AgentForm agent={agent} isAdmin={isAdmin} />

// Client component — conditional rendering
{isAdmin && (
  <FormField label="Model Provider">
    <Select ... />
  </FormField>
)}
```

No new auth system needed. No new middleware. Just pass `isAdmin` down and conditionally render.

---

## 7. What NOT to do

- Don't create a separate admin dashboard app — overkill
- Don't duplicate pages — use conditional rendering within existing pages
- Don't remove features — hide them by role
- Don't refactor the auth system — it already works
- Don't add feature flags — role check is the feature flag
