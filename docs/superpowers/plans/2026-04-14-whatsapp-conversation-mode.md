# WhatsApp Conversation Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Maya Dev Agent from one-shot task runner to a persistent conversational assistant over WhatsApp, with conversation history stored in Supabase.

**Architecture:** Every incoming WhatsApp message is saved to `agent_conversations` in Supabase. The daemon loads the last 20 messages as history, injects them into the `claude -p` prompt, and saves the response back. Code tasks still use `APPROVAL_REQUIRED:` signal before execution.

**Tech Stack:** Python, Supabase (supabase-py), claude CLI (`claude -p`), Twilio WhatsApp

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `agent/conversation.py` | Create | Supabase conversation history CRUD |
| `agent/daemon.py` | Modify | Replace task-only flow with conversation flow |
| `agent/context.py` | Modify | Add conversation history injection |
| `agent/executor.py` | Modify | Accept pre-built prompt (not just command) |

---

### Task 1: Create `agent_conversations` table in Supabase

**Files:**
- No code files — Supabase migration only

- [ ] **Step 1: Apply migration via Supabase MCP**

Run this SQL via Supabase dashboard or MCP:

```sql
CREATE TABLE IF NOT EXISTS agent_conversations (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);

ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_agent_conversations"
    ON agent_conversations FOR ALL
    USING (true) WITH CHECK (true);
```

- [ ] **Step 2: Verify table exists**

Run in Supabase SQL editor:
```sql
SELECT * FROM agent_conversations LIMIT 1;
```
Expected: empty result, no error.

---

### Task 2: Create `agent/conversation.py`

**Files:**
- Create: `agent/conversation.py`
- Test: `tests/test_conversation.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_conversation.py`:

```python
import os
import time
import pytest
from unittest.mock import MagicMock, patch

# We test the logic without hitting real Supabase
def test_save_and_load_history():
    """ConversationStore saves messages and returns them in order."""
    from agent.conversation import ConversationStore

    mock_sb = MagicMock()
    # Mock insert
    mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock()
    # Mock select — return 2 messages
    mock_sb.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "1", "role": "user", "content": "שלום", "created_at": 1.0},
            {"id": "2", "role": "assistant", "content": "שלום! מה שלומך?", "created_at": 2.0},
        ]
    )

    store = ConversationStore(sb=mock_sb)
    store.save("user", "שלום")
    history = store.get_history(limit=20)

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_format_history_for_prompt():
    """format_history returns correctly formatted string."""
    from agent.conversation import format_history

    messages = [
        {"role": "user", "content": "שלום"},
        {"role": "assistant", "content": "היי! איך אני יכול לעזור?"},
    ]
    result = format_history(messages)
    assert "[user]: שלום" in result
    assert "[assistant]: היי! איך אני יכול לעזור?" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd c:\Users\lidor\maya-ai
venv\Scripts\python -m pytest tests/test_conversation.py -v
```
Expected: `ModuleNotFoundError: No module named 'agent.conversation'`

- [ ] **Step 3: Implement `agent/conversation.py`**

```python
# agent/conversation.py
import os
import time
import uuid
from typing import Optional

from supabase import Client, create_client

HISTORY_LIMIT = int(os.getenv("AGENT_CONVERSATION_HISTORY_LIMIT", "20"))


def _get_client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


class ConversationStore:
    def __init__(self, sb: Optional[Client] = None):
        self._sb = sb or _get_client()

    def save(self, role: str, content: str) -> str:
        msg_id = str(uuid.uuid4())
        self._sb.table("agent_conversations").insert({
            "id": msg_id,
            "role": role,
            "content": content,
            "created_at": time.time(),
        }).execute()
        return msg_id

    def get_history(self, limit: int = HISTORY_LIMIT) -> list[dict]:
        res = (
            self._sb.table("agent_conversations")
            .select("*")
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return res.data or []


def format_history(messages: list[dict]) -> str:
    """Format conversation history for injection into claude -p prompt."""
    if not messages:
        return ""
    lines = [f"[{m['role']}]: {m['content']}" for m in messages]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
venv\Scripts\python -m pytest tests/test_conversation.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/conversation.py tests/test_conversation.py
git commit -m "feat(agent): add conversation history store"
```

---

### Task 3: Update `agent/context.py` to inject conversation history

**Files:**
- Modify: `agent/context.py`

- [ ] **Step 1: Update `build_context` to accept history**

Replace the bottom of `agent/context.py` (the `=== YOUR TASK ===` section):

```python
def build_context(history: str = "") -> str:
    try:
        branch = get_current_branch()
    except RuntimeError:
        branch = "(unavailable)"

    try:
        commits = get_recent_commits(n=5)
    except RuntimeError:
        commits = []

    commits_str = "\n".join(f"  {c['hash']} {c['message']}" for c in commits) or "  (none)"
    test_status = _pytest_status()

    history_section = ""
    if history:
        history_section = f"""
=== CONVERSATION HISTORY ===
{history}

"""

    return f"""
=== MAYA AI — Dev Agent Context ===

You are an autonomous development agent for the Maya AI project.
Always communicate in Hebrew (עברית) — all responses must be in Hebrew.
Project root: {PROJECT_ROOT}
Current branch: {branch}
Working branch: {AGENT_BRANCH}

Recent commits:
{commits_str}

Test status (last run):
{test_status}

=== IMPORTANT ===
IGNORE all memory files and previous session context. Base your answers ONLY on the actual current state of the codebase. Read files directly to answer questions.

=== RULES YOU MUST FOLLOW ===
1. Do all work on branch '{AGENT_BRANCH}' — never commit directly to main.
2. Before any `git push`, `railway up`, or ANY file modification: STOP and output a line that starts with
   APPROVAL_REQUIRED: followed by a summary of what you are about to do.
   Wait for the system to handle the approval — do not make changes yourself.
3. If you encounter an error, retry up to 2 times before giving up.
4. When done, output a line starting with TASK_COMPLETE: followed by a summary.
5. If you need the owner's physical input (test UX, visual check), output a line
   starting with GUIDANCE_NEEDED: followed by step-by-step instructions.
6. Keep the production FastAPI server untouched while working — do not kill uvicorn.

=== PROJECT OVERVIEW ===
- Backend: FastAPI (Python), deployed on Railway
- Frontend: Next.js dashboard in ./dashboard/
- Database: Supabase (PostgreSQL)
- WhatsApp: Twilio + Make.com
- AI: OpenAI Realtime API for voice, OpenAI chat for WhatsApp replies (Maya)
- Main entry: main.py → app/routes/
{history_section}
=== CURRENT MESSAGE (ענה בעברית בלבד!) ===
""".strip()
```

- [ ] **Step 2: Verify context renders correctly**

```bash
venv\Scripts\python -c "
from dotenv import load_dotenv; load_dotenv()
from agent.conversation import format_history
from agent.context import build_context
history = format_history([
    {'role': 'user', 'content': 'שלום'},
    {'role': 'assistant', 'content': 'היי!'},
])
ctx = build_context(history=history)
print(ctx[-500:])
"
```
Expected: output ends with `CONVERSATION HISTORY` block and `CURRENT MESSAGE`.

- [ ] **Step 3: Commit**

```bash
git add agent/context.py
git commit -m "feat(agent): inject conversation history into claude prompt"
```

---

### Task 4: Update `agent/executor.py` to accept full prompt

**Files:**
- Modify: `agent/executor.py`

- [ ] **Step 1: Add `run_conversation_turn` function**

Add this function to `agent/executor.py` (after `run_task`):

```python
def run_conversation_turn(full_prompt: str) -> ExecutionResult:
    """Run a single conversation turn with a pre-built prompt (history included)."""
    logger.info("Running conversation turn, prompt length=%d", len(full_prompt))

    try:
        claude_cmd = _find_claude()
        result = subprocess.run(
            [claude_cmd, "-p", full_prompt, "--allowedTools", "all"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            env=_env_with_api_key(),
        )
        output = result.stdout or ""
        if result.returncode != 0:
            logger.warning("claude exited with code %d", result.returncode)
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            raw_output="",
            approval_required=None,
            task_complete=None,
            guidance_needed=None,
            error="תפג הזמן אחרי 30 דקות",
        )
    except FileNotFoundError as exc:
        return ExecutionResult(
            raw_output="",
            approval_required=None,
            task_complete=None,
            guidance_needed=None,
            error=str(exc),
        )

    return _parse_output(output)
```

- [ ] **Step 2: Commit**

```bash
git add agent/executor.py
git commit -m "feat(agent): add run_conversation_turn for history-aware execution"
```

---

### Task 5: Rewrite `agent/daemon.py` conversation loop

**Files:**
- Modify: `agent/daemon.py`

- [ ] **Step 1: Rewrite `run_daemon` and main loop**

Replace the entire `agent/daemon.py` with:

```python
"""
Maya Dev Agent — conversational daemon loop.

Each WhatsApp message from the owner starts a conversation turn:
1. Save message to Supabase conversation history
2. Load history + build prompt
3. Run claude -p
4. If APPROVAL_REQUIRED: ask for approval, wait, then execute code task
5. Save response + send via WhatsApp

Polls Supabase agent_tasks for any direct task injections (legacy support).
"""
from dotenv import load_dotenv
load_dotenv()

import logging
import time
import sys

from agent.config import APPROVAL_TIMEOUT_SECONDS, MAX_TASK_RETRIES
from agent.queue import TaskQueue, ApprovalStatus
from agent.conversation import ConversationStore, format_history, HISTORY_LIMIT
from agent.context import build_context
from agent.executor import run_conversation_turn, run_task
from agent.git_ops import prepare_agent_branch, merge_to_main, get_diff_summary
from agent.whatsapp import send_to_owner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agent.daemon")

POLL_INTERVAL = 5  # seconds


def run_daemon():
    logger.info("Maya Dev Agent daemon starting...")
    send_to_owner("מאיה Dev Agent מוכנה. שלח לי משימה!")
    q = TaskQueue()
    conv = ConversationStore()

    while True:
        task = q.fetch_next_pending()
        if task is None:
            time.sleep(POLL_INTERVAL)
            continue

        task_id = task["id"]
        command = task["command"]
        logger.info("New message id=%s: %r", task_id, command[:60])

        q.set_running(task_id)
        _handle_message(q, conv, task_id, command)


def _handle_message(q: TaskQueue, conv: ConversationStore, task_id: str, command: str):
    """Handle an incoming WhatsApp message as a conversation turn."""
    # Save user message
    conv.save("user", command)

    # Build prompt with history
    history_msgs = conv.get_history(limit=HISTORY_LIMIT)
    history_str = format_history(history_msgs[:-1])  # exclude the message we just saved
    context = build_context(history=history_str)
    full_prompt = f"{context}\n\n{command}\n\n(חשוב: ענה בעברית בלבד)"

    # Run claude
    result = run_conversation_turn(full_prompt)

    if result.error:
        response = f"שגיאה: {result.error}"
        conv.save("assistant", response)
        send_to_owner(response)
        q.set_failed(task_id, error=result.error, attempt=0)
        return

    # Extract the response text (prefer task_complete, else raw output tail)
    if result.task_complete:
        response_text = result.task_complete
    else:
        response_text = result.raw_output[-1000:].strip() if result.raw_output else "(אין פלט)"

    # Handle approval flow
    if result.approval_required:
        _handle_approval(q, conv, task_id, command, result.approval_required)
        return

    if result.guidance_needed:
        response = result.guidance_needed[:1400]
        conv.save("assistant", response)
        send_to_owner(response)
        q.set_done(task_id, result="Guidance sent")
        return

    # Regular response
    conv.save("assistant", response_text)
    send_to_owner(response_text[:1500])
    q.set_done(task_id, result="Conversation turn complete")


def _handle_approval(q: TaskQueue, conv: ConversationStore, task_id: str, command: str, summary: str):
    """Send approval request and wait. If approved, run the code task."""
    try:
        prepare_agent_branch()
    except RuntimeError as e:
        msg = f"לא הצלחתי להכין branch: {e}"
        conv.save("assistant", msg)
        send_to_owner(msg)
        q.set_failed(task_id, error=str(e), attempt=0)
        return

    approval_msg = (
        f"רוצה לבצע:\n\n{summary}\n\n"
        f"שלח כן לאישור או לא לביטול."
    )
    approval_id = q.create_approval(task_id, action="code_change", summary=summary)
    q.set_awaiting_approval(task_id)
    conv.save("assistant", approval_msg)
    send_to_owner(approval_msg)

    approved = _wait_for_approval(q, approval_id)
    if not approved:
        msg = "בוטל. לא בוצעו שינויים."
        conv.save("assistant", msg)
        send_to_owner(msg)
        q.set_done(task_id, result="Cancelled by owner")
        return

    # Execute the actual code task
    send_to_owner(f"מתחיל: {command[:200]}")
    result = run_task(command)

    if result.error:
        msg = f"נכשל: {result.error[:600]}"
        conv.save("assistant", msg)
        send_to_owner(msg)
        q.set_failed(task_id, error=result.error, attempt=0)
        return

    if result.approval_required:
        # Deploy approval
        diff = get_diff_summary()
        deploy_msg = (
            f"קוד מוכן לדפלוי.\n\nסיכום: {result.approval_required}\n\n"
            f"{diff[:600]}\n\nשלח כן לדפלוי או לא לביטול."
        )
        deploy_approval_id = q.create_approval(task_id, action="push", summary=result.approval_required)
        q.set_awaiting_approval(task_id)
        conv.save("assistant", deploy_msg)
        send_to_owner(deploy_msg)

        deploy_approved = _wait_for_approval(q, deploy_approval_id)
        if deploy_approved:
            try:
                merge_to_main()
                done_msg = "עלה לפרודקשן. הכל מוכן!"
                conv.save("assistant", done_msg)
                send_to_owner(done_msg)
                q.set_done(task_id, result="Deployed")
            except RuntimeError as e:
                msg = f"דפלוי נכשל: {e}"
                conv.save("assistant", msg)
                send_to_owner(msg)
                q.set_failed(task_id, error=str(e), attempt=0)
        else:
            msg = "בוטל. לא נדחף שום דבר."
            conv.save("assistant", msg)
            send_to_owner(msg)
            q.set_done(task_id, result="Deploy cancelled")
        return

    done_text = result.task_complete or result.raw_output[-600:] or "סיימתי"
    conv.save("assistant", done_text)
    send_to_owner(f"סיימתי! {done_text[:1400]}")
    q.set_done(task_id, result="Done")


def _wait_for_approval(q: TaskQueue, approval_id: str) -> bool:
    deadline = time.time() + APPROVAL_TIMEOUT_SECONDS
    while time.time() < deadline:
        approval = q.get_approval(approval_id)
        if approval and approval["status"] == ApprovalStatus.APPROVED:
            return True
        if approval and approval["status"] == ApprovalStatus.REJECTED:
            return False
        time.sleep(3)
    q.resolve_approval(approval_id, approved=False)
    send_to_owner("פג תוקף האישור (10 דקות). המשימה בוטלה.")
    return False


if __name__ == "__main__":
    run_daemon()
```

- [ ] **Step 2: Verify daemon imports correctly**

```bash
cd c:\Users\lidor\maya-ai
venv\Scripts\python -c "from dotenv import load_dotenv; load_dotenv(); from agent.daemon import run_daemon; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent/daemon.py
git commit -m "feat(agent): rewrite daemon with conversation history flow"
```

---

### Task 6: Apply Supabase migration and test end-to-end

**Files:**
- No code changes — testing only

- [ ] **Step 1: Apply the Supabase migration from Task 1**

Via Supabase MCP or dashboard SQL editor:
```sql
CREATE TABLE IF NOT EXISTS agent_conversations (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_agent_conversations"
    ON agent_conversations FOR ALL
    USING (true) WITH CHECK (true);
```

- [ ] **Step 2: Run all tests**

```bash
venv\Scripts\python -m pytest tests/ -q
```
Expected: all tests pass (including `test_conversation.py`).

- [ ] **Step 3: Restart daemon and send test message**

```bash
taskkill /F /IM python.exe
start venv\Scripts\python -m agent.daemon
```

Send "שלום, מה שלומך?" via WhatsApp.
Expected: natural Hebrew response (not a task execution).

- [ ] **Step 4: Test conversation memory**

Send "מה שמי?" (the agent doesn't know, but the conversation context should be there).
Then send "תגיד שוב מה שאלתי לפני".
Expected: agent references previous message.

- [ ] **Step 5: Push to main**

```bash
git checkout main
git merge agent/work
git push origin main
```

---

## Self-Review

**Spec coverage:**
- ✅ Conversation history in Supabase (`agent_conversations`)
- ✅ History injected into `claude -p` prompt
- ✅ Natural responses without forcing task execution
- ✅ `APPROVAL_REQUIRED` gate before code changes
- ✅ No Anthropic API charges (uses `claude -p`)
- ✅ Hebrew responses

**No placeholders:** All steps contain actual code.

**Type consistency:** `ConversationStore`, `format_history`, `HISTORY_LIMIT` used consistently across tasks 2, 3, 5.
