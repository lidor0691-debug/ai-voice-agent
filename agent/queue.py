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
        except Exception:
            conn.rollback()
            raise
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
