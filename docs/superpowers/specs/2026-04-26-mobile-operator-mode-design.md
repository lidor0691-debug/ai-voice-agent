# Mobile Operator Mode — Design Spec

**Date:** 2026-04-26
**Status:** Draft
**Scope:** Mobile-only dashboard layout for screens below `md` (768px)

---

## Problem

After Wave 1 responsive fixes, the Maya dashboard scales to mobile screens but remains a compressed version of the desktop layout. SMB operators checking their phone want an action-first cockpit — not a shrunken command center.

## Goal

On screens below `md`, replace the desktop dashboard with a purpose-built mobile layout: an operator cockpit showing only what needs attention right now. Desktop must remain completely untouched.

## Non-Goals

- Bottom tab navigation (future phase)
- PWA / Add to Home Screen (future phase)
- Redesigning non-dashboard pages (leads, calls, agents, knowledge, settings)
- New API routes or data model changes
- Complex voice UI redesign

---

## Architecture

### Conditional Rendering Strategy

`DashboardClientPage` becomes a layout switcher:

```tsx
export function DashboardClientPage(props: Props) {
  return (
    <>
      {/* Mobile operator cockpit — phones only */}
      <div className="md:hidden">
        <MobileDashboard {...props} />
      </div>
      {/* Desktop — unchanged */}
      <div className="hidden md:block">
        {/* existing desktop JSX, moved here verbatim */}
      </div>
    </>
  );
}
```

Both branches receive the same server-fetched props. No data layer changes.

### Mobile Layout Stack (top to bottom)

```
┌──────────────────────────────┐
│ Header (hamburger + title)   │  ← already exists from Wave 1
├──────────────────────────────┤
│ KPI Strip                    │  3 compact inline stats
│ [🟢 3 Active] [📞 12] [👥 5]│  single horizontal row
├──────────────────────────────┤
│ 🔴 Today's Priorities (HERO)│  full-width stacked cards
│ ┌──────────────────────────┐ │  each card: type badge,
│ │ noshow — Sarah Cohen     │ │  lead name, description,
│ │ "התור היה ב-14:00..."    │ │  [Act] [Dismiss] buttons
│ │ [טפל]         [דחה]     │ │  min-h 44px touch targets
│ ├──────────────────────────┤ │
│ │ drop — Moshe Levi        │ │
│ │ "הלקוח שלח הודעה..."    │ │
│ │ [טפל]         [דחה]     │ │
│ └──────────────────────────┘ │
├──────────────────────────────┤
│ Recent Leads                 │  compact rows (max 5)
│ ┌──────────────────────────┐ │  name · masked phone · time
│ │ Sarah Cohen · 054••••21  │ │  tap → navigates to leads
│ │ Moshe Levi  · 052••••88  │ │  page with detail
│ └──────────────────────────┘ │
├──────────────────────────────┤
│ (content scroll ends)        │
│                              │
│ 🎙️ ─────────────────────── │  Maya FAB (fixed, bottom-start)
└──────────────────────────────┘
```

### What's Visible on Mobile

| Surface | Data Source | Purpose |
|---------|-----------|---------|
| KPI Strip (3 stats) | Props: `agents`, `calls` + client-side `/api/action-queue` count | Quick glance: active agents, today's calls, open priorities |
| Today's Priorities | Client-side fetch: `/api/action-queue` | HERO — act on conversion leaks |
| Recent Leads | Client-side fetch: `/api/leads?limit=5` | Quick access to latest leads |
| Maya FAB | `LiveVoicePanel` in bottom sheet | Voice assistant, always accessible |

### What's Hidden on Mobile

- Voice Activity chart (decorative)
- Agents list card (count is in KPI strip)
- Test Agent chat widget (needs keyboard + screen)
- Recent Calls feed (secondary to priorities)
- Lead Insights / Injection Events / Win Signals cards (analytics, not action)
- Full-size DashboardAssistant floating panel (FAB replaces it)

---

## Components

### 1. MobileDashboard

**File:** `components/mobile/mobile-dashboard.tsx`
**Responsibility:** Top-level mobile layout container. Receives same Props as DashboardClientPage. Renders KPI strip, priorities, leads, and FAB in a scrollable vertical stack.

```
Props: same as DashboardClientPage
  agents, calls, knowledgeCount, insights, injectionEvents, winSignals

Renders:
  <Header />                    ← reuses existing header
  <div scroll container>
    <MobileKpiStrip />
    <MobilePriorities />
    <MobileLeadList />
  </div>
  <MayaFab />                   ← fixed positioned, outside scroll
```

### 2. MobileKpiStrip

**File:** `components/mobile/mobile-kpi-strip.tsx`
**Responsibility:** Horizontal row of 3 compact stat pills.

**Stats shown:**
1. Active Agents — count from `agents.filter(a => a.is_active).length`
2. Today's Calls — count from `calls.length`
3. Open Priorities — count fetched from `/api/action-queue` (passed down from MobilePriorities or fetched independently)

**Design:**
- Single row, 3 equal-width pills
- Each pill: icon (small, 16px) + number (bold) + label (tiny, below)
- Compact: ~48px total height
- Background: `surface-1` card style
- No tap action in V1 (informational only)

**Props:**
```ts
interface MobileKpiStripProps {
  activeAgents: number;
  totalCalls: number;
  openPriorities: number;
}
```

### 3. MobilePriorities

**File:** `components/mobile/mobile-priorities.tsx`
**Responsibility:** Hero section — full-width stacked action cards for conversion leak signals. This is the most important mobile surface.

**Data:** Client-side fetch from `/api/action-queue` (same endpoint as existing `ActionQueueCard`).

**Card layout per signal:**
```
┌─────────────────────────────────┐
│ [type badge]  Lead Name         │
│                                 │
│ Description text (2 lines max)  │
│                                 │
│ ← Suggested action              │
│                                 │
│ [████ טפל ████]  [  דחה  ]     │
└─────────────────────────────────┘
```

**Behavior:**
- Cards stacked vertically, full width
- "טפל" (Act) button: full-width primary, min-h 44px
- "דחה" (Dismiss) button: secondary, min-h 44px
- Act triggers same flow as desktop: PATCH `/api/action-queue/[id]` + show ActionCard overlay
- Dismiss: optimistic removal + PATCH
- Empty state: green checkmark + "אין לידים שדורשים טיפול כרגע"
- Loading state: skeleton cards
- Max 10 signals shown (no pagination in V1)

**Props:**
```ts
interface MobilePrioritiesProps {
  agentId?: string;
  onPriorityCountChange?: (count: number) => void;
}
```

`onPriorityCountChange` lets MobileDashboard pass the count up to MobileKpiStrip without a second fetch.

### 4. MobileLeadList

**File:** `components/mobile/mobile-lead-list.tsx`
**Responsibility:** Compact list of recent leads. Quick-glance, not full management.

**Data:** Client-side fetch from `/api/leads?limit=5`.

**Row layout:**
```
┌─────────────────────────────────┐
│ [avatar]  Name       052••••88 │
│           3 hours ago    →     │
└─────────────────────────────────┘
```

**Behavior:**
- Each row is a `<Link>` to `/dashboard/leads` (the full leads page)
- Shows: lead name (or masked phone if no name), masked phone, relative time
- Avatar: first letter of name in a colored circle (same gradient pattern as agents)
- Max 5 leads
- "הצג הכל" (View All) link at bottom → `/dashboard/leads`
- Empty state: "אין לידים חדשים"
- Rows must be min-h 56px for comfortable tapping

**Props:**
```ts
interface MobileLeadListProps {
  // No props — fetches its own data
}
```

### 5. MayaFab

**File:** `components/mobile/maya-fab.tsx`
**Responsibility:** Floating action button for Maya voice assistant. Mobile only.

**Resting state (FAB):**
- Fixed position: `bottom-6 start-4` (bottom-left in LTR, bottom-right in RTL — uses logical `start` property so it auto-flips for RTL)
- Size: 56x56px circle
- Appearance: brand gradient background, white Mic icon (24px)
- Subtle glow shadow matching brand color
- z-index: 50 (above content, below sidebar drawer z-40... actually above — z-50)

**Expanded state (bottom sheet):**
- Tap FAB → sheet slides up from bottom
- Sheet height: ~40vh (max 320px)
- Contains: `LiveVoicePanel` component (mode="assistant"), reusing the existing component
- Sheet has rounded top corners, surface-1 background, border-top
- Backdrop: semi-transparent black overlay (same as sidebar backdrop)
- Close: tap backdrop, or tap X button in sheet header
- FAB hides when sheet is open

**Props:**
```ts
interface MayaFabProps {
  agentId: string | null;
}
```

If `agentId` is null, FAB is hidden (same behavior as desktop DashboardAssistant).

**State:**
- `sheetOpen: boolean` — local useState
- No global context needed

---

## Modifications to Existing Files

### DashboardClientPage.tsx

**Change:** Extract existing desktop JSX into a `DesktopDashboard` local component (or just wrap in a div). Add conditional mobile rendering.

```tsx
export function DashboardClientPage(props: Props) {
  return (
    <div className="flex-1 overflow-y-auto">
      <Header ... />
      {/* Mobile */}
      <div className="md:hidden">
        <MobileDashboard {...props} />
      </div>
      {/* Desktop */}
      <div className="hidden md:block">
        <div className="p-3 sm:p-5 space-y-4 bg-surface-0 min-h-full">
          {/* ... all existing desktop content unchanged ... */}
        </div>
      </div>
    </div>
  );
}
```

The Header is shared between both (it already adapts via Wave 1 hamburger). The split happens below the header.

### dashboard-assistant.tsx

**Change:** Add `hidden md:block` to the wrapper div so the full-size floating panel doesn't render on mobile (FAB replaces it).

```tsx
// Current:
<div className="fixed bottom-6 left-6 z-50 w-80 card ...">

// After:
<div className="fixed bottom-6 left-6 z-50 w-80 card ... hidden md:block">
```

### sidebar.tsx

**Change:** On mobile drawer, simplify navigation to 4 core items. Hide Knowledge and Settings from the mobile nav (operators rarely need these on phone).

Approach: accept a `compact` prop. When true, filter NAV_ITEMS to only Dashboard, Agents, Calls, Leads.

```tsx
export function Sidebar({ isAdmin = false, onNavigate, compact = false }: {
  isAdmin?: boolean;
  onNavigate?: () => void;
  compact?: boolean;
}) {
  // ...
  const items = compact
    ? NAV_ITEMS.filter(i => ["/dashboard", "/dashboard/agents", "/dashboard/calls", "/dashboard/leads"].includes(i.href))
    : NAV_ITEMS;
```

In `dashboard-shell.tsx`, the mobile drawer passes `compact`:
```tsx
<Sidebar isAdmin={isAdmin} onNavigate={close} compact />
```

Desktop sidebar remains unchanged (no `compact` prop).

---

## Data Flow

```
page.tsx (server)
  ├── fetches: agents, calls, knowledge, insights, injections, winSignals
  └── passes all to DashboardClientPage
        │
        ├── <md: MobileDashboard
        │     ├── MobileKpiStrip (computed from props + priority count callback)
        │     ├── MobilePriorities (fetches /api/action-queue client-side)
        │     ├── MobileLeadList (fetches /api/leads?limit=5 client-side)
        │     └── MayaFab → LiveVoicePanel (WebSocket to backend)
        │
        └── md+: Desktop layout (unchanged)
              ├── KPI cards, charts, agent list, test agent, calls feed
              ├── ActionQueueCard (fetches /api/action-queue)
              ├── LeadInsights, InjectionEvents, WinSignals
              └── DashboardAssistant (floating panel)
```

No new API routes. Mobile components reuse:
- `/api/action-queue` — GET open signals
- `/api/action-queue/[id]` — PATCH act/dismiss
- `/api/leads` — GET recent leads
- `/api/actions/send-whatsapp` — POST (via ActionCard, already exists)
- WebSocket `/ws/voice-browser` — Maya voice (via LiveVoicePanel)

---

## RTL / Hebrew Support

- All mobile components use `dir` from parent (set by DashboardShell)
- Text alignment inherits RTL from `dir="rtl"` on the shell
- FAB uses `start-4` (Tailwind logical property) → left in LTR, right in RTL. Actually we want bottom-left in LTR and center-bottom or bottom-left in RTL too. Use `left-4` explicitly since the user asked for bottom-left/center-bottom in RTL. Decision: `left-4` in LTR and RTL. This keeps it away from browser scroll UI on the right side. In RTL, `left` is the "end" side, which is fine — it avoids the iOS address bar and Android nav gestures on the right.
- Signal card text and buttons render RTL naturally (the ActionQueueCard already uses `dir="rtl"`)
- Lead names, phone masking — all existing utils handle Hebrew

**FAB Position Final Decision:** Fixed `bottom-6 left-4` regardless of direction. This avoids conflicts with iOS Safari bottom bar (right side) and Android gesture navigation (right edge). User explicitly requested bottom-left or center-bottom in RTL.

---

## Styling

All mobile components follow existing design tokens:
- Backgrounds: `bg-surface-0` (page), `bg-surface-1` (cards)
- Borders: `border-border`
- Text: `text-white` (primary), `text-gray-400`/`text-gray-500`/`text-gray-600` (secondary)
- Brand: `brand-500`, `brand-400`, gradient `from-brand-500 to-indigo-500`
- Card radius: `rounded-[14px]` (via `.card` class)
- Touch targets: minimum 44px height on all interactive elements
- Spacing: `p-4` card padding, `gap-3` between sections

---

## Testing Criteria

1. **Desktop unchanged** — md+ viewport renders identically to before this change
2. **Mobile layout renders** — <768px shows KPI strip, priorities, leads, FAB
3. **Priorities hero** — signals load, act/dismiss work, empty state shows
4. **Lead list** — 5 recent leads show, rows are tappable, "view all" navigates
5. **KPI strip** — 3 stats render with correct counts
6. **Maya FAB** — tap opens bottom sheet with voice panel, backdrop dismisses
7. **FAB hidden when no agent** — if `defaultAgentId` is null, no FAB
8. **RTL** — Hebrew mode renders correctly, FAB stays bottom-left
9. **Sidebar compact** — mobile drawer shows 4 items, desktop shows all 6
10. **No horizontal overflow** — no content wider than viewport on any mobile screen
