# Mobile Operator Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the desktop dashboard with a purpose-built mobile operator cockpit on screens below `md` (768px) — showing only actionable surfaces: priorities, leads, KPIs, and Maya voice FAB.

**Architecture:** Conditional rendering in `DashboardClientPage`: `md:hidden` renders `MobileDashboard`, `hidden md:block` wraps existing desktop. Five new components in `components/mobile/`. No API changes — mobile components reuse existing endpoints.

**Tech Stack:** Next.js, React, Tailwind CSS, Lucide icons. Reuses `LiveVoicePanel`, `ActionCard`, existing `/api/action-queue` and `/api/leads` endpoints.

**Spec:** `docs/superpowers/specs/2026-04-26-mobile-operator-mode-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `dashboard/components/mobile/mobile-kpi-strip.tsx` | Create | 3-stat horizontal strip: active agents, calls, open priorities |
| `dashboard/components/mobile/mobile-priorities.tsx` | Create | Hero action queue: full-width stacked signal cards, 44px touch targets. Same dismiss/act behavior as desktop ActionQueueCard |
| `dashboard/components/mobile/mobile-lead-list.tsx` | Create | Compact recent leads list (max 5), client-side fetch from /api/leads |
| `dashboard/components/mobile/maya-fab.tsx` | Create | Floating mic button (bottom-left fixed), expands to bottom sheet with LiveVoicePanel |
| `dashboard/components/mobile/mobile-dashboard.tsx` | Create | Container: assembles KPI strip + priorities + leads + FAB |
| `dashboard/app/dashboard/DashboardClientPage.tsx` | Modify | Wrap desktop in `hidden md:block`, add `md:hidden` mobile branch |
| `dashboard/components/dashboard/dashboard-assistant.tsx` | Modify | Add `hidden md:block` to hide desktop panel on mobile |
| `dashboard/components/layout/sidebar.tsx` | Modify | Add `compact` prop; when true, show only Dashboard/Agents/Calls/Leads |
| `dashboard/components/layout/dashboard-shell.tsx` | Modify | Pass `compact` to mobile drawer Sidebar |

## Implementation Order & Dependency Graph

```
Task 1: MobileKpiStrip      (standalone, no deps)
Task 2: MobilePriorities    (standalone, no deps — reuses ActionCard)
Task 3: MobileLeadList      (standalone, no deps)
Task 4: MayaFab             (standalone — wraps LiveVoicePanel)
Task 5: MobileDashboard     (depends on Tasks 1-4)
Task 6: Wire into DashboardClientPage + hide desktop assistant + compact sidebar
```

Tasks 1-4 are independent and can be built in any order or in parallel. Task 5 assembles them. Task 6 wires everything in.

## Build Risks

| Risk | Mitigation |
|------|-----------|
| LiveVoicePanel has `p-8 max-w-lg` and `py-8` padding — will overflow in a 320px bottom sheet | MayaFab wraps it in a constrained `max-h-[40vh] overflow-y-auto` container and overrides inner padding via wrapper |
| `/api/leads` returns up to 200 leads — wasteful for 5-item mobile list | Acceptable for V1: client slices to 5. Future: add `?limit=5` query param support |
| ActionCard overlay renders inline in MobilePriorities — could cause scroll jump | ActionCard already uses `mt-4` inline positioning; on mobile fullscreen priority list this is fine |
| Tailwind `hidden md:block` on DashboardAssistant could cause flash on hydration | Tailwind classes are CSS-based (no JS), so no hydration flash |
| Sidebar compact prop changes visible items — may confuse users who expect Knowledge/Settings | Spec decision: Knowledge/Settings are desktop tasks. Mobile drawer shows 4 core items only |

---

## Task 1: MobileKpiStrip

**Files:**
- Create: `dashboard/components/mobile/mobile-kpi-strip.tsx`

- [ ] **Step 1: Create the component file**

Create `dashboard/components/mobile/mobile-kpi-strip.tsx`:

```tsx
"use client";

import { Users, Phone, AlertTriangle } from "lucide-react";

interface Props {
  activeAgents: number;
  totalCalls: number;
  openPriorities: number;
}

export function MobileKpiStrip({ activeAgents, totalCalls, openPriorities }: Props) {
  const stats = [
    { label: "סוכנים פעילים", value: activeAgents, icon: Users, color: "#a78bfa", bg: "rgba(139,92,246,0.15)" },
    { label: "שיחות", value: totalCalls, icon: Phone, color: "#10b981", bg: "rgba(16,185,129,0.12)" },
    { label: "דורש טיפול", value: openPriorities, icon: AlertTriangle, color: "#ef4444", bg: "rgba(239,68,68,0.12)" },
  ];

  return (
    <div className="grid grid-cols-3 gap-2" dir="rtl">
      {stats.map(({ label, value, icon: Icon, color, bg }) => (
        <div
          key={label}
          className="card px-3 py-2.5 flex flex-col items-center gap-1"
        >
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: bg }}
          >
            <Icon className="w-3.5 h-3.5" style={{ color }} />
          </div>
          <p className="text-white text-lg font-bold leading-none">{value}</p>
          <p className="text-gray-500 text-[9px] leading-none text-center">{label}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd dashboard && npx next build 2>&1 | tail -5`

This won't be used yet (no imports), but confirms no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/mobile/mobile-kpi-strip.tsx
git commit -m "feat: add MobileKpiStrip component"
```

---

## Task 2: MobilePriorities

**Files:**
- Create: `dashboard/components/mobile/mobile-priorities.tsx`

This component replicates the data-fetching and status-update behavior of `dashboard/components/dashboard/action-queue-card.tsx` but with a mobile-optimized layout. Key constraint: **same status update behavior as desktop** — dismiss = PATCH `dismissed`, act = PATCH `acted` + open ActionCard overlay (no auto-send).

- [ ] **Step 1: Create the component file**

Create `dashboard/components/mobile/mobile-priorities.tsx`:

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { CalendarX, MessageSquareOff, AlertTriangle, Loader2, Check } from "lucide-react";
import { ActionCard, type ActionProposal } from "@/components/dashboard/action-card";

interface Signal {
  id: string;
  created_at: string;
  lead_id: string;
  lead_phone: string;
  lead_name: string | null;
  signal_type: string;
  detail: Record<string, unknown>;
  suggested_action: string | null;
  status: string;
}

const SIGNAL_CONFIG: Record<string, { icon: typeof CalendarX; color: string; bg: string; label: string }> = {
  noshow_not_reactivated: {
    icon: CalendarX,
    color: "#ef4444",
    bg: "rgba(239,68,68,0.1)",
    label: "לא הגיע/ה לתור",
  },
  conversation_drop: {
    icon: MessageSquareOff,
    color: "#f59e0b",
    bg: "rgba(245,158,11,0.1)",
    label: "הודעה ללא מענה",
  },
};

function maskPhone(phone: string): string {
  if (phone.length < 8) return phone;
  return phone.slice(0, 4) + "••••" + phone.slice(-3);
}

function signalDescription(signal: Signal): string {
  const detail = signal.detail;
  if (signal.signal_type === "noshow_not_reactivated") {
    const appt = detail.appointment_at as string | undefined;
    if (appt) {
      try {
        const d = new Date(appt);
        const formatted = d.toLocaleDateString("he-IL", { day: "numeric", month: "numeric" })
          + " " + d.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
        return `התור היה ב-${formatted} ולא בוצע מעקב`;
      } catch { /* fall through */ }
    }
    return "לא הגיע/ה לתור ולא בוצע מעקב";
  }
  if (signal.signal_type === "conversation_drop") {
    const hours = detail.hours_since as number | undefined;
    const preview = detail.last_customer_message as string | undefined;
    let text = "הלקוח/ה שלח/ה הודעה ולא קיבל/ה מענה";
    if (hours) text += ` (לפני ${hours} שעות)`;
    if (preview) text += `: "${preview.slice(0, 50)}${preview.length > 50 ? "..." : ""}"`;
    return text;
  }
  return signal.suggested_action ?? "";
}

interface Props {
  agentId?: string;
  onCountChange?: (count: number) => void;
}

export function MobilePriorities({ agentId, onCountChange }: Props) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeProposal, setActiveProposal] = useState<ActionProposal | null>(null);

  const fetchSignals = useCallback(async () => {
    try {
      const res = await fetch("/api/action-queue");
      if (!res.ok) return;
      const data = await res.json();
      const sigs = data.signals ?? [];
      setSignals(sigs);
      onCountChange?.(sigs.length);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [onCountChange]);

  useEffect(() => { fetchSignals(); }, [fetchSignals]);

  const handleDismiss = async (id: string) => {
    setSignals((prev) => {
      const next = prev.filter((s) => s.id !== id);
      onCountChange?.(next.length);
      return next;
    });
    try {
      await fetch(`/api/action-queue/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "dismissed" }),
      });
    } catch { /* silent — already removed from UI */ }
  };

  const handleAct = (signal: Signal) => {
    if (!agentId) return;
    setSignals((prev) => {
      const next = prev.filter((s) => s.id !== signal.id);
      onCountChange?.(next.length);
      return next;
    });
    setActiveProposal({
      action: "whatsapp_followup",
      status: "pending",
      agent_id: agentId,
      lead_id: signal.lead_id,
      lead_name: signal.lead_name ?? maskPhone(signal.lead_phone),
      channel: "whatsapp",
      message: signal.suggested_action ?? "",
    });
    fetch(`/api/action-queue/${signal.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "acted" }),
    }).catch(() => {});
  };

  const count = signals.length;

  return (
    <div className="space-y-3" dir="rtl">
      {/* Section header */}
      <div className="flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-brand-400" />
        <p className="text-white text-sm font-semibold">סדר עדיפויות להיום</p>
        {count > 0 && (
          <span
            className="text-[10px] font-bold px-1.5 py-0.5 rounded-full"
            style={{ color: "#ef4444", background: "rgba(239,68,68,0.15)" }}
          >
            {count}
          </span>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="card flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
        </div>
      )}

      {/* Empty state */}
      {!loading && count === 0 && (
        <div className="card flex items-center justify-center gap-2 py-8">
          <Check className="w-5 h-5 text-green-500" />
          <p className="text-gray-400 text-sm">אין לידים שדורשים טיפול כרגע</p>
        </div>
      )}

      {/* Signal cards */}
      {!loading && count > 0 && (
        <div className="flex flex-col gap-3">
          {signals.slice(0, 10).map((signal) => {
            const cfg = SIGNAL_CONFIG[signal.signal_type] ?? {
              icon: AlertTriangle,
              color: "#94a3b8",
              bg: "rgba(148,163,184,0.1)",
              label: signal.signal_type,
            };
            const Icon = cfg.icon;

            return (
              <div
                key={signal.id}
                className="card p-4"
              >
                {/* Type badge + lead info */}
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded"
                    style={{ color: cfg.color, background: cfg.bg }}
                  >
                    <Icon className="w-3 h-3" />
                    {cfg.label}
                  </span>
                  <span className="text-white text-sm font-medium">
                    {signal.lead_name ?? maskPhone(signal.lead_phone)}
                  </span>
                </div>

                {signal.lead_name && (
                  <p className="text-gray-600 text-xs mb-1">
                    {maskPhone(signal.lead_phone)}
                  </p>
                )}

                {/* Description */}
                <p className="text-gray-400 text-xs leading-relaxed mb-2 line-clamp-2">
                  {signalDescription(signal)}
                </p>

                {/* Suggested action */}
                {signal.suggested_action && (
                  <p className="text-gray-500 text-[11px] mb-3 flex items-start gap-1.5">
                    <span className="text-brand-400 flex-shrink-0">←</span>
                    {signal.suggested_action}
                  </p>
                )}

                {/* Action buttons — full width, touch-friendly */}
                <div className="flex gap-2">
                  <button
                    onClick={() => handleAct(signal)}
                    className="flex-1 flex items-center justify-center gap-1.5 min-h-[44px] bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium rounded-xl transition-colors"
                    disabled={!agentId}
                  >
                    טפל
                  </button>
                  <button
                    onClick={() => handleDismiss(signal.id)}
                    className="flex-1 flex items-center justify-center min-h-[44px] text-gray-400 hover:text-gray-200 text-sm rounded-xl border border-border hover:bg-surface-3 transition-colors"
                  >
                    דחה
                  </button>
                </div>
              </div>
            );
          })}
          {count > 10 && (
            <p className="text-gray-600 text-xs text-center">
              +{count - 10} נוספים
            </p>
          )}
        </div>
      )}

      {/* ActionCard overlay — same behavior as desktop */}
      {activeProposal && (
        <ActionCard
          proposal={activeProposal}
          onDismiss={() => setActiveProposal(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd dashboard && npx next build 2>&1 | tail -5`

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/mobile/mobile-priorities.tsx
git commit -m "feat: add MobilePriorities component — hero action queue for mobile"
```

---

## Task 3: MobileLeadList

**Files:**
- Create: `dashboard/components/mobile/mobile-lead-list.tsx`

- [ ] **Step 1: Create the component file**

Create `dashboard/components/mobile/mobile-lead-list.tsx`:

```tsx
"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Users, ArrowRight, Loader2 } from "lucide-react";
import type { SupabaseLead } from "@/types/lead";

const AVATAR_GRADIENTS = [
  "linear-gradient(135deg, #8b5cf6, #6366f1)",
  "linear-gradient(135deg, #3b82f6, #06b6d4)",
  "linear-gradient(135deg, #10b981, #14b8a6)",
  "linear-gradient(135deg, #f59e0b, #ef4444)",
  "linear-gradient(135deg, #ec4899, #a855f7)",
];

function maskPhone(phone: string): string {
  if (phone.length < 8) return phone;
  return phone.slice(0, 4) + "••••" + phone.slice(-3);
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "עכשיו";
  if (mins < 60) return `לפני ${mins} דק׳`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `לפני ${hours} שע׳`;
  const days = Math.floor(hours / 24);
  return `לפני ${days} ימים`;
}

export function MobileLeadList() {
  const [leads, setLeads] = useState<SupabaseLead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/leads");
        if (!res.ok) return;
        const data = await res.json();
        setLeads((data.leads ?? []).slice(0, 5));
      } catch { /* silent */ }
      finally { setLoading(false); }
    })();
  }, []);

  return (
    <div className="space-y-3" dir="rtl">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-brand-400" />
          <p className="text-white text-sm font-semibold">לידים אחרונים</p>
        </div>
        <Link
          href="/dashboard/leads"
          className="text-brand-400 text-xs flex items-center gap-1 hover:text-brand-300 transition-colors"
        >
          הצג הכל <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      {/* Loading */}
      {loading && (
        <div className="card flex items-center justify-center py-6">
          <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
        </div>
      )}

      {/* Empty */}
      {!loading && leads.length === 0 && (
        <div className="card flex items-center justify-center py-6">
          <p className="text-gray-500 text-sm">אין לידים חדשים</p>
        </div>
      )}

      {/* Lead rows */}
      {!loading && leads.length > 0 && (
        <div className="card overflow-hidden divide-y divide-border">
          {leads.map((lead, i) => {
            const displayName = lead.name || maskPhone(lead.phone);
            const initial = (lead.name ?? lead.phone)[0]?.toUpperCase() ?? "?";
            const gradient = AVATAR_GRADIENTS[i % AVATAR_GRADIENTS.length];

            return (
              <Link
                key={lead.id}
                href="/dashboard/leads"
                className="flex items-center gap-3 px-4 py-3 min-h-[56px] hover:bg-surface-3 transition-colors"
              >
                {/* Avatar */}
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                  style={{ background: gradient }}
                >
                  {initial}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">{displayName}</p>
                  <p className="text-gray-500 text-[11px]">{relativeTime(lead.created_at)}</p>
                </div>

                {/* Phone */}
                <span className="text-gray-600 text-xs flex-shrink-0">
                  {maskPhone(lead.phone)}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd dashboard && npx next build 2>&1 | tail -5`

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/mobile/mobile-lead-list.tsx
git commit -m "feat: add MobileLeadList component — recent leads for mobile"
```

---

## Task 4: MayaFab

**Files:**
- Create: `dashboard/components/mobile/maya-fab.tsx`

Key constraint: LiveVoicePanel has generous padding (`p-8`, `py-8`, `max-w-lg`). The bottom sheet must constrain it to `max-h-[40vh]` with `overflow-y-auto` so it doesn't overflow on small screens.

- [ ] **Step 1: Create the component file**

Create `dashboard/components/mobile/maya-fab.tsx`:

```tsx
"use client";

import { useState, useCallback } from "react";
import { Mic, X } from "lucide-react";
import { LiveVoicePanel } from "@/components/agents/live-voice-panel";
import { ActionCard, type ActionProposal } from "@/components/dashboard/action-card";

interface Props {
  agentId: string | null;
}

export function MayaFab({ agentId }: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [activeProposal, setActiveProposal] = useState<ActionProposal | null>(null);

  const handleActionProposal = useCallback((proposal: ActionProposal) => {
    setActiveProposal(proposal);
  }, []);

  if (!agentId) return null;

  return (
    <>
      {/* FAB button — fixed bottom-left */}
      {!sheetOpen && (
        <button
          onClick={() => setSheetOpen(true)}
          className="fixed bottom-6 left-4 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-brand-500 to-indigo-500 flex items-center justify-center shadow-lg hover:shadow-xl transition-shadow"
          style={{ boxShadow: "0 4px 20px rgba(139,92,246,0.4)" }}
          aria-label="Talk to Maya"
        >
          <Mic className="w-6 h-6 text-white" />
        </button>
      )}

      {/* Bottom sheet overlay */}
      {sheetOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-50 bg-black/50"
            onClick={() => setSheetOpen(false)}
          />

          {/* Sheet */}
          <div className="fixed bottom-0 left-0 right-0 z-50 bg-surface-1 border-t border-border rounded-t-2xl" dir="rtl">
            {/* Sheet header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-brand-500 to-indigo-500 flex items-center justify-center">
                  <Mic className="w-3 h-3 text-white" />
                </div>
                <span className="text-white text-sm font-medium">דבר עם מאיה</span>
              </div>
              <button
                onClick={() => setSheetOpen(false)}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-white hover:bg-surface-3 transition-colors"
                aria-label="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Voice panel — constrained height, override inner padding */}
            <div className="max-h-[40vh] overflow-y-auto [&>div]:p-4 [&>div]:py-4 [&>div>div]:max-w-none">
              <LiveVoicePanel
                agentId={agentId}
                mode="assistant"
                onActionProposal={handleActionProposal}
              />
            </div>

            {/* ActionCard overlay if Maya proposes an action */}
            {activeProposal && (
              <div className="px-4 pb-4">
                <ActionCard
                  proposal={activeProposal}
                  onDismiss={() => setActiveProposal(null)}
                />
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
```

**Note on LiveVoicePanel override:** The `[&>div]:p-4 [&>div]:py-4 [&>div>div]:max-w-none` Tailwind arbitrary selectors override the panel's `p-8` and `max-w-lg` classes. The `max-h-[40vh] overflow-y-auto` ensures the sheet never takes more than 40% of the viewport. If these CSS overrides don't work cleanly (e.g., the specificity doesn't win), the fallback is to add a simple wrapper div with `!p-4` and test.

- [ ] **Step 2: Verify it builds**

Run: `cd dashboard && npx next build 2>&1 | tail -5`

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/mobile/maya-fab.tsx
git commit -m "feat: add MayaFab — floating voice button with bottom sheet"
```

---

## Task 5: MobileDashboard Container

**Files:**
- Create: `dashboard/components/mobile/mobile-dashboard.tsx`

- [ ] **Step 1: Create the component file**

Create `dashboard/components/mobile/mobile-dashboard.tsx`:

```tsx
"use client";

import { useState, useCallback } from "react";
import { MobileKpiStrip } from "./mobile-kpi-strip";
import { MobilePriorities } from "./mobile-priorities";
import { MobileLeadList } from "./mobile-lead-list";
import { MayaFab } from "./maya-fab";
import type { AgentConfig, CallLog } from "@/types/database";

interface Props {
  agents: Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null;
  calls: Pick<CallLog, "id" | "status" | "created_at">[] | null;
  defaultAgentId: string | null;
}

export function MobileDashboard({ agents, calls, defaultAgentId }: Props) {
  const activeAgents = agents?.filter((a) => a.is_active).length ?? 0;
  const totalCalls = calls?.length ?? 0;
  const [openPriorities, setOpenPriorities] = useState(0);

  const handleCountChange = useCallback((count: number) => {
    setOpenPriorities(count);
  }, []);

  return (
    <>
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-surface-0">
        {/* KPI Strip */}
        <MobileKpiStrip
          activeAgents={activeAgents}
          totalCalls={totalCalls}
          openPriorities={openPriorities}
        />

        {/* Hero: Today's Priorities */}
        <MobilePriorities
          agentId={agents?.[0]?.id}
          onCountChange={handleCountChange}
        />

        {/* Recent Leads */}
        <MobileLeadList />

        {/* Bottom spacer for FAB clearance */}
        <div className="h-20" />
      </div>

      {/* Maya Voice FAB — fixed, outside scroll */}
      <MayaFab agentId={defaultAgentId} />
    </>
  );
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd dashboard && npx next build 2>&1 | tail -5`

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/mobile/mobile-dashboard.tsx
git commit -m "feat: add MobileDashboard container — assembles mobile cockpit"
```

---

## Task 6: Wire Into Dashboard + Hide Desktop Assistant + Compact Sidebar

**Files:**
- Modify: `dashboard/app/dashboard/DashboardClientPage.tsx`
- Modify: `dashboard/components/dashboard/dashboard-assistant.tsx:57`
- Modify: `dashboard/components/layout/sidebar.tsx:14`
- Modify: `dashboard/components/layout/dashboard-shell.tsx:41`

- [ ] **Step 1: Modify DashboardClientPage — add mobile branch**

In `dashboard/app/dashboard/DashboardClientPage.tsx`:

Add import at the top (after the existing imports, around line 10):

```tsx
import { MobileDashboard } from "@/components/mobile/mobile-dashboard";
```

Replace the return statement (lines 71-291). The new return wraps the existing desktop content in `hidden md:block` and adds a `md:hidden` mobile branch. The Header is shared:

```tsx
  return (
    <div className="flex-1 overflow-y-auto">
      <Header title={t.page_dashboard_title} subtitle={t.page_dashboard_subtitle} />

      {/* Mobile operator cockpit */}
      <div className="md:hidden">
        <MobileDashboard
          agents={agents}
          calls={calls}
          defaultAgentId={agents?.[0]?.id ?? null}
        />
      </div>

      {/* Desktop dashboard — unchanged */}
      <div className="hidden md:block">
        <div className="p-3 sm:p-5 space-y-4 bg-surface-0 min-h-full">

          {/* KPI Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {kpiCards.map(({ label, value, icon: Icon, color, bg, glow, delta, up }) => (
              <div
                key={label}
                className="relative card p-4 flex items-center gap-3 overflow-hidden"
                style={{ ["--kpi-glow" as string]: glow }}
              >
                <div
                  className="absolute inset-0 pointer-events-none rounded-[14px]"
                  style={{ background: `radial-gradient(ellipse at top right, ${glow} 0%, transparent 60%)` }}
                />
                <div
                  className="w-9 h-9 rounded-[10px] flex items-center justify-center flex-shrink-0"
                  style={{ background: bg, color }}
                >
                  <Icon className="w-4 h-4" style={{ stroke: color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-2xl font-extrabold text-white tracking-tight leading-none">{value}</p>
                  <p className="text-gray-600 text-[10px] mt-1">{label}</p>
                </div>
                <span
                  className="text-[9px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0"
                  style={up
                    ? { color: "#10b981", background: "rgba(16,185,129,0.1)" }
                    : { color: "#f59e0b", background: "rgba(245,158,11,0.1)" }
                  }
                >
                  {delta}
                </span>
              </div>
            ))}
          </div>

          {/* Main 3-column grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" style={{ minHeight: 0 }}>

            {/* Col 1: Voice Activity Chart */}
            <div className="card p-4 hidden md:flex flex-col">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-white text-[13px] font-semibold">פעילות קולית — 24 שעות</p>
                  <p className="text-gray-600 text-[10px] mt-0.5">שיחות לפי שעה</p>
                </div>
                <Link href="/dashboard/calls" className="text-brand-400 text-[10px] flex items-center gap-1 hover:text-brand-300 transition-colors">
                  הצג הכל <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              <div className="flex items-end gap-[3px] flex-1" style={{ minHeight: 120 }}>
                {CHART_BARS.map(({ h, cls }, i) => (
                  <div
                    key={i}
                    className="flex-1"
                    style={{ height: `${h}%`, borderRadius: "3px 3px 0 0", ...
                      cls === "peak"
                        ? { background: "linear-gradient(180deg,#a78bfa,rgba(139,92,246,0.6))", boxShadow: "0 -4px 12px rgba(139,92,246,0.3)" }
                        : cls === "hi"
                        ? { background: "linear-gradient(180deg,#8b5cf6,rgba(139,92,246,0.4))" }
                        : { background: "rgba(139,92,246,0.2)" }
                    }}
                  />
                ))}
              </div>
              <div className="flex justify-between mt-2">
                {["00:00","06:00","09:00","12:00","15:00","18:00","21:00"].map((l) => (
                  <span key={l} className="text-[8px] text-gray-700">{l}</span>
                ))}
              </div>
            </div>

            {/* Col 2: Agents List */}
            <div className="card p-4 flex flex-col">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-white text-[13px] font-semibold">{t.your_agents}</p>
                  <p className="text-gray-600 text-[10px] mt-0.5">
                    {activeAgents} מתוך {totalAgents} פעילים
                  </p>
                </div>
                <Link href="/dashboard/agents" className="text-brand-400 text-[10px] flex items-center gap-1 hover:text-brand-300 transition-colors">
                  נהל <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              <div className="flex flex-col gap-1.5 flex-1">
                {!agents?.length ? (
                  <div className="flex-1 flex flex-col items-center justify-center text-center py-8">
                    <p className="text-gray-600 text-[11px]">{t.no_agents_yet}</p>
                    <Link href="/dashboard/agents/new" className="mt-3 btn-primary flex items-center gap-1.5 text-[11px] px-3 py-1.5">
                      <Plus className="w-3 h-3" /> {t.new_agent_btn}
                    </Link>
                  </div>
                ) : (
                  agents.slice(0, 5).map((agent, i) => {
                    const grad = AGENT_GRADIENTS[i % AGENT_GRADIENTS.length];
                    return (
                      <Link
                        key={agent.id}
                        href={`/dashboard/agents/${agent.id}`}
                        className="flex items-center gap-2.5 px-2.5 py-2 rounded-[10px] border border-border hover:bg-surface-3 transition-all group"
                        style={{ background: "rgba(255,255,255,0.02)" }}
                      >
                        <div
                          className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0"
                          style={{ background: `linear-gradient(135deg,${grad.c1},${grad.c2})` }}
                        >
                          {agent.agent_name.charAt(0).toUpperCase()}
                        </div>
                        <span className="text-gray-300 text-[12px] font-medium flex-1 group-hover:text-white transition-colors truncate">
                          {agent.agent_name}
                        </span>
                        <span className="text-gray-600 text-[10px]">
                          {agent.phone_number ?? "—"}
                        </span>
                        <span
                          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={agent.is_active
                            ? { background: "#10b981", boxShadow: "0 0 6px #10b981" }
                            : { background: "#334155" }
                          }
                        />
                      </Link>
                    );
                  })
                )}
              </div>
            </div>

            {/* Col 3: Chat + Recent Calls */}
            <div className="flex flex-col gap-4">
              <div className="card overflow-hidden flex-1 hidden md:block">
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

              <div className="card p-4">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-white text-[13px] font-semibold">{t.kpi_recent_calls}</p>
                  <Link href="/dashboard/calls" className="text-brand-400 text-[10px] flex items-center gap-1 hover:text-brand-300 transition-colors">
                    {t.view_all} <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
                {recentCalls.length === 0 ? (
                  <p className="text-gray-700 text-[11px] text-center py-3">{t.no_calls_yet}</p>
                ) : (
                  <div className="flex flex-col gap-1">
                    {recentCalls.map((call) => (
                      <div
                        key={call.id}
                        className="flex items-center gap-2 px-2.5 py-2 rounded-lg"
                        style={{
                          background: "rgba(255,255,255,0.02)",
                          borderRight: `2px solid ${
                            call.status === "completed" ? "#10b981"
                            : call.status === "missed"  ? "#f59e0b"
                            : "#ef4444"
                          }`,
                        }}
                      >
                        <span className="text-gray-600 text-[9px] w-8 flex-shrink-0">
                          {new Date(call.created_at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}
                        </span>
                        <span className="flex-1 text-gray-500 text-[10px] truncate">
                          {new Date(call.created_at).toLocaleDateString("he-IL", { month: "short", day: "numeric" })}
                        </span>
                        <span className="text-gray-600 text-[9px]">—</span>
                        <span
                          className="text-[8.5px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0"
                          style={
                            call.status === "completed"
                              ? { color: "#10b981", background: "rgba(16,185,129,0.1)" }
                              : call.status === "missed"
                              ? { color: "#f59e0b", background: "rgba(245,158,11,0.1)" }
                              : { color: "#ef4444", background: "rgba(239,68,68,0.1)" }
                          }
                        >
                          {call.status === "completed" ? t.status_completed
                            : call.status === "missed" ? t.status_missed
                            : t.status_failed}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

          </div>

          {/* Action Queue — Daily Priorities */}
          <ActionQueueCard agentId={agents?.[0]?.id} />

          {/* Lead Intelligence */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <LeadInsightsCard insights={insights} />
            <InjectionEventsCard events={injectionEvents} />
            <WinSignalsCard signals={winSignals} />
          </div>

        </div>
      </div>
    </div>
  );
```

- [ ] **Step 2: Hide DashboardAssistant on mobile**

In `dashboard/components/dashboard/dashboard-assistant.tsx`, line 57, change:

```tsx
<div className="fixed bottom-6 left-6 z-50 w-80 card p-4 shadow-2xl border border-border/50 rounded-2xl bg-surface-1/95 backdrop-blur">
```

to:

```tsx
<div className="fixed bottom-6 left-6 z-50 w-80 card p-4 shadow-2xl border border-border/50 rounded-2xl bg-surface-1/95 backdrop-blur hidden md:block">
```

- [ ] **Step 3: Add compact prop to Sidebar**

In `dashboard/components/layout/sidebar.tsx`, line 14, change:

```tsx
export function Sidebar({ isAdmin = false, onNavigate }: { isAdmin?: boolean; onNavigate?: () => void }) {
```

to:

```tsx
export function Sidebar({ isAdmin = false, onNavigate, compact = false }: { isAdmin?: boolean; onNavigate?: () => void; compact?: boolean }) {
```

Then at line 32, where `NAV_ITEMS` is defined, add filtering right after the array definition. After line 39, add:

```tsx
  const MOBILE_HREFS = ["/dashboard", "/dashboard/agents", "/dashboard/calls", "/dashboard/leads"];
  const visibleItems = compact ? NAV_ITEMS.filter((item) => MOBILE_HREFS.includes(item.href)) : NAV_ITEMS;
```

Then at line 58, change the `.map` to use `visibleItems` instead of `NAV_ITEMS`:

```tsx
        {visibleItems.map(({ href, label, icon: Icon }) => {
```

- [ ] **Step 4: Pass compact to mobile drawer**

In `dashboard/components/layout/dashboard-shell.tsx`, line 41, change:

```tsx
          <Sidebar isAdmin={isAdmin} onNavigate={close} />
```

to:

```tsx
          <Sidebar isAdmin={isAdmin} onNavigate={close} compact />
```

- [ ] **Step 5: Verify build**

Run: `cd dashboard && npx next build 2>&1 | tail -5`
Expected: Build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app/dashboard/DashboardClientPage.tsx dashboard/components/dashboard/dashboard-assistant.tsx dashboard/components/layout/sidebar.tsx dashboard/components/layout/dashboard-shell.tsx
git commit -m "feat: wire mobile operator mode — conditional layout, compact sidebar, hide desktop assistant"
```

---

## Build Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| LiveVoicePanel inner `p-8` overrides may not work with Tailwind `[&>div]` selectors | Medium | If padding override fails, add explicit wrapper div with `style={{ padding: '16px' }}` as fallback |
| MobileDashboard creates second scroll context inside flex-1 parent | Low | Tested pattern — `flex-1 overflow-y-auto` inside `flex flex-col` works correctly |
| Two simultaneous fetches to `/api/action-queue` (MobilePriorities) and `/api/leads` (MobileLeadList) on mobile load | Low | Both are lightweight queries, acceptable for V1 |
| ActionCard overlay inline in MobilePriorities may get cut off if card is near bottom of scroll | Low | User can scroll to see it; ActionCard uses `mt-4` which keeps it visible |
| `hidden md:block` on DashboardAssistant means FAB and desktop panel can't coexist at md breakpoint | None | They're mutually exclusive: FAB is in `md:hidden` MobileDashboard, panel is in `hidden md:block` shell |

---

## Manual Mobile QA Checklist

Test on a real phone (or Chrome DevTools at 375px / 390px width).

### Layout & Navigation
- [ ] Mobile dashboard shows KPI strip + Priorities + Leads (no desktop content visible)
- [ ] Desktop dashboard (resize to 800px+) looks identical to before — no visual changes
- [ ] Hamburger menu opens sidebar drawer with 4 items (Dashboard, Agents, Calls, Leads)
- [ ] Knowledge and Settings links are NOT in mobile sidebar
- [ ] Desktop sidebar shows all 6 items
- [ ] Tapping a sidebar link closes drawer and navigates

### KPI Strip
- [ ] 3 stats show in a single row: active agents, calls, open priorities
- [ ] Priority count updates when you act on or dismiss a signal

### Today's Priorities (Hero)
- [ ] Signals load from API and display as full-width cards
- [ ] Each card shows type badge, lead name, description, suggested action
- [ ] "טפל" (Act) button: min-h 44px, tappable, opens ActionCard overlay
- [ ] ActionCard shows message, edit, send, cancel buttons (same as desktop)
- [ ] Act does NOT auto-send — user must tap "שלח עכשיו" in ActionCard
- [ ] "דחה" (Dismiss) button: removes card, PATCHes status to "dismissed"
- [ ] Empty state shows green check + "אין לידים שדורשים טיפול כרגע"
- [ ] Max 10 signals shown

### Recent Leads
- [ ] 5 recent leads show with name, phone (masked), relative time
- [ ] Each row is tappable (min-h 56px) and navigates to /dashboard/leads
- [ ] "הצג הכל" link works
- [ ] Empty state: "אין לידים חדשים"

### Maya FAB
- [ ] Purple mic button visible at bottom-left (fixed position)
- [ ] FAB doesn't overlap any content when scrolling
- [ ] Tapping FAB opens bottom sheet with Maya voice panel
- [ ] Bottom sheet has max-h ~40vh, doesn't overflow screen
- [ ] Backdrop tap closes sheet
- [ ] X button closes sheet
- [ ] Voice panel works: tap "דבר עם מאיה", mic activates
- [ ] FAB is hidden when sheet is open
- [ ] FAB is completely hidden if no agent is configured
- [ ] Desktop floating assistant panel is NOT visible on mobile

### RTL (Hebrew)
- [ ] Switch to Hebrew — all text renders RTL
- [ ] FAB stays at bottom-left (not flipped to right)
- [ ] Sidebar drawer slides from right in RTL
- [ ] Priority cards, lead rows, KPI strip all render correctly in RTL

### No Overflow
- [ ] No horizontal scroll on any mobile screen
- [ ] Content doesn't extend beyond viewport width
- [ ] FAB doesn't cause horizontal overflow
