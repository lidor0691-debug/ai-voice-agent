"""
Maya Dev Agent — conversational daemon loop.

Each WhatsApp message from the owner starts a conversation turn:
1. Save message to Supabase conversation history
2. Load history + build prompt
3. Run claude -p
4. If APPROVAL_REQUIRED: ask for approval, wait, then execute code task
5. Save response + send via WhatsApp
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
    conv.save("user", command)

    history_msgs = conv.get_history(limit=HISTORY_LIMIT)
    history_str = format_history(history_msgs[:-1])
    context = build_context(history=history_str)
    full_prompt = f"{context}\n\n{command}\n\n(חשוב: ענה בעברית בלבד)"

    result = run_conversation_turn(full_prompt)

    if result.error:
        response = f"שגיאה: {result.error}"
        conv.save("assistant", response)
        send_to_owner(response)
        q.set_failed(task_id, error=result.error, attempt=0)
        return

    if result.task_complete:
        response_text = result.task_complete
    else:
        response_text = result.raw_output[-1000:].strip() if result.raw_output else "(אין פלט)"

    if result.approval_required:
        _handle_approval(q, conv, task_id, command, result.approval_required)
        return

    if result.guidance_needed:
        response = result.guidance_needed[:1400]
        conv.save("assistant", response)
        send_to_owner(response)
        q.set_done(task_id, result="Guidance sent")
        return

    conv.save("assistant", response_text)
    send_to_owner(response_text[:1500])
    q.set_done(task_id, result="Conversation turn complete")


def _handle_approval(q: TaskQueue, conv: ConversationStore, task_id: str, command: str, summary: str):
    try:
        prepare_agent_branch()
    except RuntimeError as e:
        msg = f"לא הצלחתי להכין branch: {e}"
        conv.save("assistant", msg)
        send_to_owner(msg)
        q.set_failed(task_id, error=str(e), attempt=0)
        return

    approval_msg = f"רוצה לבצע:\n\n{summary}\n\nשלח כן לאישור או לא לביטול."
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

    send_to_owner(f"מתחיל: {command[:200]}")
    result = run_task(command)

    if result.error:
        msg = f"נכשל: {result.error[:600]}"
        conv.save("assistant", msg)
        send_to_owner(msg)
        q.set_failed(task_id, error=result.error, attempt=0)
        return

    if result.approval_required:
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
