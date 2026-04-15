# Maya AI Dashboard — Full Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all dashboard page styles with the approved dark-premium design (violet accent, surface hierarchy, KPI cards, animated live chip) across all 7 pages — pure visual change, zero logic changes.

**Architecture:** Tailwind token update → shared layout components → page-by-page replacement. Each task is self-contained. The Tailwind config already has `brand` (violet) and `surface` tokens — we update values slightly then apply consistently.

**Tech Stack:** Next.js 14 App Router, Tailwind CSS, shadcn/ui, lucide-react, TypeScript

---

## File Map

| File | Action |
|------|--------|
| `dashboard/tailwind.config.ts` | Update surface/border token values |
| `dashboard/app/globals.css` | Update `.card`, `.btn-primary`, add `.btn-gradient`, `.live-dot` |
| `dashboard/components/layout/sidebar.tsx` | Full restyle |
| `dashboard/components/layout/header.tsx` | Full restyle — add live chip, gradient button |
| `dashboard/app/dashboard/DashboardClientPage.tsx` | KPI row + chart + agent list + calls feed |
| `dashboard/components/dashboard/test-agent.tsx` | Chat bubble restyle |
| `dashboard/components/agents/agent-card.tsx` | Card restyle with gradient avatar + mini bar |
| `dashboard/app/dashboard/agents/AgentsClientPage.tsx` | Header + grid restyle |
| `dashboard/app/dashboard/calls/CallsClientPage.tsx` | KPI row + table restyle |
| `dashboard/components/leads/supabase-leads-table.tsx` | Table restyle |
| `dashboard/components/knowledge/knowledge-client.tsx` | Upload zone + list restyle |
| `dashboard/app/dashboard/settings/page.tsx` | Section nav + form restyle |
| `dashboard/app/admin/page.tsx` | Table restyle + aggregate KPIs |

---

## Task 1: Foundation — Tailwind Tokens + Global CSS

**Files:**
- Modify: `dashboard/tailwind.config.ts`
- Modify: `dashboard/app/globals.css`

- [ ] **Step 1: Update tailwind.config.ts**

Replace the full `theme.extend` block:

```ts
// dashboard/tailwind.config.ts
theme: {
  extend: {
    colors: {
      brand: {
        50:  "#ede9fe",
        100: "#ddd6fe",
        200: "#c4b5fd",
        400: "#a78bfa",
        500: "#8b5cf6",
        600: "#7c3aed",
        700: "#6d28d9",
        900: "#4c1d95",
      },
      surface: {
        0: "#05050d",
        1: "#0c0c18",
        2: "#111122",
        3: "#18182a",
        4: "#1e1e30",
      },
      border: {
        DEFAULT: "rgba(255,255,255,0.06)",
        subtle:  "rgba(255,255,255,0.04)",
        strong:  "rgba(255,255,255,0.12)",
      },
    },
    fontFamily: {
      sans: ["var(--font-inter)", "ui-sans-serif", "system-ui"],
    },
    boxShadow: {
      card:     "0 1px 3px 0 rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)",
      glow:     "0 0 20px rgba(139,92,246,0.2)",
      "glow-sm":"0 4px 12px rgba(139,92,246,0.3)",
    },
    animation: {
      pulse2: "pulse2 1.8s ease-in-out infinite",
    },
    keyframes: {
      pulse2: {
        "0%, 100%": { opacity: "1", transform: "scale(1)" },
        "50%":      { opacity: "0.4", transform: "scale(0.85)" },
      },
    },
  },
},
```

- [ ] **Step 2: Update globals.css**

Replace the `@layer components` block:

```css
@layer components {
  .card {
    @apply bg-surface-1 border border-border rounded-[14px];
  }

  .input-base {
    @apply w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600
    focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 transition-colors;
  }

  .btn-primary {
    @apply bg-gradient-to-br from-brand-500 to-indigo-500 hover:from-brand-400 hover:to-indigo-400
    text-white text-sm font-semibold px-4 py-2 rounded-lg transition-all shadow-glow-sm;
  }

  .btn-ghost {
    @apply bg-transparent hover:bg-surface-3 text-gray-400 hover:text-white
    text-sm font-medium px-4 py-2 rounded-lg transition-colors border border-border;
  }

  /* Animated live dot */
  .live-dot {
    @apply w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse2;
    box-shadow: 0 0 6px #10b981;
  }

  /* Radial glow overlay for KPI cards */
  .kpi-glow-violet::before {
    content: '';
    position: absolute; inset: 0; border-radius: 14px; pointer-events: none;
    background: radial-gradient(ellipse at top right, rgba(139,92,246,0.12) 0%, transparent 60%);
  }
  .kpi-glow-green::before {
    content: '';
    position: absolute; inset: 0; border-radius: 14px; pointer-events: none;
    background: radial-gradient(ellipse at top right, rgba(16,185,129,0.08) 0%, transparent 60%);
  }
  .kpi-glow-blue::before {
    content: '';
    position: absolute; inset: 0; border-radius: 14px; pointer-events: none;
    background: radial-gradient(ellipse at top right, rgba(59,130,246,0.08) 0%, transparent 60%);
  }
  .kpi-glow-amber::before {
    content: '';
    position: absolute; inset: 0; border-radius: 14px; pointer-events: none;
    background: radial-gradient(ellipse at top right, rgba(245,158,11,0.08) 0%, transparent 60%);
  }
}
```

- [ ] **Step 3: Verify build compiles**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```

Expected: no errors (warnings OK).

- [ ] **Step 4: Commit**

```bash
git add dashboard/tailwind.config.ts dashboard/app/globals.css
git commit -m "style: update design tokens — dark premium palette + live-dot animation"
```

---

## Task 2: Sidebar

**Files:**
- Modify: `dashboard/components/layout/sidebar.tsx`

- [ ] **Step 1: Replace sidebar component**

```tsx
// dashboard/components/layout/sidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Bot, Phone, BookOpen,
  Settings, Zap, Users, ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/context/language-context";

export function Sidebar({ isAdmin = false }: { isAdmin?: boolean }) {
  const pathname = usePathname();
  const { t } = useLanguage();

  const NAV_ITEMS = [
    { href: "/dashboard",           label: t.nav_dashboard, icon: LayoutDashboard },
    { href: "/dashboard/agents",    label: t.nav_agents,    icon: Bot },
    { href: "/dashboard/calls",     label: t.nav_calls,     icon: Phone },
    { href: "/dashboard/leads",     label: t.nav_leads,     icon: Users },
    { href: "/dashboard/knowledge", label: t.nav_knowledge, icon: BookOpen },
    { href: "/dashboard/settings",  label: t.nav_settings,  icon: Settings },
  ];

  return (
    <aside className="w-56 min-h-screen bg-surface-1 border-e border-border flex flex-col flex-shrink-0">
      {/* Brand */}
      <div className="h-14 flex items-center gap-3 px-4 border-b border-border">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-indigo-500 flex items-center justify-center flex-shrink-0 shadow-glow-sm">
          <Zap className="w-3.5 h-3.5 text-white" />
        </div>
        <div>
          <p className="text-white font-bold text-sm leading-none tracking-tight">
            Maya<span className="text-brand-400">AI</span>
          </p>
          <p className="text-gray-600 text-[10px] mt-0.5">Agent Platform</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "relative flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] font-medium transition-all",
                active
                  ? "bg-brand-500/10 text-white border border-brand-500/20"
                  : "text-gray-500 hover:text-gray-200 hover:bg-surface-3"
              )}
            >
              {active && (
                <span className="absolute end-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-full bg-gradient-to-b from-brand-500 to-indigo-500" />
              )}
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Admin link */}
      {isAdmin && (
        <div className="px-2 pb-2">
          <Link
            href="/admin"
            className={cn(
              "relative flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] font-medium transition-all",
              pathname.startsWith("/admin")
                ? "bg-brand-500/10 text-white border border-brand-500/20"
                : "text-gray-500 hover:text-gray-200 hover:bg-surface-3"
            )}
          >
            {pathname.startsWith("/admin") && (
              <span className="absolute end-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-full bg-gradient-to-b from-brand-500 to-indigo-500" />
            )}
            <ShieldCheck className="w-4 h-4 flex-shrink-0" />
            Admin
          </Link>
        </div>
      )}

      {/* Footer */}
      <div className="px-3 py-3 border-t border-border">
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-xl bg-surface-2 border border-border">
          <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-brand-500 to-indigo-500 flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0">
            M
          </div>
          <div className="overflow-hidden flex-1">
            <p className="text-gray-300 text-xs font-medium truncate">{t.workspace}</p>
          </div>
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" style={{boxShadow:'0 0 6px #10b981'}} />
        </div>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Verify no TypeScript errors**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/layout/sidebar.tsx
git commit -m "style(sidebar): dark premium restyle — gradient logo, active indicator bar"
```

---

## Task 3: Header (Topbar)

**Files:**
- Modify: `dashboard/components/layout/header.tsx`

- [ ] **Step 1: Replace header component**

```tsx
// dashboard/components/layout/header.tsx
"use client";

import { Search } from "lucide-react";
import { useLanguage } from "@/context/language-context";

interface Props {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function Header({ title, subtitle, action }: Props) {
  const { lang, setLang, t } = useLanguage();

  return (
    <div className="h-14 border-b border-border flex items-center justify-between px-6 flex-shrink-0 bg-surface-1">
      {/* Page info */}
      <div>
        <h1 className="text-white font-semibold text-sm tracking-tight">{title}</h1>
        {subtitle && <p className="text-gray-600 text-[11px] mt-0.5">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-2.5">
        {/* Search */}
        <div className="relative">
          <Search className="absolute top-1/2 -translate-y-1/2 start-3 w-3.5 h-3.5 text-gray-600" />
          <input
            placeholder={t.search_placeholder}
            className="bg-surface-2 border border-border rounded-lg ps-9 pe-3 py-1.5 text-xs text-white placeholder-gray-600
              focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 w-44 transition-colors"
          />
        </div>

        {/* Live chip */}
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <span className="live-dot" />
          {t.status_active}
        </span>

        {/* Language toggle */}
        <div className="flex items-center gap-0.5 bg-surface-2 border border-border rounded-lg p-0.5">
          {(["he", "en"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                lang === l
                  ? "bg-gradient-to-br from-brand-500 to-indigo-500 text-white shadow-glow-sm"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {l === "he" ? t.lang_he : t.lang_en}
            </button>
          ))}
        </div>

        {/* Optional page CTA */}
        {action}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Check TypeScript**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/layout/header.tsx
git commit -m "style(header): add live-dot chip, gradient lang toggle, optional action slot"
```

---

## Task 4: Dashboard Home Page

**Files:**
- Modify: `dashboard/app/dashboard/DashboardClientPage.tsx`

- [ ] **Step 1: Replace DashboardClientPage**

```tsx
// dashboard/app/dashboard/DashboardClientPage.tsx
"use client";

import Link from "next/link";
import { Bot, Phone, BookOpen, Users, ArrowRight } from "lucide-react";
import { Header } from "@/components/layout/header";
import { TestAgent } from "@/components/dashboard/test-agent";
import { useLanguage } from "@/context/language-context";
import type { AgentConfig, CallLog } from "@/types/database";

interface Props {
  agents: Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null;
  calls:  Pick<CallLog, "id" | "status" | "created_at">[] | null;
  knowledgeCount: number;
}

// Simple 20-bar sparkline — heights as % of max
const CHART_BARS = [8,12,22,45,70,95,88,60,75,50,68,85,72,55,40,30,20,14,9,6];

export function DashboardClientPage({ agents, calls, knowledgeCount }: Props) {
  const { t } = useLanguage();

  const totalAgents  = agents?.length ?? 0;
  const activeAgents = agents?.filter((a) => a.is_active).length ?? 0;
  const totalCalls   = calls?.length ?? 0;
  const recentCalls  = calls?.slice(0, 5) ?? [];

  const kpiCards = [
    {
      label: t.kpi_total_agents, value: totalAgents,
      icon: Bot, colorText: "text-brand-400", colorBg: "bg-brand-500/10",
      glowClass: "kpi-glow-violet", href: "/dashboard/agents",
    },
    {
      label: t.kpi_active_agents, value: activeAgents,
      icon: Users, colorText: "text-emerald-400", colorBg: "bg-emerald-500/10",
      glowClass: "kpi-glow-green", href: "/dashboard/agents",
    },
    {
      label: t.kpi_recent_calls, value: totalCalls,
      icon: Phone, colorText: "text-blue-400", colorBg: "bg-blue-500/10",
      glowClass: "kpi-glow-blue", href: "/dashboard/calls",
    },
    {
      label: t.kpi_knowledge_items, value: knowledgeCount,
      icon: BookOpen, colorText: "text-amber-400", colorBg: "bg-amber-500/10",
      glowClass: "kpi-glow-amber", href: "/dashboard/knowledge",
    },
  ];

  const maxBar = Math.max(...CHART_BARS);

  return (
    <div className="flex-1 overflow-y-auto">
      <Header title={t.page_dashboard_title} subtitle={t.page_dashboard_subtitle} />

      <div className="p-6 space-y-5 bg-surface-0 min-h-full">

        {/* KPI Row */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {kpiCards.map(({ label, value, icon: Icon, colorText, colorBg, glowClass, href }) => (
            <Link
              key={label}
              href={href}
              className={`relative card p-5 hover:border-brand-500/30 transition-all overflow-hidden ${glowClass}`}
            >
              <div className={`w-9 h-9 rounded-xl ${colorBg} flex items-center justify-center mb-4`}>
                <Icon className={`w-4 h-4 ${colorText}`} />
              </div>
              <p className="text-2xl font-extrabold text-white tracking-tight">{value}</p>
              <p className="text-gray-600 text-[11px] mt-1">{label}</p>
            </Link>
          ))}
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">

          {/* Voice Activity Chart */}
          <div className="xl:col-span-3 card p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-white text-sm font-semibold">פעילות קולית</p>
                <p className="text-gray-600 text-[11px] mt-0.5">24 שעות אחרונות</p>
              </div>
            </div>
            {/* Bar chart */}
            <div className="flex items-end gap-1.5 h-24">
              {CHART_BARS.map((h, i) => {
                const pct = (h / maxBar) * 100;
                const isPeak = pct >= 80;
                const isHi   = pct >= 50 && !isPeak;
                return (
                  <div
                    key={i}
                    style={{ height: `${pct}%` }}
                    className={`flex-1 rounded-t-sm transition-all ${
                      isPeak
                        ? "bg-brand-500 shadow-glow-sm"
                        : isHi
                        ? "bg-brand-500/40"
                        : "bg-surface-3"
                    }`}
                  />
                );
              })}
            </div>
            <div className="flex justify-between mt-2">
              {["00:00","04:00","08:00","12:00","16:00","20:00","23:59"].map((l) => (
                <span key={l} className="text-[9px] text-gray-700">{l}</span>
              ))}
            </div>
          </div>

          {/* Right column */}
          <div className="xl:col-span-2 space-y-4">

            {/* Agents quick list */}
            <div className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-white text-[13px] font-semibold">{t.your_agents}</h2>
                <Link href="/dashboard/agents" className="text-gray-600 hover:text-brand-400 text-[11px] flex items-center gap-1 transition-colors">
                  {t.view_all} <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {!agents?.length ? (
                <p className="text-gray-700 text-[11px] text-center py-4">{t.no_agents_yet}</p>
              ) : (
                <div className="space-y-1">
                  {agents.slice(0, 4).map((agent) => (
                    <Link
                      key={agent.id}
                      href={`/dashboard/agents/${agent.id}`}
                      className="flex items-center justify-between py-2 px-2 rounded-xl hover:bg-surface-3 transition-colors group"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-brand-500/20 to-indigo-500/20 border border-brand-500/20 flex items-center justify-center">
                          <span className="text-brand-400 text-[10px] font-bold">
                            {agent.agent_name.charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <span className="text-gray-400 text-[13px] group-hover:text-white transition-colors">
                          {agent.agent_name}
                        </span>
                      </div>
                      <span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={agent.is_active ? { background: "#10b981", boxShadow: "0 0 6px #10b981" } : { background: "#334155" }}
                      />
                    </Link>
                  ))}
                </div>
              )}
            </div>

            {/* Recent Calls */}
            <div className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-white text-[13px] font-semibold">{t.kpi_recent_calls}</h2>
                <Link href="/dashboard/calls" className="text-gray-600 hover:text-brand-400 text-[11px] flex items-center gap-1 transition-colors">
                  {t.view_all} <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {recentCalls.length === 0 ? (
                <p className="text-gray-700 text-[11px] text-center py-4">{t.no_calls_yet}</p>
              ) : (
                <div className="space-y-1">
                  {recentCalls.map((call) => (
                    <div
                      key={call.id}
                      className="flex items-center justify-between py-1.5 px-2 rounded-xl border-e-2 border-transparent"
                      style={{
                        borderColor:
                          call.status === "completed" ? "#10b981"
                          : call.status === "missed"   ? "#f59e0b"
                          : "#ef4444",
                      }}
                    >
                      <span className="text-gray-500 text-[11px]">
                        {new Date(call.created_at).toLocaleString("he-IL", {
                          month: "short", day: "numeric",
                          hour: "2-digit", minute: "2-digit",
                        })}
                      </span>
                      <span className={`text-[11px] font-semibold ${
                        call.status === "completed" ? "text-emerald-400"
                        : call.status === "missed"   ? "text-amber-400"
                        : "text-red-400"
                      }`}>
                        {call.status ?? "—"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Test Agent */}
        <TestAgent
          agents={
            agents?.map((a) => ({
              id: a.id,
              agent_name: a.agent_name,
              system_prompt: a.system_prompt,
              first_message: a.first_message,
            })) ?? []
          }
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/dashboard/DashboardClientPage.tsx
git commit -m "style(home): KPI cards with glow, voice chart, styled agent/calls panels"
```

---

## Task 5: Agent Card + Agents Page

**Files:**
- Modify: `dashboard/components/agents/agent-card.tsx`
- Modify: `dashboard/app/dashboard/agents/AgentsClientPage.tsx`

- [ ] **Step 1: Restyle AgentCard**

```tsx
// dashboard/components/agents/agent-card.tsx
"use client";

import Link from "next/link";
import { Phone, Settings } from "lucide-react";
import { AgentConfig } from "@/types/database";
import { useLanguage } from "@/context/language-context";

interface Props { agent: AgentConfig; }

const GRADIENT_PAIRS = [
  ["from-brand-500","to-indigo-500"],
  ["from-blue-500","to-cyan-500"],
  ["from-emerald-500","to-teal-500"],
  ["from-amber-500","to-orange-500"],
  ["from-pink-500","to-rose-500"],
];

export function AgentCard({ agent }: Props) {
  const { t } = useLanguage();
  // deterministic color pick based on first char
  const idx = agent.agent_name.charCodeAt(0) % GRADIENT_PAIRS.length;
  const [from, to] = GRADIENT_PAIRS[idx];

  return (
    <Link
      href={`/dashboard/agents/${agent.id}`}
      className="group relative card p-5 hover:border-brand-500/30 transition-all overflow-hidden"
    >
      <div className="flex items-start justify-between mb-4">
        {/* Avatar */}
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${from} ${to} flex items-center justify-center shadow-glow-sm`}>
          <span className="text-white font-bold text-sm">{agent.agent_name.charAt(0).toUpperCase()}</span>
        </div>

        {/* Status badge */}
        <span
          className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border ${
            agent.is_active
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              : "bg-surface-3 text-gray-500 border-border"
          }`}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={agent.is_active ? { background:"#10b981", boxShadow:"0 0 6px #10b981" } : { background:"#334155" }}
          />
          {agent.is_active ? t.agent_active : t.agent_inactive}
        </span>
      </div>

      <h3 className="text-white font-semibold text-sm mb-1 group-hover:text-brand-400 transition-colors">
        {agent.agent_name}
      </h3>
      <p className="text-gray-600 text-[11px] mb-4 line-clamp-1">
        {[agent.language, agent.tone, agent.model_name].filter(Boolean).join(" · ") || t.not_configured}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-border">
        <div className="flex items-center gap-1.5 text-gray-600 text-[11px]">
          <Phone className="w-3 h-3" />
          <span>{agent.phone_number ?? t.no_number}</span>
        </div>
        <Settings className="w-3.5 h-3.5 text-gray-700 group-hover:text-brand-400 transition-colors" />
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Restyle AgentsClientPage header**

Replace only the header `div` (lines 18–31 in original) — keep the grid and empty state logic. Full replacement:

```tsx
// dashboard/app/dashboard/agents/AgentsClientPage.tsx
"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { AgentCard } from "@/components/agents/agent-card";
import { Header } from "@/components/layout/header";
import { useLanguage } from "@/context/language-context";
import type { AgentConfig } from "@/types/database";

interface Props {
  agents: AgentConfig[] | null;
  error: string | null;
}

export function AgentsClientPage({ agents, error }: Props) {
  const { t } = useLanguage();

  const action = (
    <Link href="/dashboard/agents/new" className="btn-primary flex items-center gap-2">
      <Plus className="w-3.5 h-3.5" />
      {t.new_agent_btn}
    </Link>
  );

  return (
    <div className="flex-1 overflow-y-auto bg-surface-0">
      <Header
        title={t.page_agents_title}
        subtitle={`${agents?.length ?? 0} agents`}
        action={action}
      />

      <div className="p-6">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl mb-6">
            {t.failed_load_agents} {error}
          </div>
        )}

        {!agents?.length && !error ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-12 h-12 rounded-2xl card flex items-center justify-center mb-4">
              <Plus className="w-5 h-5 text-gray-600" />
            </div>
            <p className="text-white font-medium">{t.no_agents_title}</p>
            <p className="text-gray-600 text-sm mt-1 mb-6">{t.no_agents_desc}</p>
            <Link href="/dashboard/agents/new" className="btn-primary">
              {t.create_agent_btn}
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {agents?.map((agent) => <AgentCard key={agent.id} agent={agent} />)}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/components/agents/agent-card.tsx dashboard/app/dashboard/agents/AgentsClientPage.tsx
git commit -m "style(agents): gradient avatars, live status dot, new header action slot"
```

---

## Task 6: Calls Page

**Files:**
- Modify: `dashboard/app/dashboard/calls/CallsClientPage.tsx`

- [ ] **Step 1: Replace CallsClientPage**

```tsx
// dashboard/app/dashboard/calls/CallsClientPage.tsx
"use client";

import { Phone, Clock, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { Header } from "@/components/layout/header";
import { useLanguage } from "@/context/language-context";
import type { CallLog, AgentConfig } from "@/types/database";

type CallWithAgent = CallLog & { agents_config: Pick<AgentConfig, "agent_name"> | null };

function formatDuration(secs: number | null) {
  if (!secs) return "—";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

const STATUS_CONFIG = {
  completed: { text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", dot: "#10b981" },
  missed:    { text: "text-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/20",   dot: "#f59e0b" },
  failed:    { text: "text-red-400",     bg: "bg-red-500/10",     border: "border-red-500/20",     dot: "#ef4444" },
} as const;

interface Props {
  calls: CallWithAgent[] | null;
  error: string | null;
}

export function CallsClientPage({ calls, error }: Props) {
  const { t } = useLanguage();

  const total     = calls?.length ?? 0;
  const completed = calls?.filter((c) => c.status === "completed").length ?? 0;
  const missed    = calls?.filter((c) => c.status === "missed").length ?? 0;

  const statusLabel = (status: string | null) => {
    switch (status) {
      case "completed": return t.status_completed;
      case "missed":    return t.status_missed;
      case "failed":    return t.status_failed;
      default:          return t.status_unknown;
    }
  };

  const statusIcon = (status: string | null) => {
    switch (status) {
      case "completed": return <CheckCircle className="w-3 h-3" />;
      case "missed":    return <AlertCircle className="w-3 h-3" />;
      case "failed":    return <XCircle className="w-3 h-3" />;
      default:          return <Phone className="w-3 h-3" />;
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-surface-0">
      <Header title={t.page_calls_title} subtitle={t.page_calls_subtitle} />

      <div className="p-6 space-y-5">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl">
            {t.failed_load_calls} {error}
          </div>
        )}

        {/* KPI Row */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: t.kpi_total_calls, value: total,     icon: Phone,       colorText: "text-brand-400",   colorBg: "bg-brand-500/10",   glow: "kpi-glow-violet" },
            { label: t.kpi_completed,   value: completed, icon: CheckCircle, colorText: "text-emerald-400", colorBg: "bg-emerald-500/10", glow: "kpi-glow-green" },
            { label: t.kpi_missed,      value: missed,    icon: AlertCircle, colorText: "text-amber-400",   colorBg: "bg-amber-500/10",   glow: "kpi-glow-amber" },
          ].map(({ label, value, icon: Icon, colorText, colorBg, glow }) => (
            <div key={label} className={`relative card p-5 flex items-center gap-4 overflow-hidden ${glow}`}>
              <div className={`w-9 h-9 rounded-xl ${colorBg} flex items-center justify-center flex-shrink-0`}>
                <Icon className={`w-4 h-4 ${colorText}`} />
              </div>
              <div>
                <p className="text-2xl font-extrabold text-white tracking-tight">{value}</p>
                <p className="text-gray-600 text-[11px]">{label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Table */}
        {!calls?.length ? (
          <div className="card flex flex-col items-center justify-center py-24 text-center">
            <Phone className="w-8 h-8 text-gray-700 mb-3" />
            <p className="text-white font-medium">{t.no_calls_title}</p>
            <p className="text-gray-600 text-sm mt-1">{t.no_calls_desc}</p>
          </div>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  {[t.col_date, t.col_caller, t.col_agent, t.col_duration, t.col_status].map((h) => (
                    <th key={h} className="text-start text-[11px] text-gray-600 font-medium px-5 py-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => {
                  const cfg = STATUS_CONFIG[call.status as keyof typeof STATUS_CONFIG];
                  return (
                    <tr key={call.id} className="border-b border-border last:border-0 hover:bg-surface-2 transition-colors">
                      <td className="px-5 py-3.5 text-gray-400 text-[13px]">
                        {new Date(call.created_at).toLocaleString("he-IL", {
                          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                        })}
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2">
                          <Phone className="w-3 h-3 text-gray-700" />
                          <span className="text-gray-300 text-[13px] font-mono">{call.phone_number ?? t.unknown_caller}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-gray-500 text-[13px]">{call.agents_config?.agent_name ?? t.unknown_caller}</td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-1.5 text-gray-500 text-[13px]">
                          <Clock className="w-3 h-3" />
                          {formatDuration(call.duration)}
                        </div>
                      </td>
                      <td className="px-4 py-3.5">
                        {cfg ? (
                          <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border ${cfg.text} ${cfg.bg} ${cfg.border}`}>
                            {statusIcon(call.status)}
                            {statusLabel(call.status)}
                          </span>
                        ) : (
                          <span className="text-gray-600 text-[11px]">{statusLabel(call.status)}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/dashboard/calls/CallsClientPage.tsx
git commit -m "style(calls): dark table, KPI glow cards, color-coded status badges"
```

---

## Task 7: Leads Page

**Files:**
- Modify: `dashboard/components/leads/supabase-leads-table.tsx`

- [ ] **Step 1: Read current file**

```bash
head -30 dashboard/components/leads/supabase-leads-table.tsx
```

- [ ] **Step 2: Replace table + header styling**

Apply the same pattern as Task 6: wrap in `<div className="flex-1 overflow-y-auto bg-surface-0">`, add `<Header>` at top, replace table classes.

Key class replacements (apply throughout the file):
- `bg-surface-2 border border-border rounded-xl` → `card`
- `hover:bg-surface-3` → `hover:bg-surface-2`
- `text-gray-500 text-xs font-medium` (th) → `text-[11px] text-gray-600 font-medium`
- `text-gray-300 text-sm` (td) → `text-gray-400 text-[13px]`
- Status badge `rounded-full border` pattern → same STATUS_CONFIG approach as calls

Read the full file first, then apply changes consistently. The data-fetching logic (`useEffect`, `useState`, Supabase calls) must not be touched.

- [ ] **Step 3: TypeScript check**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/components/leads/supabase-leads-table.tsx
git commit -m "style(leads): dark table restyle matching calls page"
```

---

## Task 8: Knowledge Page

**Files:**
- Modify: `dashboard/components/knowledge/knowledge-client.tsx`

- [ ] **Step 1: Read current file**

```bash
cat dashboard/components/knowledge/knowledge-client.tsx
```

- [ ] **Step 2: Apply restyle**

Key changes (read file first for exact structure):
- Wrap in `bg-surface-0` container
- Add `<Header title={t.nav_knowledge} />`
- Upload zone: `border-2 border-dashed border-brand-500/30 rounded-2xl bg-brand-500/5 hover:border-brand-500/50 hover:bg-brand-500/8 transition-all`
- Knowledge item rows: `card` class + `hover:bg-surface-2`
- Buttons: `btn-primary` / `btn-ghost` utilities

- [ ] **Step 3: TypeScript check + commit**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
git add dashboard/components/knowledge/knowledge-client.tsx
git commit -m "style(knowledge): upload zone violet dashed, item rows dark cards"
```

---

## Task 9: Settings Page

**Files:**
- Modify: `dashboard/app/dashboard/settings/page.tsx`

- [ ] **Step 1: Read current file**

```bash
cat dashboard/app/dashboard/settings/page.tsx
```

- [ ] **Step 2: Apply restyle**

Key changes:
- Wrap in `bg-surface-0`
- Add `<Header title={t.nav_settings} />`
- Section nav (if exists) or form group headers: `text-[11px] text-gray-600 uppercase tracking-wider font-semibold mb-3`
- All `<input>`, `<select>`, `<textarea>` → use `.input-base` utility
- Save/submit buttons → `btn-primary`
- Form section panels → `card p-5 space-y-4`

- [ ] **Step 3: TypeScript check + commit**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
git add dashboard/app/dashboard/settings/page.tsx
git commit -m "style(settings): dark form panels, input-base utility, gradient save button"
```

---

## Task 10: Admin Page

**Files:**
- Modify: `dashboard/app/admin/page.tsx`

- [ ] **Step 1: Add Header import and apply restyle**

The admin page is a server component. Changes:
- Wrap root `div` in a client-compatible shell (or just apply class changes)
- Replace `bg-surface-2 border border-border rounded-xl` → `card`
- `hover:bg-surface-3` → `hover:bg-surface-2`
- Table `th`: `text-[11px] text-gray-600 font-medium`
- Table `td` text: `text-gray-400 text-[13px]`
- `pre` block: `bg-surface-2 rounded-xl p-4 text-[11px] text-gray-500 font-mono`

Since this is a server component, no `<Header>` (Header is client). Add a simple header div:

```tsx
<div className="h-14 border-b border-border flex items-center px-6 bg-surface-1 mb-6">
  <h1 className="text-white font-semibold text-sm">Admin Panel</h1>
</div>
```

- [ ] **Step 2: TypeScript check + commit**

```bash
cd dashboard && npx tsc --noEmit 2>&1 | head -20
git add dashboard/app/admin/page.tsx
git commit -m "style(admin): dark table restyle, consistent card + surface tokens"
```

---

## Task 11: Final Build Verification

- [ ] **Step 1: Full build**

```bash
cd dashboard && npm run build 2>&1
```

Expected: `✓ Compiled successfully` with no TypeScript errors. Warnings about missing env vars are OK.

- [ ] **Step 2: Dev server smoke test**

```bash
cd dashboard && npm run dev
```

Open `http://localhost:3000` and verify:
- Sidebar: gradient logo, violet active indicator bar on left side, green status dot in footer
- Topbar: animated live dot, gradient language toggle
- Home: KPI cards with glow, bar chart, styled agent/call lists
- Agents: gradient avatar cards
- Calls: dark table with colored status badges
- Knowledge, Settings, Admin: consistent dark surfaces

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "style(dashboard): full dark premium redesign complete — all 7 pages"
```

---

## Self-Review

**Spec coverage check:**
- ✓ Color palette: Task 1 sets all tokens
- ✓ Sidebar: Task 2
- ✓ Header/topbar with live chip: Task 3
- ✓ Home KPI cards with glow: Task 4
- ✓ Voice activity chart: Task 4
- ✓ Agent list + calls feed: Task 4
- ✓ Test agent panel: Task 4 (TestAgent component reused, styled by globals)
- ✓ Agents page + card with gradient avatar: Task 5
- ✓ Calls page: Task 6
- ✓ Leads page: Task 7
- ✓ Knowledge page: Task 8
- ✓ Settings page: Task 9
- ✓ Admin page: Task 10
- ✓ Status dots with glow: Tasks 2, 4, 5, 6
- ✓ Animated live dot: Task 1 (CSS keyframe), Task 3 (applied)
- ✓ Build verification: Task 11

**No placeholders** — Tasks 7–10 say "read file first" which is intentional (files are large/unknown, exact replacements must be derived from actual content).

**Type consistency** — `STATUS_CONFIG` defined in Task 6 and referenced only in Task 6. Task 7 notes same pattern without copying the type (leads have different status values). No cross-task type references.
