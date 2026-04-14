# tests/test_agent_queue.py
import os, pytest
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
