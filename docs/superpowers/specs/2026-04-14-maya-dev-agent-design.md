# Maya Dev Agent — Design Spec
Date: 2026-04-14

## Overview

A local autonomous development agent that runs on the home desktop (always-on) and is controlled via WhatsApp. The agent acts as a project partner: it can write code, fix bugs, deploy, and run tests autonomously — and when human input is required (testing Maya's UX, dashboard interactions, prompt review), it guides the user step-by-step over WhatsApp exactly as Claude Code does in the IDE.

---

## Goals

1. Execute dev tasks (code, debug, deploy) without the user being at the computer
2. Guide the user remotely over WhatsApp when their hands are needed
3. Test Maya automatically when possible; ask the user when human judgment is needed
4. Never deploy or push without explicit user approval via WhatsApp

---

## Architecture

```
User (WhatsApp)
    ↓ task message (from user's phone number only)
Twilio → FastAPI (existing) → POST /agent/command (new route)
    ↓ webhook
Agent Daemon (Python, runs as Windows background service on home desktop)
    ↓
Task Queue (local SQLite file)
    ↓
Claude Code CLI  (claude -p "task" --allowedTools all)
    ↓ executes autonomously in project directory
Git / Railway CLI / Supabase CLI / Make.com API / Twilio API
    ↓ progress updates + approval requests
User (WhatsApp)
```

---

## Components

### 1. FastAPI route: `POST /agent/command`

- Validates that the sender's phone number matches the owner's number (env var `OWNER_PHONE`)
- Accepts raw WhatsApp message body
- Forwards to Agent Daemon via local HTTP (localhost:8765) or writes to task queue file
- Returns 200 immediately (Twilio requirement)

### 2. Agent Daemon

A long-running Python process managed by Windows Task Scheduler (on startup, restart on failure).

Responsibilities:
- Listens for incoming tasks (from FastAPI or a local queue file)
- Maintains a task queue (SQLite) with status: `pending → running → awaiting_approval → done / failed`
- Runs one task at a time (sequential, not parallel — safer for a single repo)
- Sends WhatsApp updates via Twilio API at key moments
- Handles the approval flow (waits up to 10 minutes for user reply before aborting)

### 3. Claude Code execution

Each task runs:
```bash
claude -p "<task description>" --allowedTools all --output-format json
```
Inside the project directory (`c:\Users\lidor\maya-ai`).

The agent is given a system context preamble that includes:
- Current project state (branch, last commits)
- Available tools (Railway CLI, Supabase CLI, Make.com API key)
- Rules: never push/deploy without sending approval request first

### 4. Dual operating modes

**Autonomous mode** — agent does the work itself:
- Writing/editing code
- Running tests
- Git commits
- Calling APIs (Supabase, Make.com)
- Railway deploy (after approval)

**Guidance mode** — agent instructs the user step by step:
- Testing Maya's WhatsApp UX (human feel/quality checks)
- Dashboard interactions requiring visual judgment
- Prompt review and adjustment
- Any action that requires physical presence or subjective evaluation

The agent decides which mode to use per task. For Maya testing specifically:
- Technical checks (response received, latency, JSON structure) → autonomous via API
- Quality/UX checks (does Maya sound right? is the answer helpful?) → guidance mode

### 5. Approval flow (before any deploy/push)

1. Agent sends WhatsApp: summary of what it did + what it's about to push/deploy
2. Waits up to 10 minutes for "כן" / "לא" (also accepts "yes"/"no")
3. "כן" → executes
4. "לא" → aborts, reports what was skipped
5. Timeout → aborts, notifies user

### 6. Error recovery

- On task failure: retries up to 2 times automatically
- On 3rd failure: sends detailed WhatsApp report (what was attempted, what failed, what the user needs to do)
- Report includes exact error message and suggested next step

---

## WhatsApp commands (natural language)

The agent understands natural Hebrew and English. Examples:

```
"תקן את הbug ב-whatsapp_history.py"
"בנה את הtab החדש לanalysis בdashboard"
"תבדוק שמאיה עונה כמו שצריך"
"מה הסטטוס של הפרויקט?"
"תעשה deploy של מה שיש"
"עדכן את הפרומפט של מאיה ל..."
"תריץ את הtests ותגיד לי מה קרה"
"תבדוק אם יש באגים חדשים"
```

Status command returns: current branch, last 3 commits, any pending tasks, Railway deploy status.

---

## Security

- Only messages from `OWNER_PHONE` are processed — all others silently ignored
- Daemon listens only on localhost (not exposed to internet)
- All secrets (Railway token, Supabase key, Anthropic API key, Twilio credentials) stored in `.env` — same file already used by the project
- No new credentials required beyond what already exists

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| Daemon language | Python 3.11 |
| Task queue | SQLite (via Python `sqlite3`) |
| Process management | Windows Task Scheduler |
| Claude execution | Claude Code CLI (`claude -p`) |
| WhatsApp send | Twilio REST API (existing credentials) |
| WhatsApp receive | Existing FastAPI + Twilio webhook |

---

## What is NOT in scope

- Multi-user support
- Web UI for the agent
- Running on a cloud server (desktop-only by design)
- Parallel task execution
- Memory/learning between sessions (Claude Code handles context via git history and project files)

---

## File structure (new files)

```
app/
  routes/
    agent.py          # POST /agent/command route
agent/
  daemon.py           # main daemon process
  queue.py            # SQLite task queue
  executor.py         # Claude Code runner
  whatsapp.py         # send WhatsApp via Twilio
  context.py          # builds project context preamble for Claude
  config.py           # env vars + settings
  install.bat         # registers daemon with Windows Task Scheduler
```

---

## Success criteria

- User sends WhatsApp from phone → agent executes task → user receives update, all without touching the computer
- Agent correctly identifies when to act autonomously vs. when to guide the user
- No deploy or push happens without explicit WhatsApp approval
- Agent reports clearly when it's stuck and what's needed
