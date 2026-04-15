# Admin Panel + Auth Completion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin role support (bypass client_id filter) and `/admin` panel listing all clients with stats.

**Architecture:** A `getUserContext()` helper extracts `{ clientId, isAdmin }` from the JWT. All existing dashboard pages use it: admins see all data, clients see only their own. Middleware guards `/admin` (admin-only). A minimal `/admin` page lists clients with agent/lead counts and reset SQL.

**Tech Stack:** Next.js App Router (server components), Supabase Auth + SSR, TypeScript

---

## What Already Exists (do not rebuild)

| File | Status |
|---|---|
| `dashboard/middleware.ts` | done — session refresh + /login redirect |
| `dashboard/lib/supabase-server.ts` | done |
| `dashboard/lib/supabase-browser.ts` | done |
| `dashboard/app/login/page.tsx` | done |
| `dashboard/app/login/actions.ts` | done |
| All dashboard pages | already filter by clientId from session |
| `dashboard/app/api/leads/route.ts` | already filters by clientId |
| `supabase/migrations/add_client_id_to_leads.sql` | file exists — apply in Task 1 |

---

## File Map

| Action | File |
|--------|------|
| Create | `dashboard/lib/user-context.ts` |
| Modify | `dashboard/middleware.ts` |
| Modify | `dashboard/app/dashboard/page.tsx` |
| Modify | `dashboard/app/dashboard/agents/page.tsx` |
| Modify | `dashboard/app/dashboard/leads/page.tsx` |
| Modify | `dashboard/app/dashboard/calls/page.tsx` |
| Modify | `dashboard/app/api/leads/route.ts` |
| Create | `dashboard/app/admin/layout.tsx` |
| Create | `dashboard/app/admin/page.tsx` |

---

### Task 1: Apply the leads migration

No code — run in Supabase SQL editor.

- [ ] **Step 1: Run the migration**

Open Supabase Dashboard → SQL Editor, paste and run:

```sql
ALTER TABLE leads ADD COLUMN IF NOT EXISTS client_id uuid REFERENCES clients(id);
CREATE INDEX IF NOT EXISTS idx_leads_client_id ON leads(client_id);
```

Expected: "Success. No rows returned."

- [ ] **Step 2: Confirm the column exists**

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'leads' AND column_name = 'client_id';
```

Expected: one row returned.

---

### Task 2: Create getUserContext helper

**Files:**
- Create: `dashboard/lib/user-context.ts`

- [ ] **Step 1: Create the file**

```ts
// dashboard/lib/user-context.ts
import type { User } from "@supabase/supabase-js";

export type UserContext =
  | { isAdmin: true }
  | { isAdmin: false; clientId: string };

/**
 * Extract auth context from a Supabase user.
 * Returns null if unauthenticated or no client_id.
 * Admin: user_metadata.role === "admin"
 * Client: user_metadata.client_id is a UUID string
 */
export function getUserContext(user: User | null | undefined): UserContext | null {
  if (!user) return null;
  const meta = user.user_metadata ?? {};
  if (meta.role === "admin") return { isAdmin: true };
  const clientId = meta.client_id as string | undefined;
  if (!clientId) return null;
  return { isAdmin: false, clientId };
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/lib/user-context.ts
git commit -m "feat(auth): add getUserContext helper"
```

---

### Task 3: Update middleware to protect /admin

**Files:**
- Modify: `dashboard/middleware.ts`

- [ ] **Step 1: Replace the file**

```ts
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

  const { data: { user } } = await supabase.auth.getUser();
  const { pathname } = request.nextUrl;

  // Not logged in -> /login
  if (!user && pathname !== "/login") {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Logged in on /login -> /dashboard
  if (user && pathname === "/login") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // Non-admin on /admin -> /dashboard
  if (user && pathname.startsWith("/admin")) {
    const isAdmin = user.user_metadata?.role === "admin";
    if (!isAdmin) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/middleware.ts
git commit -m "feat(auth): protect /admin — admin role required"
```

---

### Task 4: Update all pages to support admin

**Files:**
- Modify: `dashboard/app/dashboard/page.tsx`
- Modify: `dashboard/app/dashboard/agents/page.tsx`
- Modify: `dashboard/app/dashboard/leads/page.tsx`
- Modify: `dashboard/app/dashboard/calls/page.tsx`
- Modify: `dashboard/app/api/leads/route.ts`

Admins have no `client_id` in metadata, so they currently see empty pages. Replace inline `user?.user_metadata?.client_id` with `getUserContext(user)`, then apply `.eq("client_id", ctx.clientId)` only when `!ctx.isAdmin`.

- [ ] **Step 1: Update dashboard/app/dashboard/page.tsx**

```tsx
export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { supabase } from "@/lib/supabase";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig, CallLog } from "@/types/database";
import { DashboardClientPage } from "./DashboardClientPage";

export default async function DashboardPage() {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) {
    return <DashboardClientPage agents={null} calls={null} knowledgeCount={0} />;
  }

  const agentQuery = supabase
    .from("agents_config")
    .select("id, agent_name, is_active, system_prompt, first_message, phone_number")
    .order("created_at", { ascending: false });
  if (!ctx.isAdmin) agentQuery.eq("client_id", ctx.clientId);
  const agentRes = await agentQuery;

  const agentIds = (agentRes.data ?? []).map((a: Pick<AgentConfig, "id">) => a.id);
  const callRes = agentIds.length > 0
    ? await supabase
        .from("call_logs")
        .select("id, status, created_at")
        .in("agent_id", agentIds)
        .order("created_at", { ascending: false })
        .limit(10)
    : { data: [] };

  const knowledgeRes = await supabase.from("knowledge_items").select("id, is_active");

  return (
    <DashboardClientPage
      agents={agentRes.data as Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null}
      calls={callRes.data as Pick<CallLog, "id" | "status" | "created_at">[] | null}
      knowledgeCount={knowledgeRes.data?.length ?? 0}
    />
  );
}
```

- [ ] **Step 2: Update dashboard/app/dashboard/agents/page.tsx**

```tsx
export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { supabase } from "@/lib/supabase";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig } from "@/types/database";
import { AgentsClientPage } from "./AgentsClientPage";

export default async function AgentsPage() {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return <AgentsClientPage agents={null} error="Not authenticated" />;

  const query = supabase
    .from("agents_config")
    .select("*")
    .order("created_at", { ascending: false });
  if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

  const { data, error } = await query;
  return (
    <AgentsClientPage
      agents={data as AgentConfig[] | null}
      error={error?.message ?? null}
    />
  );
}
```

- [ ] **Step 3: Update dashboard/app/dashboard/leads/page.tsx**

```tsx
export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { supabase } from "@/lib/supabase";
import { getUserContext } from "@/lib/user-context";
import { LeadsClientPage } from "./LeadsClientPage";
import { computeLeadsStats } from "@/lib/leads-stats";
import type { LeadsApiResponse, SupabaseLead } from "@/types/lead";

const EMPTY: LeadsApiResponse = {
  leads: [],
  stats: { total: 0, today: 0, new: 0, contacted: 0, voice: 0, whatsapp: 0 },
};

export default async function LeadsPage() {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return <LeadsClientPage data={EMPTY} />;

  let data: LeadsApiResponse = EMPTY;
  try {
    const query = supabase
      .from("leads")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(200);
    if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

    const { data: rows, error } = await query;
    if (error) throw error;
    const leads = (rows ?? []) as SupabaseLead[];
    data = { leads, stats: computeLeadsStats(leads) };
  } catch (err) {
    console.error("[LeadsPage] Failed to fetch leads:", err);
  }

  return <LeadsClientPage data={data} />;
}
```

- [ ] **Step 4: Update dashboard/app/dashboard/calls/page.tsx**

```tsx
export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { supabase } from "@/lib/supabase";
import { getUserContext } from "@/lib/user-context";
import { CallLog, AgentConfig } from "@/types/database";
import { CallsClientPage } from "./CallsClientPage";

type CallWithAgent = CallLog & { agents_config: Pick<AgentConfig, "agent_name"> | null };

export default async function CallsPage() {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return <CallsClientPage calls={null} error="Not authenticated" />;

  if (ctx.isAdmin) {
    const { data, error } = await supabase
      .from("call_logs")
      .select("*, agents_config(agent_name)")
      .order("created_at", { ascending: false })
      .limit(200);
    return <CallsClientPage calls={data as CallWithAgent[] | null} error={error?.message ?? null} />;
  }

  const { data: agents } = await supabase
    .from("agents_config")
    .select("id")
    .eq("client_id", ctx.clientId);

  const agentIds = (agents ?? []).map((a: Pick<AgentConfig, "id">) => a.id);
  if (agentIds.length === 0) return <CallsClientPage calls={[]} error={null} />;

  const { data, error } = await supabase
    .from("call_logs")
    .select("*, agents_config(agent_name)")
    .in("agent_id", agentIds)
    .order("created_at", { ascending: false })
    .limit(100);

  return <CallsClientPage calls={data as CallWithAgent[] | null} error={error?.message ?? null} />;
}
```

- [ ] **Step 5: Update dashboard/app/api/leads/route.ts**

```ts
import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { supabase } from "@/lib/supabase";
import { computeLeadsStats } from "@/lib/leads-stats";
import type { SupabaseLead, LeadsApiResponse } from "@/types/lead";

export async function GET(): Promise<NextResponse<LeadsApiResponse | { error: string }>> {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const query = supabase
    .from("leads")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(200);
  if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

  const { data, error } = await query;
  if (error) {
    console.error("[/api/leads] Supabase error:", error.message);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const leads = (data ?? []) as SupabaseLead[];
  return NextResponse.json({ leads, stats: computeLeadsStats(leads) });
}
```

- [ ] **Step 6: Commit**

```bash
git add dashboard/app/dashboard/page.tsx dashboard/app/dashboard/agents/page.tsx dashboard/app/dashboard/leads/page.tsx dashboard/app/dashboard/calls/page.tsx dashboard/app/api/leads/route.ts
git commit -m "feat(auth): admin role bypasses client_id filter in all pages"
```

---

### Task 5: Build the Admin panel

**Files:**
- Create: `dashboard/app/admin/layout.tsx`
- Create: `dashboard/app/admin/page.tsx`

Server-rendered page listing all clients with per-client stats.

- [ ] **Step 1: Create the layout**

```tsx
// dashboard/app/admin/layout.tsx
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-surface-0 text-white">
      <div className="border-b border-border px-8 py-4 flex items-center gap-3">
        <span className="text-brand-400 text-xs font-mono bg-brand-600/20 px-2 py-0.5 rounded">
          ADMIN
        </span>
        <span className="text-white font-semibold text-sm">Maya AI — Admin Panel</span>
      </div>
      <div className="p-8">{children}</div>
    </div>
  );
}
```

- [ ] **Step 2: Create the admin page**

```tsx
// dashboard/app/admin/page.tsx
export const dynamic = "force-dynamic";

import { supabase } from "@/lib/supabase";

type ClientRow = { id: string; name: string; created_at: string };
type AgentRow = { client_id: string };
type LeadRow = { client_id: string; created_at: string };

export default async function AdminPage() {
  const [clientsRes, agentsRes, leadsRes] = await Promise.all([
    supabase.from("clients").select("id, name, created_at").order("created_at", { ascending: false }),
    supabase.from("agents_config").select("client_id"),
    supabase.from("leads").select("client_id, created_at").order("created_at", { ascending: false }),
  ]);

  const clients = (clientsRes.data ?? []) as ClientRow[];
  const agents = (agentsRes.data ?? []) as AgentRow[];
  const leads = (leadsRes.data ?? []) as LeadRow[];

  const stats = clients.map((client) => {
    const agentCount = agents.filter((a) => a.client_id === client.id).length;
    const clientLeads = leads.filter((l) => l.client_id === client.id);
    const lastLead = clientLeads[0]?.created_at;
    return { ...client, agentCount, leadCount: clientLeads.length, lastLead };
  });

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h2 className="text-white font-semibold text-lg">Clients</h2>
        <p className="text-gray-500 text-sm mt-0.5">{clients.length} total</p>
      </div>

      <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-gray-400 font-medium px-5 py-3">Client</th>
              <th className="text-left text-gray-400 font-medium px-5 py-3">ID</th>
              <th className="text-right text-gray-400 font-medium px-5 py-3">Agents</th>
              <th className="text-right text-gray-400 font-medium px-5 py-3">Leads</th>
              <th className="text-right text-gray-400 font-medium px-5 py-3">Last Lead</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((c) => (
              <tr key={c.id} className="border-b border-border/50 last:border-0">
                <td className="px-5 py-3 text-white font-medium">{c.name}</td>
                <td className="px-5 py-3 text-gray-500 font-mono text-xs">{c.id}</td>
                <td className="px-5 py-3 text-right text-gray-300">{c.agentCount}</td>
                <td className="px-5 py-3 text-right text-gray-300">{c.leadCount}</td>
                <td className="px-5 py-3 text-right text-gray-500 text-xs">
                  {c.lastLead ? new Date(c.lastLead).toLocaleDateString("he-IL") : "—"}
                </td>
              </tr>
            ))}
            {stats.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-gray-600">
                  No clients yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="bg-surface-2 border border-border rounded-xl p-5 space-y-3">
        <h3 className="text-white font-medium text-sm">Reset demo data</h3>
        <p className="text-gray-500 text-xs">
          Run in Supabase SQL Editor. Copy the client ID from the table above.
        </p>
        <pre className="bg-surface-3 rounded-lg p-4 text-xs text-gray-400 font-mono whitespace-pre overflow-x-auto">{
`-- Delete leads for a client
DELETE FROM leads WHERE client_id = '<CLIENT_ID>';

-- Delete call logs for a client's agents
DELETE FROM call_logs
WHERE agent_id IN (
  SELECT id FROM agents_config WHERE client_id = '<CLIENT_ID>'
);`
        }</pre>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/admin/layout.tsx dashboard/app/admin/page.tsx
git commit -m "feat(admin): clients overview + reset SQL panel"
```

---

### Task 6: Verify build + BPM setup

- [ ] **Step 1: Verify TypeScript build**

```bash
cd dashboard && npm run build
```

Expected: no TypeScript errors, build completes.

- [ ] **Step 2: Get BPM client_id from Supabase**

```sql
SELECT id, name FROM clients;
```

If no BPM row:
```sql
INSERT INTO clients (name) VALUES ('BPM Studio') RETURNING id;
```

- [ ] **Step 3: Backfill agents_config**

```sql
UPDATE agents_config SET client_id = '<BPM_CLIENT_ID>' WHERE client_id IS NULL;
```

- [ ] **Step 4: Backfill leads**

```sql
UPDATE leads SET client_id = '<BPM_CLIENT_ID>' WHERE client_id IS NULL;
```

- [ ] **Step 5: Create BPM Auth user**

Supabase Dashboard → Authentication → Users → Add user (BPM email + password).

Then link to their client:
```sql
UPDATE auth.users
SET raw_user_meta_data = jsonb_build_object('client_id', '<BPM_CLIENT_ID>')
WHERE email = 'bpm-contact@example.com';
```

- [ ] **Step 6: Create your admin user**

Supabase Dashboard → Authentication → Users → Add user (your email + password).

Then set admin role:
```sql
UPDATE auth.users
SET raw_user_meta_data = jsonb_build_object('role', 'admin')
WHERE email = 'your@email.com';
```

- [ ] **Step 7: End-to-end verify**

1. `/dashboard` without login → redirected to `/login`
2. BPM login → scoped data only (only BPM agents/leads/calls)
3. Admin login → all data visible in `/dashboard`
4. `/admin` as admin → clients table visible
5. `/admin` as BPM user → redirected to `/dashboard`
