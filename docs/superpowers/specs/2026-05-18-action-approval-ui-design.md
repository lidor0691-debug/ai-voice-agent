# Phase 3.10A — Approve / Edit / Skip UI design

**Date:** 2026-05-18
**Status:** Design approved, pending implementation plan
**Predecessor:** Phase 3.9 (read-only suggestions UI on `/home/morning`, commit `6022332`)
**Successor:** Phase 3.11 (executor — first real WhatsApp send capability; out of scope here)

## 1. Scope

Wire the existing 3.7B RPCs (`approve_action`, `skip_action`, `edit_action_payload`) into the suggestion cards already rendered by `dashboard/app/home/morning/page.tsx`.

In scope:

- Three actions per card: approve, edit (message body), skip (with optional Hebrew reason chip).
- Server-action plumbing with `revalidatePath`.
- A minimal `"use client"` island for the buttons + their two expandable panels + inline error display.
- Inline error banner per card mapped from RPC error codes to Hebrew copy.

Out of scope (explicitly):

- No executor. No Twilio. No WhatsApp send. Approval flips `status='approved'` in the DB and the card disappears from the queue; nothing else happens until 3.11.
- No "today's activity" recap line on the page.
- No optimistic UI. No undo. No bulk approve. No keyboard shortcuts.
- No client-side mirror of the SQL message validator. The SQL validator stays canonical; admins discover rule violations through error messages.
- No changes to the SELECT path, the admin-without-client locked hint, the visible status filter, or any 3.9 server-rendering behavior.

Visible status filter remains `status IN ('suggested','pending_approval','edited')` plus `expires_at > now()`. After approve/skip, rows transition to `approved`/`skipped` and fall out of the filter on the next render.

## 2. Architecture

`dashboard/app/home/morning/page.tsx` stays a **server component**. The list SELECT continues to run on the server with the RLS-aware `createSupabaseServerClient()`.

Each card renders three `<form>` elements whose `action` props are **bound server actions** (no hidden `suggestion_id` / `version` inputs):

```ts
approveAction.bind(null, suggestion.id, suggestion.version)
skipAction.bind(null, suggestion.id, suggestion.version)
editAction.bind(null, suggestion.id, suggestion.version)
```

`FormData` only carries user-entered values:

- `message_he` (string, edit form only)
- `skip_reason` (string, skip form only; chip label or free text)

Bound server actions are compatible with `useActionState` in Next 15 / React 19: the bound action is passed to `useActionState`, which returns `[state, action]`. The card client island uses `useActionState` to receive the action result and render the inline error banner.

**Server-action contract** (lives in `dashboard/app/home/morning/actions.ts`, marked `"use server"`).

Because the card client island wires each form through `useActionState`, every server action signature **must** include `prevState` between the bound arguments and `formData`. The full signatures are:

| Action | Signature | RPC called | RPC params |
|---|---|---|---|
| `approveAction` | `(suggestionId, expectedVersion, prevState, formData)` | `approve_action` | `p_suggestion_id`, `p_expected_version` |
| `skipAction` | `(suggestionId, expectedVersion, prevState, formData)` | `skip_action` | `p_suggestion_id`, `p_expected_version`, `p_reason` (from `formData.skip_reason`) |
| `editAction` | `(suggestionId, expectedVersion, prevState, formData)` | `edit_action_payload` | `p_suggestion_id`, `p_expected_version`, `p_message_he` (from `formData.message_he`) |

No server action signature omits `prevState`. Every RPC call **must** include `p_expected_version`, sourced from `suggestion.version` at render time and bound into the server action. No RPC is ever called without `p_expected_version`.

Each server action:

1. Re-derives admin / client context server-side (same `user.user_metadata.client_id` peek as the page).
2. Reads the user-entered value(s) from `FormData` (if any).
3. Calls the RPC via the RLS-aware server Supabase client.
4. On success → `revalidatePath('/home/morning')` and returns `{ ok: true }`.
5. On failure → returns `{ ok: false, code, message }`. Server actions never throw to the client.

**Net new files:**

- `dashboard/app/home/morning/actions.ts` — three server actions.
- `dashboard/app/home/morning/suggestion-card.tsx` — `"use client"` card wrapper. Owns local expand state for the edit and skip panels, calls `useActionState` for each of the three bound actions, and renders the inline error banner. The read-only message body, expiry line, and any server-rendered context are passed in as props/children.

The server-only SELECT path from 3.9 is preserved. The client island is strictly buttons + two expand panels + error display. No data fetching, no auth, no Supabase client in the browser.

## 3. Card states

A single card has four UI states:

### 3.1 Default

Read-only Hebrew message body plus three buttons in this order (RTL): **אשר** · **ערוך** · **דלג**.

One-click approve — no confirm step in 3.10A. The button copy stays plain `אשר`. When 3.11 ships and approve becomes a real send, friction will be added as part of that phase.

### 3.2 Editing

Clicking **ערוך** replaces the message block with:

- An RTL `<textarea>` pre-filled with the current `payload_message`.
- A live char counter `N / 2000`.
- Two buttons: **שמור** / **ביטול**.

Submitting calls `editAction`. On validator failure the `<textarea>` content is preserved and a red Hebrew error line renders above it. On success the card returns to default state with status `edited`.

### 3.3 Skipping

Clicking **דלג** expands an inline panel with:

- Four reason chips: `לא רלוונטי עוד` · `טופל כבר` · `מנוסח באיכות נמוכה` · `אחר`.
- An optional Hebrew free-text input, max 200 chars. Selecting the `אחר` chip reveals this input and makes it required.
- Two buttons: **אשר דילוג** / **ביטול**.

The submitted `skip_reason` is the chip label (Hebrew string) for the three fixed chips, or the free-text content when `אחר` is chosen. At least one of "chip selected" or "free text non-empty" must be true; the panel is opened intentionally, so a fully empty submission is rejected client-side before the server call.

### 3.4 Error

A small red Hebrew banner renders directly above the action buttons (or above the textarea, in editing state). It reflects the most recent `{ ok: false, code }` from the relevant `useActionState`. The banner clears on the next successful state transition or panel cancellation.

## 4. Error mapping

| Error code from RPC / server action | Hebrew banner copy |
|---|---|
| `stale_version` | הכרטיס עודכן במקום אחר. רעננו ונסו שוב. |
| `expired` | ההצעה פגה. רעננו את הדף. |
| `already_acted` / `wrong_status` | הצעה זו כבר טופלה. |
| `permission_disabled` / `permission_drift` | מצב הפעולה אינו מאפשר את הפעולה הזו. |
| `validation_failed_length` | ההודעה חייבת להיות באורך 1 עד 2000 תווים. |
| `validation_failed_placeholder` | אין להשתמש במחזיקי מקום בסוגריים מרובעים. |
| `validation_failed_currency` | אין לציין סכומי כסף בהודעה. |
| `validation_failed_control_chars` | ההודעה מכילה תווי בקרה שאינם מותרים. |
| any other failure | הפעולה נכשלה. נסו שוב. |

`stale_version` is mandatory in this mapping — it is the version-conflict signal the three RPCs raise when `p_expected_version` does not match the row's current `version`.

## 5. State transition contract

| User action | RPC | Status before → after | Card after revalidate |
|---|---|---|---|
| Approve | `approve_action` | `suggested` / `pending_approval` / `edited` → `approved` | gone from queue |
| Skip | `skip_action` | same → `skipped` (writes `skip_reason`) | gone from queue |
| Edit + Save | `edit_action_payload` | `suggested` / `pending_approval` → `edited` (writes new `payload_message`, bumps `version`) | stays visible in `edited` state, default buttons restored |
| Edit then Approve | two RPCs, two clicks (second click uses the new `version` from the re-rendered card) | `edited` → `approved` | gone from queue |
| Cancel in edit or skip panel | none | unchanged | card collapses back to default |

After every successful RPC, the card's `version` changes. The page re-renders via `revalidatePath` and the bound server actions are re-bound with the fresh version, so the next user click on the same card carries the current `p_expected_version`.

## 6. What 3.10A explicitly does NOT do

- Send WhatsApp messages.
- Reach any Twilio code path.
- Add a results / analytics / activity-today surface.
- Add optimistic UI.
- Add an undo for skip.
- Add bulk approve.
- Mirror the SQL message validator on the client.
- Surface approved suggestions anywhere in the UI after they leave the queue. (Audit access stays via SQL until 3.12.)

## 7. Risks and notes

- **Concurrency.** Two admins on the same card. The losing click receives `stale_version` (when versions diverge) or `already_acted` (when status no longer matches). Both are handled by the error mapping in §4. The user refreshes and decides; we do not auto-retry.
- **Client island boundary.** This is the first `"use client"` component on this page. Keep it minimal: buttons, local expand state for the two panels, and `useActionState` wiring. All data fetching, auth, RLS, and Supabase access stay on the server.
- **Skip reason values.** Chip labels are stored verbatim as Hebrew strings in `skip_reason`. Three of the four are fixed strings; the `אחר` path stores free text. Future analytics will need to bucket by label — acceptable while the chip set is stable.
- **Validator parity.** We continue with the locked rule: the SQL validator is canonical, the Python generator mirrors it, and the dashboard does not add a third copy. Admins learn the rules from error messages.
- **No hidden inputs for `suggestion_id` / `version`.** Bound server actions are the chosen path. If a future requirement forces falling back to hidden inputs (e.g., progressive enhancement without JS), it must be raised before that change is made, not done implicitly.

## 8. Open questions

None at design time. All forks were resolved in brainstorming.
