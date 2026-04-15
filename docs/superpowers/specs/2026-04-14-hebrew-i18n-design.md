# Hebrew i18n — Design Spec
Date: 2026-04-14

## Goal
Translate the entire Maya AI dashboard UI to Hebrew with full RTL layout support. A toggle in the header allows switching to English. No internal logic, API calls, variable names, or data structures are affected — only visible text and layout direction change.

---

## Architecture

### 1. Translations file — `dashboard/lib/i18n.ts`
A single flat object with two keys: `he` and `en`. Every visible UI string in the dashboard has a key here.
- All Hebrew strings already exist in the codebase (agent-form, leads pages, etc.) — they are consolidated here.
- All English strings from the remaining components are added.
- No external i18n library. Just a typed TypeScript object.

### 2. Language Context — `dashboard/context/language-context.tsx`
- `LanguageContext` holds `lang: "he" | "en"` and `setLang`.
- `useLanguage()` hook returns `{ t: Translations[lang], lang, setLang }`.
- Default: `"he"`.
- No persistence (localStorage not needed for now).

### 3. Layout wrapper — `dashboard/app/dashboard/layout.tsx`
- Wrap children with `<LanguageProvider>`.
- Set `<html dir={lang} lang={lang}>` dynamically — but since layout is a server component, the `dir` is set on the inner wrapper div instead: `<div dir={lang}>`.

### 4. Language toggle — `dashboard/components/layout/header.tsx`
- Add `EN | עב` toggle button in the top-right of the header.
- Active language is highlighted (brand color), inactive is muted.
- Calls `setLang` from `useLanguage()`.

### 5. Component updates
Every component that renders visible text calls `const { t, lang } = useLanguage()` and uses `t.keyName` instead of hardcoded strings.

---

## RTL Support
- The outermost dashboard wrapper gets `dir="rtl"` when lang is `"he"` and `dir="ltr"` when `"en"`.
- Tailwind handles most RTL automatically via logical properties — no CSS rewrites needed.
- Sidebar, header, tables, cards all flip correctly with `dir`.

---

## Files Changed
| File | Change |
|------|--------|
| `dashboard/lib/i18n.ts` | **New** — all translations |
| `dashboard/context/language-context.tsx` | **New** — context + hook |
| `dashboard/app/dashboard/layout.tsx` | Wrap with LanguageProvider, add dir |
| `dashboard/components/layout/header.tsx` | Add lang toggle, use `t` |
| `dashboard/components/layout/sidebar.tsx` | Use `t` for nav labels |
| `dashboard/app/dashboard/page.tsx` | Use `t` |
| `dashboard/app/dashboard/agents/page.tsx` | Use `t` |
| `dashboard/app/dashboard/calls/page.tsx` | Use `t` |
| `dashboard/app/dashboard/settings/page.tsx` | Use `t` |
| `dashboard/app/dashboard/knowledge/page.tsx` | Use `t` |
| `dashboard/app/dashboard/leads/LeadsClientPage.tsx` | Use `t` |
| `dashboard/components/dashboard/test-agent.tsx` | Use `t` |
| `dashboard/components/agents/agent-card.tsx` | Use `t` |
| `dashboard/components/agents/agent-form.tsx` | Use `t` (already Hebrew — consolidate to `t`) |
| `dashboard/components/agents/agent-page-tabs.tsx` | Use `t` |
| `dashboard/components/agents/client-assets-tab.tsx` | Use `t` (already Hebrew — consolidate to `t`) |
| `dashboard/components/knowledge/knowledge-client.tsx` | Use `t` |
| `dashboard/components/dashboard/leads-table.tsx` | Use `t` |
| `dashboard/components/dashboard/lead-detail-panel.tsx` | Use `t` |

---

## What Is NOT Changed
- API routes, fetch calls, Supabase queries
- Variable names, prop names, type definitions
- Route paths (`/dashboard/agents` etc.)
- Data values coming from the database (status values like "new", "contacted" are display-mapped via `t`)
- `dashboard/components/ui/*` (shadcn primitives — no visible text)

---

## Success Criteria
- Default language on load is Hebrew, full RTL layout
- Clicking EN switches all text to English, layout flips to LTR
- Clicking עב switches back
- No console errors, no broken functionality
- All pages covered: Dashboard, Agents, Calls, Leads, Knowledge, Settings
