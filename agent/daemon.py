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
