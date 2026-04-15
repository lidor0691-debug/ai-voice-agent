# Client-Scoped Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Supabase SSR auth + client_id filtering so BPM studio logs in and sees only their own agents, leads, and calls.

**Architecture:** Install `@supabase/ssr`, add a middleware session guard, create server/browser Supabase client factories, add a login page, then filter every dashboard query by `client_id` read from the authenticated user's `user_metadata`.

**Tech Stack:** Next.js 16 App Router, `@supabase/ssr`, `@supabase/supabase-js`, TypeScript, Supabase Auth

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `dashboard/package.json` | Modify | Add `@supabase/ssr` dependency |
| `dashboard/middleware.ts` | Create | Session refresh + route guard (redirect to `/login` if no session) |
| `dashboard/lib/supabase-server.ts` | Create | Server-side Supabase client factory (reads cookies from request) |
| `dashboard/lib/supabase-browser.ts` | Create | Browser-side cookie-aware Supabase client |
| `dashboard/app/login/page.tsx` | Create | Login form (email + password, dark theme) |
| `dashboard/app/login/actions.ts` | Create | `signIn` server action calling `signInWithPassword` |
| `dashboard/app/dashboard/page.tsx` | Modify | Filter agents + calls by `client_id` from session |
| `dashboard/app/dashboard/agents/page.tsx` | Modify | Filter agents by `client_id` |
| `dashboard/app/dashboard/leads/page.tsx` | Modify | Filter leads by `client_id` |
| `dashboard/app/dashboard/calls/page.tsx` | Modify | Filter calls via agent_id IN (client's agents) |
| `dashboard/app/api/leads/route.ts` | Modify | Filter leads by `client_id` from session |
| `supabase/migrations/add_client_id_to_leads.sql` | Create | Add `client_id` column + index to `leads` |

---

## Task 1: Install `@supabase/ssr`

**Files:**
- Modify: `dashboard/package.json`

- [ ] **Step 1: Install the package**

```bash
cd dashboard && npm install @supabase/ssr
```

Expected output: `added N packages` with no errors.

- [ ] **Step 2: Verify the install**

```bash
grep "@supabase/ssr" dashboard/package.json
```

Expected: `"@supabase/ssr": "^X.X.X"` appears in `dependencies`.

- [ ] **Step 3: Commit**

```bash
git add dashboard/package.json dashboard/package-lock.json
git commit -m "chore: install @supabase/ssr"
```

---

## Task 2: Create server-side Supabase client factory

**Files:**
- Create: `dashboard/lib/supabase-server.ts`

- [ ] **Step 1: Create the file**

```typescript
// dashboard/lib/supabase-server.ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createSupabaseServerClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          } catch {
            // setAll called from a Server Component — safe to ignore
          }
        },
      },
    }
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/lib/supabase-server.ts
git commit -m "feat(auth): add server-side Supabase client factory"
```

---

## Task 3: Create browser-side Supabase client factory

**Files:**
- Create: `dashboard/lib/supabase-browser.ts`

- [ ] **Step 1: Create the file**

```typescript
// dashboard/lib/supabase-browser.ts
import { createBrowserClient } from "@supabase/ssr";

export function createSupabaseBrowserClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/lib/supabase-browser.ts
git commit -m "feat(auth): add browser-side Supabase client factory"
```

---

## Task 4: Add middleware session guard

**Files:**
- Create: `dashboard/middleware.ts`

The middleware runs on every matched request. It:
1. Refreshes the Supabase session cookie (required by `@supabase/ssr` to keep tokens fresh)
2. Redirects unauthenticated users to `/login`
3. Redirects already-logged-in users away from `/login`

- [ ] **Step 1: Create the file**

```typescript
// dashboard/middleware.ts
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  // Refresh session — must call getUser() not getSession()
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  // If logged in and on login page → redirect to dashboard
  if (user && pathname === "/login") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // If not logged in and not on login page → redirect to login
  if (!user && pathname !== "/login") {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
```

- [ ] **Step 2: Verify the build still compiles**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```

Expected: build completes without TypeScript errors. (It will now redirect everything to `/login` since there's no login page yet — that's fine.)

- [ ] **Step 3: Commit**

```bash
git add dashboard/middleware.ts
git commit -m "feat(auth): add middleware session guard"
```

---

## Task 5: Add login page and server action

**Files:**
- Create: `dashboard/app/login/page.tsx`
- Create: `dashboard/app/login/actions.ts`

- [ ] **Step 1: Create the server action**

```typescript
// dashboard/app/login/actions.ts
"use server";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";

export async function signIn(
  _prevState: string | null,
  formData: FormData
): Promise<string | null> {
  const email = formData.get("email") as string;
  const password = formData.get("password") as string;

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });

  if (error) {
    return error.message;
  }

  redirect("/dashboard");
}
```

- [ ] **Step 2: Create the login page**

```tsx
// dashboard/app/login/page.tsx
"use client";

import { useActionState } from "react";
import { signIn } from "./actions";

export default function LoginPage() {
  const [error, formAction, isPending] = useActionState(signIn, null);

  return (
    <div className="min-h-screen bg-surface-0 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-white font-semibold text-2xl">Maya AI</h1>
          <p className="text-gray-500 text-sm mt-1">Sign in to your dashboard</p>
        </div>

        <form action={formAction} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-300 mb-1.5">Email</label>
            <input
              name="email"
              type="email"
              required
              autoComplete="email"
              className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 transition-colors"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-300 mb-1.5">Password</label>
            <input
              name="password"
              type="password"
              required
              autoComplete="current-password"
              className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 transition-colors"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={isPending}
            className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded-lg transition-colors"
          >
            {isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify the build compiles**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors.

- [ ] **Step 4: Smoke test login page locally**

```bash
cd dashboard && npm run dev
```

Open `http://localhost:3000` — should redirect to `/login`. The form should render with email + password fields. No errors in browser console.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app/login/page.tsx dashboard/app/login/actions.ts
git commit -m "feat(auth): add login page and signIn server action"
```

---

## Task 6: Add Supabase migration for `leads.client_id`

**Files:**
- Create: `supabase/migrations/add_client_id_to_leads.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- supabase/migrations/add_client_id_to_leads.sql
ALTER TABLE leads ADD COLUMN IF NOT EXISTS client_id uuid REFERENCES clients(id);
CREATE INDEX IF NOT EXISTS idx_leads_client_id ON leads(client_id);
```

- [ ] **Step 2: Run the migration in Supabase**

Go to Supabase Dashboard → SQL Editor → paste and run:
```sql
ALTER TABLE leads ADD COLUMN IF NOT EXISTS client_id uuid REFERENCES clients(id);
CREATE INDEX IF NOT EXISTS idx_leads_client_id ON leads(client_id);
```

Expected: `ALTER TABLE` and `CREATE INDEX` succeed with no errors.

- [ ] **Step 3: Verify the column exists**

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'leads' AND column_name = 'client_id';
```

Expected: one row with `column_name = client_id`, `data_type = uuid`.

- [ ] **Step 4: Commit the migration file**

```bash
git add supabase/migrations/add_client_id_to_leads.sql
git commit -m "feat(schema): add client_id to leads table"
```

---

## Task 7: Filter dashboard home page by client_id

**Files:**
- Modify: `dashboard/app/dashboard/page.tsx`

The current file fetches agents, calls, and knowledge items without any client filter. We replace the bare `supabase` import with the server client factory and filter agents + calls by `client_id`.

- [ ] **Step 1: Replace the file content**

```typescript
// dashboard/app/dashboard/page.tsx
export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { AgentConfig, CallLog } from "@/types/database";
import { DashboardClientPage } from "./DashboardClientPage";

export default async function DashboardPage() {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return (
      <DashboardClientPage agents={null} calls={null} knowledgeCount={0} />
    );
  }

  // Fetch agents filtered by client
  const agentRes = await supabase
    .from("agents_config")
    .select("id, agent_name, is_active, system_prompt, first_message, phone_number")
    .eq("client_id", clientId)
    .order("created_at", { ascending: false });

  // Fetch client's agent IDs to filter calls
  const agentIds = (agentRes.data ?? []).map(
    (a: Pick<AgentConfig, "id">) => a.id
  );

  const callRes = agentIds.length > 0
    ? await supabase
        .from("call_logs")
        .select("id, status, created_at")
        .in("agent_id", agentIds)
        .order("created_at", { ascending: false })
        .limit(10)
    : { data: [] };

  const knowledgeRes = await supabase
    .from("knowledge_items")
    .select("id, is_active");

  return (
    <DashboardClientPage
      agents={agentRes.data as Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null}
      calls={callRes.data as Pick<CallLog, "id" | "status" | "created_at">[] | null}
      knowledgeCount={knowledgeRes.data?.length ?? 0}
    />
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/dashboard/page.tsx
git commit -m "feat(auth): filter dashboard home by client_id"
```

---

## Task 8: Filter agents page by client_id

**Files:**
- Modify: `dashboard/app/dashboard/agents/page.tsx`

- [ ] **Step 1: Replace the file content**

```typescript
// dashboard/app/dashboard/agents/page.tsx
export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { AgentConfig } from "@/types/database";
import { AgentsClientPage } from "./AgentsClientPage";

export default async function AgentsPage() {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return <AgentsClientPage agents={null} error="Not authenticated" />;
  }

  const { data, error } = await supabase
    .from("agents_config")
    .select("*")
    .eq("client_id", clientId)
    .order("created_at", { ascending: false });

  return (
    <AgentsClientPage
      agents={data as AgentConfig[] | null}
      error={error?.message ?? null}
    />
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/dashboard/agents/page.tsx
git commit -m "feat(auth): filter agents page by client_id"
```

---

## Task 9: Filter leads page by client_id

**Files:**
- Modify: `dashboard/app/dashboard/leads/page.tsx`

- [ ] **Step 1: Replace the file content**

```typescript
// dashboard/app/dashboard/leads/page.tsx
export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { LeadsClientPage } from "./LeadsClientPage";
import { computeLeadsStats } from "@/lib/leads-stats";
import type { LeadsApiResponse, SupabaseLead } from "@/types/lead";

const EMPTY: LeadsApiResponse = {
  leads: [],
  stats: { total: 0, today: 0, new: 0, contacted: 0, voice: 0, whatsapp: 0 },
};

export default async function LeadsPage() {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return <LeadsClientPage data={EMPTY} />;
  }

  let data: LeadsApiResponse = EMPTY;

  try {
    const { data: rows, error } = await supabase
      .from("leads")
      .select("*")
      .eq("client_id", clientId)
      .order("created_at", { ascending: false })
      .limit(200);

    if (error) throw error;

    const leads = (rows ?? []) as SupabaseLead[];
    data = { leads, stats: computeLeadsStats(leads) };
  } catch (err) {
    console.error("[LeadsPage] Failed to fetch leads:", err);
  }

  return <LeadsClientPage data={data} />;
}
```

- [ ] **Step 2: Verify build**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/dashboard/leads/page.tsx
git commit -m "feat(auth): filter leads page by client_id"
```

---

## Task 10: Filter calls page by client_id

**Files:**
- Modify: `dashboard/app/dashboard/calls/page.tsx`

Calls don't have a direct `client_id`. We filter by getting the client's agent IDs first, then filtering calls by `agent_id IN (...)`.

- [ ] **Step 1: Replace the file content**

```typescript
// dashboard/app/dashboard/calls/page.tsx
export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { CallLog, AgentConfig } from "@/types/database";
import { CallsClientPage } from "./CallsClientPage";

type CallWithAgent = CallLog & { agents_config: Pick<AgentConfig, "agent_name"> | null };

export default async function CallsPage() {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return <CallsClientPage calls={null} error="Not authenticated" />;
  }

  // Get this client's agent IDs
  const { data: agents } = await supabase
    .from("agents_config")
    .select("id")
    .eq("client_id", clientId);

  const agentIds = (agents ?? []).map((a: Pick<AgentConfig, "id">) => a.id);

  if (agentIds.length === 0) {
    return <CallsClientPage calls={[]} error={null} />;
  }

  const { data, error } = await supabase
    .from("call_logs")
    .select("*, agents_config(agent_name)")
    .in("agent_id", agentIds)
    .order("created_at", { ascending: false })
    .limit(100);

  return (
    <CallsClientPage
      calls={data as CallWithAgent[] | null}
      error={error?.message ?? null}
    />
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/dashboard/calls/page.tsx
git commit -m "feat(auth): filter calls page by client_id"
```

---

## Task 11: Filter `/api/leads` route by client_id

**Files:**
- Modify: `dashboard/app/api/leads/route.ts`

- [ ] **Step 1: Replace the file content**

```typescript
// dashboard/app/api/leads/route.ts
import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { computeLeadsStats } from "@/lib/leads-stats";
import type { SupabaseLead, LeadsApiResponse } from "@/types/lead";

export async function GET(): Promise<NextResponse<LeadsApiResponse | { error: string }>> {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("leads")
    .select("*")
    .eq("client_id", clientId)
    .order("created_at", { ascending: false })
    .limit(200);

  if (error) {
    console.error("[/api/leads] Supabase error:", error.message);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const leads = (data ?? []) as SupabaseLead[];
  return NextResponse.json({ leads, stats: computeLeadsStats(leads) });
}
```

- [ ] **Step 2: Verify build**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/api/leads/route.ts
git commit -m "feat(auth): filter /api/leads by client_id from session"
```

---

## Task 12: BPM one-time setup

This is a manual operations task, not code. Run the following steps in order.

- [ ] **Step 1: Find or create the BPM client row**

In Supabase Dashboard → SQL Editor:
```sql
SELECT id, name FROM clients ORDER BY created_at;
```

If a BPM row exists, note its `id` as `<BPM_CLIENT_ID>`.

If not:
```sql
INSERT INTO clients (name) VALUES ('BPM Studio') RETURNING id;
```

Note the returned `id` as `<BPM_CLIENT_ID>`.

- [ ] **Step 2: Backfill agents_config**

```sql
UPDATE agents_config
SET client_id = '<BPM_CLIENT_ID>'
WHERE client_id IS NULL;
```

Verify:
```sql
SELECT id, agent_name, client_id FROM agents_config;
```

Expected: all rows now have `client_id` set.

- [ ] **Step 3: Backfill leads**

```sql
UPDATE leads
SET client_id = '<BPM_CLIENT_ID>'
WHERE client_id IS NULL;
```

Verify:
```sql
SELECT COUNT(*) FROM leads WHERE client_id IS NULL;
```

Expected: `0`.

- [ ] **Step 4: Create the BPM Supabase Auth user**

Go to Supabase Dashboard → Authentication → Users → "Add user" (invite or create directly).

Set the email and password for the BPM contact.

- [ ] **Step 5: Set client_id in user metadata**

In Supabase SQL Editor:
```sql
UPDATE auth.users
SET raw_user_meta_data = jsonb_build_object('client_id', '<BPM_CLIENT_ID>'::text)
WHERE email = 'bpm-contact@example.com';
```

Verify:
```sql
SELECT email, raw_user_meta_data FROM auth.users WHERE email = 'bpm-contact@example.com';
```

Expected: `raw_user_meta_data` contains `{"client_id": "<BPM_CLIENT_ID>"}`.

---

## Task 13: End-to-end verification

- [ ] **Step 1: Start the dev server**

```bash
cd dashboard && npm run dev
```

- [ ] **Step 2: Verify unauthenticated redirect**

Open `http://localhost:3000` in a fresh private browser window.

Expected: redirected to `http://localhost:3000/login`.

- [ ] **Step 3: Verify login works**

Enter the BPM email + password in the login form. Click "Sign in".

Expected: redirected to `/dashboard`. Dashboard shows BPM agents and calls only.

- [ ] **Step 4: Verify agents isolation**

Go to `/dashboard/agents`.

Expected: only BPM agents listed.

- [ ] **Step 5: Verify leads isolation**

Go to `/dashboard/leads`.

Expected: only BPM leads listed.

- [ ] **Step 6: Verify calls isolation**

Go to `/dashboard/calls`.

Expected: only calls linked to BPM agents listed.

- [ ] **Step 7: Final commit tag**

```bash
git tag v1.0.0-client-isolation
```

---

## Self-Review Notes

- All spec requirements covered: auth flow (Tasks 1–5), schema (Task 6), query filtering (Tasks 7–11), BPM setup (Task 12), verification (Task 13).
- `getUser()` used throughout — not `getSession()`.
- `call_logs` filtered via `agent_id IN (client's agents)` — no schema change needed.
- `knowledge_items` intentionally left unfiltered (no `client_id` column, only one client today).
- Types consistent: `Pick<AgentConfig, "id">` used for agent ID extraction in Tasks 7, 8, 10.
- No voice logic, WhatsApp logic, i18n, or UI layout touched.
