# Maya AI Dashboard — Full Redesign Spec

**Date:** 2026-04-15  
**Status:** Approved for implementation  
**Scope:** All dashboard pages — full visual overhaul

---

## 1. Design Direction

**Style:** Dark premium SaaS — inspired by approved mockup (`maya-hifi.html`)  
**Palette:**
- Background: `#05050d` (deep near-black)
- Surface 1: `#0c0c18`
- Surface 2: `#111122`
- Border: `rgba(255,255,255,0.06)`
- Accent: `#8b5cf6` (violet-500) with glow `rgba(139,92,246,0.15)`
- Accent secondary: `#6366f1` (indigo-500)
- Text: `#f8fafc`
- Muted: `#94a3b8`
- Dim: `#334155`
- Success/live: `#10b981`
- Warning: `#f59e0b`
- Error: `#ef4444`

**Typography:** Inter — weights 400/500/600/700/800  
**Border radius:** 14px panels, 10px rows/inputs, 8px buttons  
**Shadows:** `0 40px 80px rgba(0,0,0,0.6)` outer frame; subtle radial glow per KPI card

---

## 2. Layout Architecture

### Global Shell

```
┌─────────────────────────────────────────────┐
│  Sidebar (220px) │  Topbar (56px, full-width) │
│                  ├────────────────────────────│
│  nav items       │  Page content              │
│                  │                            │
│  [footer: user]  │                            │
└─────────────────────────────────────────────┘
```

**Sidebar (220px, fixed):**
- Brand logo: violet gradient icon + "MayaAI" wordmark
- Nav items: icon + label, active state = violet tint bg + right-side violet bar indicator + border
- Footer: user avatar (gradient), name, role, green status dot
- Admin link: appears only for `isAdmin=true` users — same style as nav items (no visual distinction)

**Topbar (56px):**
- Left: page title (bold) + subtitle (muted)
- Right: search input, live status chip (animated green dot), primary CTA button

**Content area:** `background: #05050d`, padding `20px 24px`, scrollable

---

## 3. Shared Components

### KPI Card
- `background: surface-1`, `border-radius: 14px`, subtle radial glow matching card color
- Icon box (36×36, tinted bg), large value (28px/800), label (10px/muted), delta badge (↑↓)
- Hover: border brightens slightly
- Clickable → navigates to relevant section

### Panel
- `background: surface-1`, `border: 1px solid border`, `border-radius: 14px`
- Header: title (12px/600) + optional subtitle + "view all" link (accent color)
- Consistent 16px padding

### Status Dot
- Live: `#10b981` with `box-shadow: 0 0 6px #10b981`
- Warning: `#f59e0b` with glow
- Off: `#334155`, no glow

### Primary Button
- `background: linear-gradient(135deg, #8b5cf6, #6366f1)`
- `box-shadow: 0 4px 12px rgba(139,92,246,0.3)`
- 8px border-radius, 11px/600 font

### Live Chip (topbar)
- `bg: rgba(16,185,129,0.1)`, `border: rgba(16,185,129,0.2)`, green text
- Animated pulse dot (CSS keyframe)

---

## 4. Pages

### 4a. Dashboard Home (`/dashboard`)

**Layout:** KPI row (4 cols) + main grid (5-col: 3+2)

**KPI Row (4 cards):**
1. Active Agents — violet icon, count, delta vs last month
2. Monthly Calls — green icon, count, ↑% vs last month
3. New Leads — blue icon, count, ↑%
4. Avg Call Duration — amber icon, mm:ss, ↓s (faster = good)

**Main Grid:**
- Left (3/5): Voice Activity Chart — bar chart, 24h view, violet gradient bars, peak bars glow
- Right-top (2/5): Agent quick list — avatar, name, call count, status dot, hover → agent page
- Right-bottom (2/5): Recent Calls feed — time, agent name, duration, status badge

**Test Agent panel** (below grid, full-width or 3/5):
- Agent selector dropdown
- Chat bubbles (AI = violet tinted, User = violet gradient)
- Input + send button

---

### 4b. Agents (`/dashboard/agents`)

**Layout:** Header + filter bar + agent cards grid (3 cols)

**Agent Card:**
- Gradient avatar (initial letter), name, phone number
- Status dot + label ("פעיל" / "כבוי")
- Call count this month, mini sparkline bar
- Active toggle (pill switch, violet when on)
- Click → agent detail page

**Agent Detail (`/dashboard/agents/[id]`):**
- Tabs: כללי | נכסים | ידע — existing tabs, redesigned to match new style
- Tab active: violet underline + text
- Form fields: dark surface-2 background, border on focus = violet ring

---

### 4c. Calls (`/dashboard/calls`)

**Layout:** Header + filter chips + full-width table

**Filter chips:** "הכל" / "הושלם" / "הוחמץ" / "נכשל" — pill style, active = violet fill

**Table:**
- Dark surface-1 bg, no outer border, row separator = `border-bottom: 1px solid border`
- Columns: זמן | Agent | מספר | משך | סטטוס
- Status badge: color-coded (green/amber/red), small, rounded
- Row hover: `background: rgba(255,255,255,0.025)`
- Pagination: minimal, muted style

---

### 4d. Leads (`/dashboard/leads`)

**Layout:** Header + search/filter bar + table

Identical table pattern to Calls page. Columns: שם | טלפון | Agent | תאריך | סטטוס ליד

Status values: "חדש" (blue), "בתהליך" (amber), "סגור" (green), "אבוד" (red)

---

### 4e. Knowledge (`/dashboard/knowledge`)

**Layout:** Header + upload zone + knowledge items list

**Upload zone:** dashed border (violet), drag-and-drop, icon + text, violet CTA button

**Knowledge items:** list of cards — icon (file type), filename, size, upload date, delete button

---

### 4f. Settings (`/dashboard/settings`)

**Layout:** Two-column — section nav (left, 180px) + form area (right)

**Section nav:** vertical list of settings categories, active = violet tint  
**Form fields:** consistent with agent form style — dark surface-2, violet focus ring  
**Save button:** primary gradient button, sticky at bottom of form area

---

### 4g. Admin (`/admin`)

**Same visual design** as all other pages. No special color scheme.

**Admin-specific content:**
- Clients table: client name, plan, agent count, call count, created date
- Stats across all clients (aggregate KPIs at top)
- Each client row expandable or links to client detail

---

## 5. Micro-interactions

- Nav hover: `color` transition 150ms
- KPI card hover: `border-color` transition 200ms
- Agent row hover: `background` transition 150ms
- Status dots: CSS `animation: pulse` keyframe on live dots
- Primary button: subtle `box-shadow` increase on hover
- Chat send: input clears, bubble appears with 150ms fade-in

---

## 6. Responsive / Constraints

- Minimum supported width: **1024px** (no mobile optimization in this phase)
- Sidebar: fixed, non-collapsible in this phase
- Content area: `overflow-y: auto`, sidebar + topbar `position: sticky`

---

## 7. Implementation Approach

**Preserve existing functionality** — this is a pure visual redesign. No data fetching, routing, or business logic changes. The implementation touches:

1. CSS/Tailwind tokens (`tailwind.config`, `globals.css`) — update color palette
2. Layout components: `DashboardShell`, `Sidebar`, `Header`
3. Page client components: all pages listed above
4. Shared UI components: buttons, badges, inputs, cards

**No new dependencies required** — use existing Tailwind + shadcn + lucide-react.

---

## 8. Success Criteria

- All 7 pages match the approved `maya-hifi.html` visual direction
- Dark surface hierarchy visible (bg → surface-1 → surface-2)
- Violet accent consistent across all interactive states
- Animated live status dot on topbar
- No regressions in functionality (auth, filtering, i18n, RTL)
- Build passes (`next build`) with no TypeScript errors
