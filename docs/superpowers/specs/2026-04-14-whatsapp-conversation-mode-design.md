# WhatsApp Conversation Mode — Design Spec
Date: 2026-04-14

## Overview

Upgrade the Maya Dev Agent from a one-shot task runner to a full conversational assistant over WhatsApp. The agent remembers the conversation history, responds naturally in Hebrew, and can execute code tasks with a single approval gate before touching the codebase.

Uses `claude -p` (Claude Code CLI) with injected conversation history — no Anthropic API charges, runs on the user's existing Claude Max subscription.

---

## Goals

1. Talk freely with the agent over WhatsApp — like ChatGPT but in Hebrew
2. Agent remembers the full conversation history
3. Agent can execute dev tasks when asked, but only after user sends "כן"
4. No additional API costs beyond the existing Claude Max subscription

---

## Architecture

```
User WhatsApp message
    ↓
Twilio → Railway FastAPI POST /agent/command
    ↓
Save message to Supabase agent_conversations (role=user)
    ↓
Daemon picks up message, loads full conversation history
    ↓
claude -p "<history + new message>"
    ↓
Parse response:
  - APPROVAL_REQUIRED: → send approval request, wait for כן/לא
  - Regular text → send directly to WhatsApp
    ↓
Save response to Supabase agent_conversations (role=assistant)
    ↓
WhatsApp reply to user
```

---

## Components

### 1. Supabase table: `agent_conversations`

```sql
CREATE TABLE agent_conversations (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,        -- 'user' or 'assistant'
    content TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
```

Keeps the full conversation log. No per-session scoping — one continuous conversation.

### 2. Modified daemon flow

Instead of treating every message as an independent task:

1. Save incoming message as `role=user`
2. Load last N messages (e.g. 20) as conversation history
3. Build prompt: `[context preamble] + [conversation history] + [current message]`
4. Run `claude -p "<full prompt>"`
5. Parse output:
   - If contains `APPROVAL_REQUIRED:` → send WhatsApp approval request, wait for כן/לא, then run the code task
   - Otherwise → send response directly as WhatsApp reply
6. Save assistant response as `role=assistant`

### 3. Conversation history format

Injected into the prompt as:

```
=== CONVERSATION HISTORY ===
[user]: ...
[assistant]: ...
[user]: ...

=== CURRENT MESSAGE ===
<new message>
```

### 4. Approval flow (unchanged)

When the agent wants to touch code:
- Outputs `APPROVAL_REQUIRED: <summary of what it wants to do>`
- Daemon sends WhatsApp: "רוצה לבצע: <summary>. שלח כן לאישור או לא לביטול."
- User replies כן → daemon runs `claude -p` with the actual code task
- User replies לא → daemon cancels, notifies user

---

## Data Flow Details

**Conversation history limit:** Last 20 messages (to keep prompt size reasonable). Configurable via env var `AGENT_CONVERSATION_HISTORY_LIMIT`.

**History truncation:** If total history is too long, truncate oldest messages first.

**No separate sessions:** One continuous conversation thread. If needed in the future, can add session scoping.

---

## What Does NOT Change

- Twilio webhook → Railway FastAPI route (unchanged)
- OWNER_PHONE validation (unchanged)
- `claude -p` execution for code tasks (unchanged)
- git branching and approval flow for deploys (unchanged)
- WhatsApp send via Twilio (unchanged)

---

## Success Criteria

1. User can send "מה שלומך?" and get a natural Hebrew response
2. User can say "תוסיף לוג ב-daemon.py" → agent asks for approval → user says כן → agent makes the change
3. Agent remembers what was said 5 messages ago
4. No new Anthropic API charges
