# Maya Dev Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an autonomous development agent controlled via WhatsApp that executes coding tasks, fixes bugs, and deploys — all without the user being at the computer.

**Architecture:** A Python daemon runs permanently on the home desktop (Windows Task Scheduler). WhatsApp messages from the owner's phone → Twilio → FastAPI `/agent/command` → SQLite queue → daemon wakes up → runs `claude -p "<task>"` → reports back via WhatsApp. Before any git push or Railway deploy, the daemon sends a diff summary to WhatsApp and waits for explicit approval.

**Tech Stack:** Python 3.14, FastAPI (existing), SQLite (stdlib), Twilio REST API, Claude Code CLI (`claude`), Railway CLI, subprocess

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `agent/config.py` | Create | Env vars, constants |
| `agent/queue.py` | Create | SQLite task + approval queue |
| `agent/whatsapp.py` | Create | Send WhatsApp via Twilio REST |
| `agent/git_ops.py` | Create | Branch management, diff summary, merge |
| `agent/context.py` | Create | Build project context preamble for Claude |
| `agent/executor.py` | Create | Run `claude -p` subprocess, capture output |
| `agent/daemon.py` | Create | Main loop — orchestrates everything |
| `app/routes/dev_agent.py` | Create | POST /agent/command FastAPI route |
| `main.py` | Modify | Register dev_agent router |
| `agent/install_scheduler.bat` | Create | Register daemon with Windows Task Scheduler |
| `tests/test_agent_queue.py` | Create | Queue unit tests |
| `tests/test_agent_whatsapp.py` | Create | WhatsApp sender tests |
| `tests/test_agent_route.py` | Create | Route tests |
| `tests/test_agent_git_ops.py` | Create | Git ops tests |

---

## Task 1: Config

**Files:**
- Create: `agent/__init__.py`
- Create: `agent/config.py`

- [ ] **Step 1: Create `agent/__init__.py`** (empty)

```python
# agent/__init__.py
```

- [ ] **Step 2: Write `agent/config.py`**

```python
# agent/config.py
import os

# Owner's WhatsApp phone (E.164 format, e.g. "+972501234567")
# The agent ONLY accepts commands from this number.
OWNER_PHONE: str = os.environ["OWNER_PHONE"]

# Twilio credentials (already in .env)
TWILIO_ACCOUNT_SID: str = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN: str = os.environ["TWILIO_AUTH_TOKEN"]
# The Twilio number used to SEND messages back to the owner
TWILIO_PHONE_NUMBER: str = os.environ["TWILIO_PHONE_NUMBER"]

# Anthropic API key (for claude CLI)
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]

# Absolute path to the project root (this repo)
PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Path to the SQLite queue DB file
QUEUE_DB_PATH: str = os.path.join(PROJECT_ROOT, "agent", "agent_queue.db")

# How long (seconds) to wait for owner approval before aborting
APPROVAL_TIMEOUT_SECONDS: int = int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "600"))  # 10 min

# Max retries before giving up on a task
MAX_TASK_RETRIES: int = 2

# Branch where agent does all work
AGENT_BRANCH: str = "agent/work"

# Railway project name (used in CLI commands)
RAILWAY_PROJECT: str = os.getenv("RAILWAY_PROJECT", "maya-ai")
```

- [ ] **Step 3: Add `OWNER_PHONE` to `.env`**

Open `.env` and add:
```
OWNER_PHONE=+972XXXXXXXXX
```
Replace with the actual owner WhatsApp number in E.164 format.

- [ ] **Step 4: Commit**

```bash
git add agent/__init__.py agent/config.py
git commit -m "feat(agent): add config module"
```

---

## Task 2: SQLite Task Queue

**Files:**
- Create: `agent/queue.py`
- Create: `tests/test_agent_queue.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_agent_queue.py
import os, tempfile, pytest
os.environ.setdefault("OWNER_PHONE", "+972500000000")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "token_test")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+1234567890")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

from agent.queue import TaskQueue, TaskStatus, ApprovalStatus

@pytest.fixture
def q(tmp_path):
    db = str(tmp_path / "test.db")
    return TaskQueue(db_path=db)

def test_enqueue_and_fetch(q):
    task_id = q.enqueue("fix the bug in whatsapp_history.py")
    task = q.fetch_next_pending()
    assert task is not None
    assert task["id"] == task_id
    assert task["command"] == "fix the bug in whatsapp_history.py"
    assert task["status"] == TaskStatus.PENDING

def test_set_running(q):
    task_id = q.enqueue("build dashboard tab")
    q.set_running(task_id)
    task = q.get_task(task_id)
    assert task["status"] == TaskStatus.RUNNING

def test_set_done(q):
    task_id = q.enqueue("run tests")
    q.set_running(task_id)
    q.set_done(task_id, result="All tests passed")
    task = q.get_task(task_id)
    assert task["status"] == TaskStatus.DONE
    assert task["result"] == "All tests passed"

def test_set_failed(q):
    task_id = q.enqueue("deploy")
    q.set_running(task_id)
    q.set_failed(task_id, error="Railway CLI not found", attempt=1)
    task = q.get_task(task_id)
    assert task["status"] == TaskStatus.FAILED
    assert task["attempt"] == 1

def test_create_approval_and_resolve(q):
    task_id = q.enqueue("push to main")
    approval_id = q.create_approval(task_id, action="push", summary="Added WhatsApp fix")
    pending = q.get_pending_approval()
    assert pending is not None
    assert pending["action"] == "push"
    q.resolve_approval(approval_id, approved=True)
    resolved = q.get_approval(approval_id)
    assert resolved["status"] == ApprovalStatus.APPROVED

def test_no_pending_task_when_empty(q):
    assert q.fetch_next_pending() is None

def test_handle_incoming_approval_yes(q):
    task_id = q.enqueue("push")
    approval_id = q.create_approval(task_id, action="deploy", summary="Deploy v2")
    q.handle_incoming_message("כן")
    resolved = q.get_approval(approval_id)
    assert resolved["status"] == ApprovalStatus.APPROVED

def test_handle_incoming_approval_no(q):
    task_id = q.enqueue("push")
    approval_id = q.create_approval(task_id, action="deploy", summary="Deploy v2")
    q.handle_incoming_message("לא")
    resolved = q.get_approval(approval_id)
    assert resolved["status"] == ApprovalStatus.REJECTED
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd c:\Users\lidor\maya-ai
python -m pytest tests/test_agent_queue.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'agent.queue'`

- [ ] **Step 3: Implement `agent/queue.py`**

```python
# agent/queue.py
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Optional

from agent.config import QUEUE_DB_PATH


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    FAILED = "failed"


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


_APPROVAL_TRIGGERS = {"כן", "yes", "y", "כן."}
_REJECTION_TRIGGERS = {"לא", "no", "n", "לא."}


class TaskQueue:
    def __init__(self, db_path: str = QUEUE_DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempt INTEGER NOT NULL DEFAULT 0,
                    result TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    resolved_at REAL
                );
            """)

    def enqueue(self, command: str) -> str:
        task_id = str(uuid.uuid4())
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tasks (id, command, status, created_at, updated_at) VALUES (?,?,?,?,?)",
                (task_id, command, TaskStatus.PENDING, now, now),
            )
        return task_id

    def fetch_next_pending(self) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE status=? ORDER BY created_at LIMIT 1",
                (TaskStatus.PENDING,),
            ).fetchone()
            return dict(row) if row else None

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row) if row else None

    def set_running(self, task_id: str):
        self._update_task(task_id, status=TaskStatus.RUNNING)

    def set_done(self, task_id: str, result: str):
        self._update_task(task_id, status=TaskStatus.DONE, result=result)

    def set_failed(self, task_id: str, error: str, attempt: int):
        self._update_task(task_id, status=TaskStatus.FAILED, error=error, attempt=attempt)

    def set_awaiting_approval(self, task_id: str):
        self._update_task(task_id, status=TaskStatus.AWAITING_APPROVAL)

    def _update_task(self, task_id: str, **fields):
        fields["updated_at"] = time.time()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [task_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE tasks SET {set_clause} WHERE id=?", values)

    def create_approval(self, task_id: str, action: str, summary: str) -> str:
        approval_id = str(uuid.uuid4())
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO approvals (id, task_id, action, summary, status, created_at) VALUES (?,?,?,?,?,?)",
                (approval_id, task_id, action, summary, ApprovalStatus.PENDING, now),
            )
        return approval_id

    def get_pending_approval(self) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE status=? ORDER BY created_at LIMIT 1",
                (ApprovalStatus.PENDING,),
            ).fetchone()
            return dict(row) if row else None

    def get_approval(self, approval_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            return dict(row) if row else None

    def resolve_approval(self, approval_id: str, approved: bool):
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        with self._conn() as conn:
            conn.execute(
                "UPDATE approvals SET status=?, resolved_at=? WHERE id=?",
                (status, time.time(), approval_id),
            )

    def handle_incoming_message(self, message: str) -> bool:
        """
        Called when the owner sends a WhatsApp reply.
        If there's a pending approval, resolve it.
        Returns True if message was consumed as an approval response.
        """
        text = message.strip().lower()
        pending = self.get_pending_approval()
        if pending is None:
            return False
        if text in _APPROVAL_TRIGGERS:
            self.resolve_approval(pending["id"], approved=True)
            return True
        if text in _REJECTION_TRIGGERS:
            self.resolve_approval(pending["id"], approved=False)
            return True
        return False
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_agent_queue.py -v
```
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/queue.py tests/test_agent_queue.py
git commit -m "feat(agent): add SQLite task queue"
```

---

## Task 3: WhatsApp Sender

**Files:**
- Create: `agent/whatsapp.py`
- Create: `tests/test_agent_whatsapp.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_agent_whatsapp.py
import os
os.environ.setdefault("OWNER_PHONE", "+972500000000")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "token_test")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+1234567890")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

from unittest.mock import patch, MagicMock
from agent.whatsapp import send_to_owner

def test_send_to_owner_calls_twilio():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SM123")
    with patch("agent.whatsapp.Client", return_value=mock_client):
        send_to_owner("Task complete!")
    mock_client.messages.create.assert_called_once_with(
        from_="whatsapp:+1234567890",
        to="whatsapp:+972500000000",
        body="Task complete!",
    )

def test_send_to_owner_truncates_long_message():
    long_msg = "x" * 2000
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SM123")
    with patch("agent.whatsapp.Client", return_value=mock_client):
        send_to_owner(long_msg)
    sent_body = mock_client.messages.create.call_args[1]["body"]
    assert len(sent_body) <= 1600
    assert sent_body.endswith("... [truncated]")
```

- [ ] **Step 2: Run test — verify it fails**

```bash
python -m pytest tests/test_agent_whatsapp.py -v
```
Expected: `ModuleNotFoundError: No module named 'agent.whatsapp'`

- [ ] **Step 3: Implement `agent/whatsapp.py`**

```python
# agent/whatsapp.py
import logging
from twilio.rest import Client

from agent.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    OWNER_PHONE,
)

logger = logging.getLogger(__name__)
_MAX_MSG_LEN = 1600


def send_to_owner(message: str) -> None:
    """Send a WhatsApp message to the owner via Twilio."""
    if len(message) > _MAX_MSG_LEN:
        message = message[: _MAX_MSG_LEN - 15] + "... [truncated]"
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
            to=f"whatsapp:{OWNER_PHONE}",
            body=message,
        )
        logger.info("WhatsApp sent sid=%s", msg.sid)
    except Exception as exc:
        logger.error("Failed to send WhatsApp: %s", exc)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_agent_whatsapp.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/whatsapp.py tests/test_agent_whatsapp.py
git commit -m "feat(agent): add WhatsApp sender"
```

---

## Task 4: FastAPI Route `/agent/command`

**Files:**
- Create: `app/routes/dev_agent.py`
- Create: `tests/test_agent_route.py`
- Modify: `main.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_agent_route.py
import os
os.environ.setdefault("OWNER_PHONE", "+972500000000")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "token_test")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+1234567890")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Patch queue before importing app
with patch("agent.queue.TaskQueue") as mock_queue_cls:
    mock_q = MagicMock()
    mock_queue_cls.return_value = mock_q
    from app.routes.dev_agent import router, get_queue
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

def twilio_form(from_number: str, body: str) -> dict:
    return {"From": f"whatsapp:{from_number}", "Body": body}

def test_unknown_sender_is_rejected():
    resp = client.post("/agent/command", data=twilio_form("+972599999999", "do something"))
    assert resp.status_code == 200
    xml = resp.text
    assert "<Response/>" in xml or "<Response>" in xml

def test_known_sender_creates_task():
    mock_q.handle_incoming_message.return_value = False
    resp = client.post(
        "/agent/command",
        data=twilio_form("+972500000000", "fix the bug in whatsapp_history.py"),
    )
    assert resp.status_code == 200
    mock_q.enqueue.assert_called_with("fix the bug in whatsapp_history.py")

def test_approval_reply_is_not_enqueued():
    mock_q.handle_incoming_message.return_value = True  # consumed as approval
    mock_q.enqueue.reset_mock()
    resp = client.post(
        "/agent/command",
        data=twilio_form("+972500000000", "כן"),
    )
    assert resp.status_code == 200
    mock_q.enqueue.assert_not_called()
```

- [ ] **Step 2: Run test — verify it fails**

```bash
python -m pytest tests/test_agent_route.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.routes.dev_agent'`

- [ ] **Step 3: Implement `app/routes/dev_agent.py`**

```python
# app/routes/dev_agent.py
"""
POST /agent/command
====================
Twilio sends WhatsApp messages here.
Only messages from OWNER_PHONE are accepted.
Incoming approvals (כן/לא) resolve pending approvals in the queue.
All other messages are enqueued as tasks for the daemon.
"""
import logging
from functools import lru_cache

from fastapi import APIRouter, Form, Response

from agent.config import OWNER_PHONE
from agent.queue import TaskQueue

logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_queue() -> TaskQueue:
    return TaskQueue()


@router.post("/agent/command")
async def agent_command(
    From: str = Form(...),
    Body: str = Form(...),
) -> Response:
    """Receive a WhatsApp message from Twilio."""
    # Twilio sends From as "whatsapp:+972..."
    sender = From.replace("whatsapp:", "").strip()

    if sender != OWNER_PHONE:
        logger.warning("Ignored message from unknown sender: %s", sender)
        return Response(content="<Response/>", media_type="application/xml")

    q = get_queue()
    command = Body.strip()

    # Check if this is an approval response first
    consumed = q.handle_incoming_message(command)
    if consumed:
        logger.info("Approval response received: %s", command)
    else:
        task_id = q.enqueue(command)
        logger.info("Task enqueued id=%s command=%r", task_id, command)

    return Response(content="<Response/>", media_type="application/xml")
```

- [ ] **Step 4: Register route in `main.py`**

Open `main.py` and add after the existing imports:
```python
from app.routes.dev_agent import router as dev_agent_router
```
And after the other `app.include_router(...)` calls:
```python
app.include_router(dev_agent_router)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python -m pytest tests/test_agent_route.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/routes/dev_agent.py tests/test_agent_route.py main.py
git commit -m "feat(agent): add /agent/command WhatsApp route"
```

---

## Task 5: Git Operations

**Files:**
- Create: `agent/git_ops.py`
- Create: `tests/test_agent_git_ops.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_agent_git_ops.py
import os, subprocess, tempfile, pytest

os.environ.setdefault("OWNER_PHONE", "+972500000000")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "token_test")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+1234567890")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

from agent.git_ops import get_diff_summary, get_recent_commits, get_current_branch

def test_get_current_branch_returns_string():
    branch = get_current_branch()
    assert isinstance(branch, str)
    assert len(branch) > 0

def test_get_recent_commits_returns_list():
    commits = get_recent_commits(n=3)
    assert isinstance(commits, list)
    assert len(commits) <= 3
    for c in commits:
        assert "hash" in c
        assert "message" in c

def test_get_diff_summary_returns_string():
    summary = get_diff_summary(base="HEAD~1", head="HEAD")
    assert isinstance(summary, str)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_agent_git_ops.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `agent/git_ops.py`**

```python
# agent/git_ops.py
import subprocess
import logging
from typing import List, Dict

from agent.config import PROJECT_ROOT, AGENT_BRANCH

logger = logging.getLogger(__name__)


def _git(*args: str) -> str:
    """Run a git command in the project root and return stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def get_current_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD")


def get_recent_commits(n: int = 5) -> List[Dict[str, str]]:
    log = _git("log", f"-{n}", "--pretty=format:%h|%s")
    commits = []
    for line in log.splitlines():
        if "|" in line:
            hash_, msg = line.split("|", 1)
            commits.append({"hash": hash_, "message": msg})
    return commits


def get_diff_summary(base: str = "main", head: str = AGENT_BRANCH) -> str:
    """Return a human-readable summary of changes between base and head."""
    try:
        stat = _git("diff", "--stat", f"{base}...{head}")
        diff = _git("diff", "--unified=3", f"{base}...{head}")
        # Cap diff at 3000 chars to keep WhatsApp message reasonable
        if len(diff) > 3000:
            diff = diff[:3000] + "\n... [diff truncated, see git log for full changes]"
        return f"=== Changed files ===\n{stat}\n\n=== Diff ===\n{diff}"
    except RuntimeError as e:
        return f"Could not compute diff: {e}"


def prepare_agent_branch() -> None:
    """Reset agent/work branch from current main. Called before each task."""
    try:
        current = get_current_branch()
        if current != "main":
            _git("checkout", "main")
        _git("pull", "origin", "main")
        # Force-reset agent/work to main
        try:
            _git("branch", "-D", AGENT_BRANCH)
        except RuntimeError:
            pass  # branch didn't exist yet
        _git("checkout", "-b", AGENT_BRANCH)
        logger.info("Agent branch '%s' ready", AGENT_BRANCH)
    except RuntimeError as e:
        logger.error("Failed to prepare agent branch: %s", e)
        raise


def merge_to_main() -> None:
    """Merge agent/work into main and push."""
    _git("checkout", "main")
    _git("merge", "--no-ff", AGENT_BRANCH, "-m", "chore: merge agent/work into main")
    _git("push", "origin", "main")
    logger.info("Merged agent/work into main and pushed")
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_agent_git_ops.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/git_ops.py tests/test_agent_git_ops.py
git commit -m "feat(agent): add git operations module"
```

---

## Task 6: Context Builder

**Files:**
- Create: `agent/context.py`

No unit tests needed — this is a pure text assembly function tested implicitly via executor tests.

- [ ] **Step 1: Implement `agent/context.py`**

```python
# agent/context.py
"""
Builds the context preamble injected before every task prompt.
Gives Claude Code full situational awareness of the project.
"""
import subprocess
from agent.config import PROJECT_ROOT, AGENT_BRANCH
from agent.git_ops import get_current_branch, get_recent_commits


def _run(cmd: str) -> str:
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip()
    except Exception:
        return "(unavailable)"


def build_context() -> str:
    branch = get_current_branch()
    commits = get_recent_commits(n=5)
    commits_str = "\n".join(f"  {c['hash']} {c['message']}" for c in commits)

    # Check for failing tests
    test_status = _run("python -m pytest tests/ --tb=no -q 2>&1 | tail -5")

    return f"""
=== MAYA AI — Dev Agent Context ===

You are an autonomous development agent for the Maya AI project.
Project root: {PROJECT_ROOT}
Current branch: {branch}
Working branch: {AGENT_BRANCH}

Recent commits:
{commits_str}

Test status (last run):
{test_status}

=== RULES YOU MUST FOLLOW ===
1. Do all work on branch '{AGENT_BRANCH}' — never commit directly to main.
2. Before any `git push` or `railway up`: STOP and output a line that starts with
   APPROVAL_REQUIRED: followed by a summary of what you are about to do.
   Wait for the system to handle the approval — do not push yourself.
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

=== YOUR TASK ===
""".strip()
```

- [ ] **Step 2: Commit**

```bash
git add agent/context.py
git commit -m "feat(agent): add context builder"
```

---

## Task 7: Claude Code Executor

**Files:**
- Create: `agent/executor.py`

- [ ] **Step 1: Implement `agent/executor.py`**

```python
# agent/executor.py
"""
Runs `claude -p "<prompt>"` as a subprocess and parses the output for
special signals (APPROVAL_REQUIRED, TASK_COMPLETE, GUIDANCE_NEEDED).
"""
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

from agent.config import PROJECT_ROOT, ANTHROPIC_API_KEY
from agent.context import build_context

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    raw_output: str
    approval_required: Optional[str]   # summary string if approval needed, else None
    task_complete: Optional[str]        # summary string if done, else None
    guidance_needed: Optional[str]      # instructions string if owner needed, else None
    error: Optional[str]               # error message if execution failed


def run_task(command: str) -> ExecutionResult:
    """Run a dev task via Claude Code CLI and return the parsed result."""
    context = build_context()
    full_prompt = f"{context}\n{command}"

    logger.info("Running claude -p for command: %r", command[:80])

    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--allowedTools", "all"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,  # 30 min max per task
            env=_env_with_api_key(),
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            raw_output="",
            approval_required=None,
            task_complete=None,
            guidance_needed=None,
            error="Task timed out after 30 minutes",
        )
    except FileNotFoundError:
        return ExecutionResult(
            raw_output="",
            approval_required=None,
            task_complete=None,
            guidance_needed=None,
            error="Claude CLI not found. Is 'claude' in PATH?",
        )

    return _parse_output(output)


def _env_with_api_key() -> dict:
    import os
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
    return env


def _parse_output(output: str) -> ExecutionResult:
    approval_required = None
    task_complete = None
    guidance_needed = None

    for line in output.splitlines():
        if line.startswith("APPROVAL_REQUIRED:"):
            approval_required = line[len("APPROVAL_REQUIRED:"):].strip()
        elif line.startswith("TASK_COMPLETE:"):
            task_complete = line[len("TASK_COMPLETE:"):].strip()
        elif line.startswith("GUIDANCE_NEEDED:"):
            # Collect everything from here
            idx = output.find("GUIDANCE_NEEDED:")
            guidance_needed = output[idx + len("GUIDANCE_NEEDED:"):].strip()
            break

    return ExecutionResult(
        raw_output=output,
        approval_required=approval_required,
        task_complete=task_complete,
        guidance_needed=guidance_needed,
        error=None,
    )
```

- [ ] **Step 2: Commit**

```bash
git add agent/executor.py
git commit -m "feat(agent): add Claude Code executor"
```

---

## Task 8: Daemon Main Loop

**Files:**
- Create: `agent/daemon.py`

- [ ] **Step 1: Implement `agent/daemon.py`**

```python
# agent/daemon.py
"""
Maya Dev Agent — main daemon loop.

Run this script as a Windows background process (see install_scheduler.bat).
It polls the SQLite queue for tasks, runs them via Claude Code, handles
approval flows, and reports back via WhatsApp.

Loop cycle: 5 seconds when idle, immediate when task found.
"""
import logging
import time
import sys

from agent.config import APPROVAL_TIMEOUT_SECONDS, MAX_TASK_RETRIES
from agent.queue import TaskQueue, TaskStatus, ApprovalStatus
from agent.executor import run_task
from agent.git_ops import prepare_agent_branch, merge_to_main, get_diff_summary
from agent.whatsapp import send_to_owner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agent.daemon")

POLL_INTERVAL = 5  # seconds between queue checks


def run_daemon():
    logger.info("Maya Dev Agent daemon starting...")
    send_to_owner("Maya Dev Agent started and ready. Send me a task!")
    q = TaskQueue()

    while True:
        task = q.fetch_next_pending()
        if task is None:
            time.sleep(POLL_INTERVAL)
            continue

        task_id = task["id"]
        command = task["command"]
        logger.info("Processing task %s: %r", task_id, command[:60])

        q.set_running(task_id)
        send_to_owner(f"Starting task: {command[:200]}")

        _process_task(q, task_id, command, attempt=0)


def _process_task(q: TaskQueue, task_id: str, command: str, attempt: int):
    # Prepare isolated branch
    try:
        prepare_agent_branch()
    except RuntimeError as e:
        _fail_task(q, task_id, f"Could not prepare git branch: {e}", attempt)
        return

    # Run Claude Code
    result = run_task(command)

    if result.error:
        if attempt < MAX_TASK_RETRIES:
            logger.warning("Task %s failed (attempt %d): %s — retrying", task_id, attempt, result.error)
            send_to_owner(f"Attempt {attempt + 1} failed: {result.error}\nRetrying...")
            time.sleep(3)
            _process_task(q, task_id, command, attempt + 1)
        else:
            _fail_task(q, task_id, result.error, attempt)
        return

    # Guidance needed (human input required)
    if result.guidance_needed:
        q.set_done(task_id, result=f"Guidance provided to owner")
        send_to_owner(
            f"I need your help for this task:\n\n{result.guidance_needed[:1400]}"
        )
        return

    # Approval required before push/deploy
    if result.approval_required:
        diff = get_diff_summary()
        approval_msg = (
            f"Task ready to deploy.\n\n"
            f"Summary: {result.approval_required}\n\n"
            f"{diff[:800]}\n\n"
            f"Reply כן to push+deploy, or לא to cancel."
        )
        q.set_awaiting_approval(task_id)
        approval_id = q.create_approval(task_id, action="push", summary=result.approval_required)
        send_to_owner(approval_msg)

        # Wait for approval
        approved = _wait_for_approval(q, approval_id)
        if approved:
            try:
                merge_to_main()
                send_to_owner("Deployed to production. All done!")
                q.set_done(task_id, result="Deployed successfully")
            except RuntimeError as e:
                _fail_task(q, task_id, f"Deploy failed: {e}", attempt)
        else:
            q.set_done(task_id, result="Cancelled by owner")
            send_to_owner("Cancelled. No changes pushed.")
        return

    # Task completed without deploy
    if result.task_complete:
        q.set_done(task_id, result=result.task_complete)
        send_to_owner(f"Done! {result.task_complete[:400]}")
    else:
        # Completed but no explicit signal — report raw output tail
        q.set_done(task_id, result="Completed (no explicit signal)")
        tail = result.raw_output[-600:] if result.raw_output else "(no output)"
        send_to_owner(f"Task finished.\n\n{tail}")


def _wait_for_approval(q: TaskQueue, approval_id: str) -> bool:
    """Poll queue until approval is resolved or timeout expires. Returns True if approved."""
    deadline = time.time() + APPROVAL_TIMEOUT_SECONDS
    while time.time() < deadline:
        approval = q.get_approval(approval_id)
        if approval and approval["status"] == ApprovalStatus.APPROVED:
            return True
        if approval and approval["status"] == ApprovalStatus.REJECTED:
            return False
        time.sleep(3)
    # Timeout
    q.resolve_approval(approval_id, approved=False)
    send_to_owner("Approval timed out (10 min). Task cancelled — nothing was pushed.")
    return False


def _fail_task(q: TaskQueue, task_id: str, error: str, attempt: int):
    q.set_failed(task_id, error=error, attempt=attempt)
    send_to_owner(
        f"Task failed after {attempt + 1} attempt(s).\n\n"
        f"Error: {error[:600]}\n\n"
        f"What should I do next?"
    )


if __name__ == "__main__":
    run_daemon()
```

- [ ] **Step 2: Commit**

```bash
git add agent/daemon.py
git commit -m "feat(agent): add daemon main loop"
```

---

## Task 9: Windows Task Scheduler Setup

**Files:**
- Create: `agent/install_scheduler.bat`
- Create: `agent/run_daemon.bat`

- [ ] **Step 1: Create `agent/run_daemon.bat`** (the script Task Scheduler will call)

```batch
@echo off
cd /d C:\Users\lidor\maya-ai
call venv\Scripts\activate.bat
python -m agent.daemon >> agent\daemon.log 2>&1
```

- [ ] **Step 2: Create `agent/install_scheduler.bat`**

```batch
@echo off
echo Registering Maya Dev Agent with Windows Task Scheduler...

schtasks /create /tn "MayaDevAgent" /tr "C:\Users\lidor\maya-ai\agent\run_daemon.bat" /sc onstart /ru "%USERNAME%" /rl HIGHEST /f

echo Done. The agent will now start automatically on boot.
echo To start it now without rebooting, run:
echo   schtasks /run /tn "MayaDevAgent"
pause
```

- [ ] **Step 3: Run `install_scheduler.bat` as Administrator**

Right-click `agent\install_scheduler.bat` → "Run as administrator"

Expected output: `Done. The agent will now start automatically on boot.`

- [ ] **Step 4: Start the daemon now (without reboot)**

```bash
schtasks /run /tn "MayaDevAgent"
```

- [ ] **Step 5: Verify daemon started**

```bash
# Check the log file after 5 seconds
type agent\daemon.log
```
Expected: Line containing `Maya Dev Agent daemon starting...`

- [ ] **Step 6: Commit**

```bash
git add agent/install_scheduler.bat agent/run_daemon.bat
git commit -m "feat(agent): add Windows Task Scheduler setup scripts"
```

---

## Task 10: End-to-End Smoke Test

No code to write — this is a manual verification checklist.

- [ ] **Step 1: Verify FastAPI route is live**

```bash
# Start FastAPI locally
uvicorn main:app --port 8000

# In another terminal, simulate a Twilio webhook
curl -X POST http://localhost:8000/agent/command \
  -d "From=whatsapp:%2B972500000000&Body=status" \
  -H "Content-Type: application/x-www-form-urlencoded"
```
Expected: `<Response/>`

- [ ] **Step 2: Send "status" from your WhatsApp to the Twilio number**

WhatsApp message: `status`

Expected WhatsApp reply within 60 seconds: agent reports current branch + last commits.

- [ ] **Step 3: Send a simple task**

WhatsApp message: `תגיד לי מה יש בקובץ app/config`

Expected: Agent reads the file and reports contents via WhatsApp.

- [ ] **Step 4: Test approval flow**

WhatsApp message: `תוסיף הערה בתחילת קובץ main.py ואז תשאל אישור לפני שתדחוף`

Expected:
1. Agent makes the change
2. Sends WhatsApp with diff summary + "Reply כן to push"
3. Reply `כן`
4. Agent pushes and confirms

- [ ] **Step 5: Commit smoke test results**

If everything passed:
```bash
git add -A
git commit -m "test(agent): end-to-end smoke test passed"
```

---

## Summary

After completing all tasks:
- WhatsApp message from owner's phone → triggers Claude Code → does dev work autonomously
- Before any push/deploy → sends diff to WhatsApp and waits for "כן"
- Guidance mode: agent sends step-by-step instructions when human input needed
- Error recovery: retries twice, then reports with clear next steps
- Always-on: Windows Task Scheduler restarts daemon on boot
- Production-safe: all work on `agent/work` branch, main never touched without approval
