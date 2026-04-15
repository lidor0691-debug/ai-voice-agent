# Client-Scoped Dashboard — Design Spec

**Date:** 2026-04-15  
**Status:** Approved  
**Scope:** Minimal client isolation for BPM studio — login + data filtering by client_id

---

## Goal

One paying client (BPM studio) can log in and see only their own dashboard data: agents, leads, and calls. No mixed data with future clients.

---

## Non-goals

- Full RLS hardening for all future clients
- Multi-user teams or roles
- Billing or subscriptions
- UI redesign
- Full onboarding flow
- Voice or WhatsApp logic changes (except client_id linkage where strictly required)

---

## Section 1 — Schema

### Existing (no change needed)
- `clients` table — already exists
- `agents_config.client_id uuid references clients(id)` — already exists, set on new agents via `POST /api/agents`

### New migration
Add `client_id` to `leads`:
```sql
ALTER TABLE leads ADD COLUMN IF NOT EXISTS client_id uuid REFERENCES clients(id);
CREATE INDEX IF NOT EXISTS idx_leads_client_id ON leads(client_id);
```

`call_logs` — no schema change. Calls are already linked to agents via `agent_id`. Dashboard filters calls by joining through `agents_config` where `client_id` matches.

---

## Section 2 — Auth Flow

### Packages
Install `@supabase/ssr`.

### Supabase client factories
- `dashboard/lib/supabase-server.ts` — server-side client that reads session from request cookies. Used in server components and API routes.
- `dashboard/lib/supabase-browser.ts` — cookie-aware browser client. Used in the login form client component.

### Middleware (`dashboard/middleware.ts`)
Runs on every request:
1. Refreshes the session cookie (required by `@supabase/ssr`)
2. If no valid session → redirect to `/login`
3. If valid session and path is `/login` → redirect to `/dashboard`

Protected paths: everything under `/dashboard` and `/api`.

### Login page (`dashboard/app/login/page.tsx`)
- Minimal email + password form, dark theme matching the existing UI
- On submit → calls server action `signIn` in `app/login/actions.ts`
- On success → redirects to `/dashboard`
- On failure → shows inline error message

### Server action (`dashboard/app/login/actions.ts`)
- Calls `supabase.auth.signInWithPassword({ email, password })`
- On success → Next.js redirect to `/dashboard`
- On error → returns error string to the form

---

## Section 3 — Session → client_id

Each Supabase Auth user stores `client_id` in `user_metadata`:
```json
{ "client_id": "<uuid>" }
```

Server components and API routes read `client_id` from the authenticated user:
```ts
const { data: { user } } = await supabase.auth.getUser()
const clientId = user?.user_metadata?.client_id
```

**Important:** use `getUser()`, not `getSession()`. `getUser()` validates the JWT server-side with Supabase. `getSession()` only reads from the cookie without validation and is not safe for server-side authorization.

No separate `users` table. No extra join. `client_id` travels with the JWT.

---

## Section 4 — Dashboard Query Filtering

Every server component that fetches data gets the session from cookies via the server Supabase client and applies `.eq("client_id", clientId)`.

| Page | Table | Filter |
|---|---|---|
| `/dashboard` (home) | `agents_config` | `.eq("client_id", clientId)` |
| `/dashboard` (home) | `call_logs` | via agent_id IN (filtered agents) |
| `/dashboard` (home) | `knowledge_items` | **not filtered** — no `client_id` column; acceptable since only one client exists today |
| `/dashboard/agents` | `agents_config` | `.eq("client_id", clientId)` |
| `/dashboard/leads` | `leads` | `.eq("client_id", clientId)` |
| `/dashboard/calls` | `call_logs` | subfilter: only calls where `agent_id` belongs to client's agents |
| `GET /api/leads` | `leads` | `.eq("client_id", clientId)` from session cookie |

If `clientId` is undefined (should not happen post-login), return empty results — do not expose data.

---

## Section 5 — BPM Setup (one-time)

### Step 1 — Confirm BPM client row
Run in Supabase SQL editor:
```sql
SELECT id, name FROM clients;
```
Note the BPM client's `id` (call it `<BPM_CLIENT_ID>`).

If no BPM row exists yet:
```sql
INSERT INTO clients (name) VALUES ('BPM Studio') RETURNING id;
```

### Step 2 — Backfill agents_config
```sql
UPDATE agents_config
SET client_id = '<BPM_CLIENT_ID>'
WHERE client_id IS NULL;
```

### Step 3 — Backfill leads
```sql
UPDATE leads
SET client_id = '<BPM_CLIENT_ID>'
WHERE client_id IS NULL;
```

### Step 4 — Create BPM Auth user
In Supabase Dashboard → Authentication → Users → Invite user (or use Admin API):
- Email: bpm@example.com (or whatever the BPM contact's email is)
- After creation, set `user_metadata` via Supabase Admin API:
```json
{ "client_id": "<BPM_CLIENT_ID>" }
```

Or use the Supabase SQL editor with the auth admin functions:
```sql
SELECT auth.users; -- confirm user id
UPDATE auth.users
SET raw_user_meta_data = '{"client_id": "<BPM_CLIENT_ID>"}'
WHERE email = 'bpm@example.com';
```

---

## Section 6 — Files Changed

| File | Action |
|---|---|
| `dashboard/package.json` | Add `@supabase/ssr` |
| `dashboard/middleware.ts` | New — session guard + redirect |
| `dashboard/lib/supabase-server.ts` | New — server client factory (cookies) |
| `dashboard/lib/supabase-browser.ts` | New — browser client factory (cookies) |
| `dashboard/app/login/page.tsx` | New — login form |
| `dashboard/app/login/actions.ts` | New — signIn server action |
| `dashboard/app/dashboard/page.tsx` | Filter agents + calls by `client_id` |
| `dashboard/app/dashboard/agents/page.tsx` | Filter agents by `client_id` |
| `dashboard/app/dashboard/leads/page.tsx` | Filter leads by `client_id` |
| `dashboard/app/dashboard/calls/page.tsx` | Filter calls by agent's `client_id` |
| `dashboard/app/api/leads/route.ts` | Filter leads by `client_id` from session |
| `supabase/migrations/add_client_id_to_leads.sql` | New column + index |

### Not touched
- Voice logic (`/agent`, Twilio, OpenAI Realtime)
- WhatsApp backend
- Agent form internals
- Settings page
- Knowledge base
- UI layout / sidebar / header
- i18n

---

## Verification

After implementation + BPM setup:
1. Navigating to `/dashboard` without login → redirected to `/login`
2. Login with BPM credentials → redirected to `/dashboard`
3. Agents page shows only BPM agents
4. Leads page shows only BPM leads
5. Calls page shows only calls linked to BPM agents
6. Dashboard home stats reflect only BPM data
