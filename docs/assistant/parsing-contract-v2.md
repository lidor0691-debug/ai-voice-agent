# Maya Assistant — Parsing Contract v2

Status: **dormant foundation** (PR1). Nothing in the running service imports
this yet. Production Stage-1 is an LLM (Claude); the rule-based parser shipped
under `tests/assistant/nlp/parser.py` is a **test oracle only** and must never
be wired as the live Stage-1.

## Two-stage model

**Stage 1 — PARSE** (production: LLM). Natural language → structured
`ParsedIntent`. Output `status` is `parsed` or `needs_clarification`.

**Stage 2 — RESOLVE** (production: deterministic backend, see
`app/assistant/nlp/resolver.py`). Takes a `ParsedIntent` plus injected
contact / 24h-window / active-template data and produces a `SendPlan`. No
Supabase/Twilio/Telegram/Make/network in this layer.

## Vocabulary (`app/assistant/nlp/contract.py`)

- `RecipientType`: `client | teacher | group`
- `MessageType`: `agreement | deposit | video | lesson_coordination | custom`
  - The old `teacher` message type was **renamed** to `lesson_coordination` to
    avoid colliding with `RecipientType.TEACHER`.
- `ParseStatus`: `parsed | needs_clarification`
- `SendPlan`: `group_manual | manual_fallback | api_template | api_freeform`
- `TEMPLATE_TYPES`: message types that can be template-backed
  (`agreement, deposit, video, lesson_coordination`). `custom` is free text only.

## Locked rules

1. **Preposition rule (event-date vs send-date).**
   - `ב-<date>` / "on `<date>`" → `scheduled_at_local` (the SEND date).
   - `ל-` / `עד` / `של` `<date>` / "for / by / of `<date>`" →
     `related_event_date` (the date the message is ABOUT).
   - A date that is **only** an event date does **not** satisfy the send-time
     requirement.

2. **Default time.** A send date with no time-of-day defaults to **10:00**
   with `is_explicit_time = False`. There is **no** special
   "bare tomorrow → 09:00" rule.

3. **No silent inference of a missing send time.** If there is no send date/time
   (e.g. only an event date, or nothing), `status = needs_clarification`.

4. **Missing recipient** → `status = needs_clarification`.

5. **Inferred times are always surfaced** (`inferred_notes`) in the confirmation.

6. **`expired` ≠ `cancelled`** (status semantics for later PRs): `cancelled` =
   owner cancelled; `expired` = approval not given within 2h after the
   scheduled send time. (Not exercised by PR1 parsing.)

7. **Unknown recipient → inline contact-add** (stateful, two-turn): Maya asks
   for the phone number, creates the contact, then resumes the original intent.
   (Stage-2/flow concern; not built in PR1.)

## Stage-2 `SendPlan` decision tree

First match wins:

1. Group recipient → `group_manual`
2. No contact / no phone on file → `manual_fallback`
3. Inside the WhatsApp 24h service window → `api_freeform`
4. Outside the window, an **active** template exists → `api_template`
5. Outside the window, no active template → `manual_fallback`
