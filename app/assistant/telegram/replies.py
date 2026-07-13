"""Pure Hebrew owner-facing reply formatting. No I/O.

Replies are short, action-first, and owner-facing only (never customer-facing).
They never include internal field names, ids, tokens, or secrets.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.assistant.nlp.contract import MessageType, SendPlan

_DRY_PREFIX = "🧪 בדיקה — "

_MSG_TYPE_HE = {
    MessageType.AGREEMENT: "הסכם",
    MessageType.DEPOSIT: "מקדמה",
    MessageType.VIDEO: "סרטון",
    MessageType.LESSON_COORDINATION: "תיאום שיעור",
    MessageType.CUSTOM: "הודעה",
}

_PLAN_HE = {
    SendPlan.GROUP_MANUAL: "קבוצה (ידני)",
    SendPlan.MANUAL_FALLBACK: "ידני",
    SendPlan.API_TEMPLATE: "תבנית",
    SendPlan.API_FREEFORM: "טקסט חופשי",
}


def _msg_he(message_type: Optional[MessageType]) -> str:
    if isinstance(message_type, MessageType):
        return _MSG_TYPE_HE.get(message_type, "הודעה")
    return "הודעה"


def _plan_he(send_plan: Optional[SendPlan]) -> Optional[str]:
    if isinstance(send_plan, SendPlan):
        return _PLAN_HE.get(send_plan)
    return None


def _fmt_dt(iso: Optional[str]) -> str:
    """'2026-06-29T18:00:00' -> '29.06 18:00'; pass through on parse failure."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{dt.day:02d}.{dt.month:02d} {dt.hour:02d}:{dt.minute:02d}"


def reply_scheduled(
    *,
    recipient_name: Optional[str],
    message_type: Optional[MessageType],
    scheduled_at_local: Optional[str],
    send_plan: Optional[SendPlan] = None,
    dry_run: bool = False,
) -> str:
    who = recipient_name or "—"
    when = _fmt_dt(scheduled_at_local)
    plan = _plan_he(send_plan)
    body = f"✅ נקבע: {_msg_he(message_type)} ל{who} — שליחה {when}"
    if plan:
        body += f" ({plan})"
    body += "."
    return (_DRY_PREFIX + body) if dry_run else body


def reply_missing_send_time(
    *,
    recipient_name: Optional[str],
    message_type: Optional[MessageType],
    related_event_date: Optional[str] = None,
    dry_run: bool = False,
) -> str:
    who = recipient_name or "—"
    body = f"❓ מתי לשלוח? הבנתי: {_msg_he(message_type)} ל{who}"
    if related_event_date:
        body += f" (אירוע {_fmt_dt(related_event_date) or related_event_date})"
    body += "."
    return (_DRY_PREFIX + body) if dry_run else body


def reply_missing_recipient(*, dry_run: bool = False) -> str:
    body = "❓ למי לשלוח?"
    return (_DRY_PREFIX + body) if dry_run else body


def reply_unknown_recipient(*, recipient_name: Optional[str], dry_run: bool = False) -> str:
    who = recipient_name or "—"
    body = f'🤔 לא מצאתי איש קשר בשם "{who}". (הוספת אנשי קשר תיתמך בהמשך.)'
    return (_DRY_PREFIX + body) if dry_run else body


def reply_ambiguous(*, recipient_name: Optional[str], dry_run: bool = False) -> str:
    who = recipient_name or "—"
    body = f'🤔 יש כמה אנשי קשר בשם "{who}". למי התכוונת?'
    return (_DRY_PREFIX + body) if dry_run else body


# ── immediate WhatsApp send (pilot) — owner-facing result replies ─────────────

def reply_wa_sent(name: Optional[str]) -> str:
    return f"✅ נשלח WhatsApp ל{name or '—'}"


def reply_wa_window_closed(name: Optional[str]) -> str:
    who = name or "הנמען"
    return (
        f"אי אפשר לשלוח עדיין — צריך ש{who} ישלח/תשלח קודם הודעה "
        f"למספר מאיה כדי לפתוח חלון WhatsApp."
    )


def reply_wa_missing_phone() -> str:
    return "מצאתי את איש הקשר, אבל אין לו מספר טלפון."


def reply_wa_no_lead() -> str:
    return "מצאתי את איש הקשר, אבל אין ליד תואם לשליחה."


def reply_wa_ambiguous_contact() -> str:
    return "מצאתי יותר מאיש קשר אחד בשם הזה. צריך לדייק למי לשלוח."


def reply_wa_ambiguous_lead() -> str:
    return "מצאתי יותר מליד אחד עם המספר הזה. עצרתי כדי לא לשלוח בטעות."


def reply_wa_disabled() -> str:
    return "שליחת WhatsApp מטלגרם עדיין כבויה. כרגע זו בדיקה בלבד."


def reply_wa_contact_not_found() -> str:
    return "לא מצאתי איש קשר בשם הזה."


def reply_wa_no_body() -> str:
    return 'לא הצלחתי לזהות את תוכן ההודעה. כתבי אחרי "הודעה:".'


def reply_wa_not_configured() -> str:
    return "שליחת WhatsApp לא מוגדרת כרגע."


def reply_wa_send_failed() -> str:
    return "שליחת ה-WhatsApp נכשלה. אפשר לנסות שוב מאוחר יותר."


# ── scheduled WhatsApp job (PR-A) — persist-only, never sends ─────────────────

def reply_wa_schedule_save_failed() -> str:
    return "לא הצלחתי לשמור את המשימה המתוזמנת. אפשר לנסות שוב."
