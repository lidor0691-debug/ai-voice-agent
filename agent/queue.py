# agent/queue.py
import os
import time
import uuid
from typing import Optional

from supabase import create_client, Client


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


def _get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


class TaskQueue:
    def __init__(self):
        self._sb = _get_client()

    def enqueue(self, command: str) -> str:
        task_id = str(uuid.uuid4())
        now = time.time()
        self._sb.table("agent_tasks").insert({
            "id": task_id,
            "command": command,
            "status": TaskStatus.PENDING,
            "attempt": 0,
            "created_at": now,
            "updated_at": now,
        }).execute()
        return task_id

    def fetch_next_pending(self) -> Optional[dict]:
        res = (
            self._sb.table("agent_tasks")
            .select("*")
            .eq("status", TaskStatus.PENDING)
            .order("created_at")
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def get_task(self, task_id: str) -> Optional[dict]:
        res = self._sb.table("agent_tasks").select("*").eq("id", task_id).execute()
        return res.data[0] if res.data else None

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
        self._sb.table("agent_tasks").update(fields).eq("id", task_id).execute()

    def create_approval(self, task_id: str, action: str, summary: str) -> str:
        approval_id = str(uuid.uuid4())
        now = time.time()
        self._sb.table("agent_approvals").insert({
            "id": approval_id,
            "task_id": task_id,
            "action": action,
            "summary": summary,
            "status": ApprovalStatus.PENDING,
            "created_at": now,
        }).execute()
        return approval_id

    def get_pending_approval(self) -> Optional[dict]:
        res = (
            self._sb.table("agent_approvals")
            .select("*")
            .eq("status", ApprovalStatus.PENDING)
            .order("created_at")
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def get_approval(self, approval_id: str) -> Optional[dict]:
        res = self._sb.table("agent_approvals").select("*").eq("id", approval_id).execute()
        return res.data[0] if res.data else None

    def resolve_approval(self, approval_id: str, approved: bool):
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        self._sb.table("agent_approvals").update({
            "status": status,
            "resolved_at": time.time(),
        }).eq("id", approval_id).execute()

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
