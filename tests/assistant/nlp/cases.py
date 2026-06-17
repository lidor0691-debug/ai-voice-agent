"""The 25 Hebrew-first eval cases. TEST-ONLY.

Each case pins expected Stage-1 parse output for a natural-language command.
A subset also carries a Stage-2 ``resolve`` expectation so the resolver decision
tree is exercised end-to-end.

MUST-PASS set (event-date vs send-date): cases 1, 12, 13, 14, 15, 21, 22, 23.

All dates assume the frozen clock NOW = 2026-06-15 12:00 (Mon), Asia/Jerusalem:
  today = 2026-06-15, tomorrow = 2026-06-16, day-after = 2026-06-17.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.assistant.nlp.contract import MessageType, ParseStatus, RecipientType, SendPlan


@dataclass
class Case:
    id: int
    description: str
    text: str
    expect: Dict[str, object]
    must_pass: bool = False
    resolve: Optional[Dict[str, object]] = None


CASES: List[Case] = [
    Case(
        id=1,
        description="ב-<date> = SEND date, with explicit time",
        text="שלח לדנה תזכורת ב-29.6 בשעה 18:00",
        must_pass=True,
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.CUSTOM,
            "scheduled_at_local": "2026-06-29T18:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
    ),
    Case(
        id=2,
        description="relative day 'tomorrow' + explicit time",
        text="שלח לדנה הודעה מחר בשעה 14:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.CUSTOM,
            "scheduled_at_local": "2026-06-16T14:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
    ),
    Case(
        id=3,
        description="teacher + lesson reminder, today + explicit time",
        text="תזכיר ליוסי על השיעור היום ב-20:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "יוסי",
            "recipient_type": RecipientType.TEACHER,
            "message_type": MessageType.LESSON_COORDINATION,
            "scheduled_at_local": "2026-06-15T20:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
    ),
    Case(
        id=4,
        description="agreement, tomorrow + explicit time",
        text="שלח לרבקה הסכם מחר ב-09:30",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "רבקה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.AGREEMENT,
            "scheduled_at_local": "2026-06-16T09:30:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
    ),
    Case(
        id=5,
        description="no date/time at all -> needs_clarification (missing send time)",
        text="שלח לדנה הודעה",
        expect={
            "status": ParseStatus.NEEDS_CLARIFICATION,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.CUSTOM,
            "scheduled_at_local": None,
            "related_event_date": None,
        },
    ),
    Case(
        id=6,
        description="group recipient -> parsed, resolves to group_manual",
        text="שלח לקבוצת בוקר הודעה מחר ב-09:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "קבוצת בוקר",
            "recipient_type": RecipientType.GROUP,
            "message_type": MessageType.CUSTOM,
            "scheduled_at_local": "2026-06-16T09:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
        resolve={
            "contact_name": "קבוצת בוקר",
            "within_window": False,
            "active_templates": [],
            "plan": SendPlan.GROUP_MANUAL,
        },
    ),
    Case(
        id=7,
        description="deposit outside window, no active template -> manual_fallback",
        text="שלח לרבקה מקדמה מחר ב-12:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "רבקה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.DEPOSIT,
            "scheduled_at_local": "2026-06-16T12:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
        resolve={
            "contact_name": "רבקה",
            "within_window": False,
            "active_templates": [],
            "plan": SendPlan.MANUAL_FALLBACK,
        },
    ),
    Case(
        id=8,
        description="agreement outside window, active template -> api_template",
        text="שלח לאבי הסכם היום ב-16:30",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "אבי",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.AGREEMENT,
            "scheduled_at_local": "2026-06-15T16:30:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
        resolve={
            "contact_name": "אבי",
            "within_window": False,
            "active_templates": [MessageType.AGREEMENT],
            "plan": SendPlan.API_TEMPLATE,
        },
    ),
    Case(
        id=9,
        description="lesson coordination with teacher via 'עם', tomorrow + time",
        text="תאם שיעור עם יוסי מחר ב-08:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "יוסי",
            "recipient_type": RecipientType.TEACHER,
            "message_type": MessageType.LESSON_COORDINATION,
            "scheduled_at_local": "2026-06-16T08:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
    ),
    Case(
        id=10,
        description="video, tomorrow + explicit time",
        text="שלח לדנה סרטון מחר ב-19:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.VIDEO,
            "scheduled_at_local": "2026-06-16T19:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
    ),
    Case(
        id=11,
        description="relative day 'day after tomorrow' + explicit time",
        text="שלח לדנה הודעה מחרתיים ב-11:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.CUSTOM,
            "scheduled_at_local": "2026-06-17T11:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
    ),
    Case(
        id=12,
        description="ל-<date> = EVENT date only, no send time -> needs_clarification",
        text="תשלח לרבקה את ההסכם ל-29.6",
        must_pass=True,
        expect={
            "status": ParseStatus.NEEDS_CLARIFICATION,
            "recipient_name": "רבקה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.AGREEMENT,
            "scheduled_at_local": None,
            "related_event_date": "2026-06-29",
        },
    ),
    Case(
        id=13,
        description="ל-<event> + SEND tomorrow at explicit time",
        text="תשלח לרבקה את ההסכם ל-29.6 מחר ב-10:00",
        must_pass=True,
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "רבקה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.AGREEMENT,
            "scheduled_at_local": "2026-06-16T10:00:00",
            "is_explicit_time": True,
            "related_event_date": "2026-06-29",
        },
    ),
    Case(
        id=14,
        description="עד <date> = EVENT/deadline only, no send time -> needs_clarification",
        text="שלח לאבי מקדמה עד 29.6",
        must_pass=True,
        expect={
            "status": ParseStatus.NEEDS_CLARIFICATION,
            "recipient_name": "אבי",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.DEPOSIT,
            "scheduled_at_local": None,
            "related_event_date": "2026-06-29",
        },
    ),
    Case(
        id=15,
        description="עד <event> + explicit SEND today at time",
        text="שלח לאבי מקדמה עד 29.6, תשלח היום ב-15:00",
        must_pass=True,
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "אבי",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.DEPOSIT,
            "scheduled_at_local": "2026-06-15T15:00:00",
            "is_explicit_time": True,
            "related_event_date": "2026-06-29",
        },
    ),
    Case(
        id=16,
        description="ב-<date> SEND with explicit time, no event",
        text="שלח לרבקה הודעה ב-25.6 בשעה 13:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "רבקה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.CUSTOM,
            "scheduled_at_local": "2026-06-25T13:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
    ),
    Case(
        id=17,
        description="ב-<date> SEND, no time -> default 10:00 (inferred)",
        text="שלח לאבי הסכם ב-30.6",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "אבי",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.AGREEMENT,
            "scheduled_at_local": "2026-06-30T10:00:00",
            "is_explicit_time": False,
            "related_event_date": None,
        },
    ),
    Case(
        id=18,
        description="של <date> = EVENT only -> needs_clarification",
        text="שלח לדנה הודעה של 28.6",
        expect={
            "status": ParseStatus.NEEDS_CLARIFICATION,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.CUSTOM,
            "scheduled_at_local": None,
            "related_event_date": "2026-06-28",
        },
    ),
    Case(
        id=19,
        description="teacher lesson coordination, ב-<date> no time -> default 10:00",
        text="שלח ליוסי תיאום שיעור ב-18.6",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "יוסי",
            "recipient_type": RecipientType.TEACHER,
            "message_type": MessageType.LESSON_COORDINATION,
            "scheduled_at_local": "2026-06-18T10:00:00",
            "is_explicit_time": False,
            "related_event_date": None,
        },
    ),
    Case(
        id=20,
        description="relative day 'tomorrow', NO time -> default 10:00 (CORRECTED)",
        text="שלח לדנה הודעה מחר",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.CUSTOM,
            "scheduled_at_local": "2026-06-16T10:00:00",
            "is_explicit_time": False,
            "related_event_date": None,
        },
    ),
    Case(
        id=21,
        description="של <date> = EVENT only (video) -> needs_clarification",
        text="שלח לדנה סרטון של 29.6",
        must_pass=True,
        expect={
            "status": ParseStatus.NEEDS_CLARIFICATION,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.VIDEO,
            "scheduled_at_local": None,
            "related_event_date": "2026-06-29",
        },
    ),
    Case(
        id=22,
        description="ב-<date> = SEND (video), no time -> default 10:00",
        text="שלח לדנה סרטון ב-29.6",
        must_pass=True,
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.VIDEO,
            "scheduled_at_local": "2026-06-29T10:00:00",
            "is_explicit_time": False,
            "related_event_date": None,
        },
    ),
    Case(
        id=23,
        description="ל-<event> + ב-<send> + explicit time, teacher lesson coordination",
        text="שלח ליוסי תיאום שיעור ל-20.6 ב-17.6 בשעה 09:00",
        must_pass=True,
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "יוסי",
            "recipient_type": RecipientType.TEACHER,
            "message_type": MessageType.LESSON_COORDINATION,
            "scheduled_at_local": "2026-06-17T09:00:00",
            "is_explicit_time": True,
            "related_event_date": "2026-06-20",
        },
    ),
    Case(
        id=24,
        description="mixed Hebrew/English, inside window -> api_freeform",
        text="שלח לדנה agreement ב-26.6 at 14:00",
        expect={
            "status": ParseStatus.PARSED,
            "recipient_name": "דנה",
            "recipient_type": RecipientType.CLIENT,
            "message_type": MessageType.AGREEMENT,
            "scheduled_at_local": "2026-06-26T14:00:00",
            "is_explicit_time": True,
            "related_event_date": None,
        },
        resolve={
            "contact_name": "דנה",
            "within_window": True,
            "active_templates": [MessageType.AGREEMENT],
            "plan": SendPlan.API_FREEFORM,
        },
    ),
    Case(
        id=25,
        description="no recipient -> needs_clarification (missing recipient)",
        text="שלח תזכורת מחר ב-10:00",
        expect={
            "status": ParseStatus.NEEDS_CLARIFICATION,
            "recipient_name": None,
            "recipient_type": None,
            "message_type": MessageType.CUSTOM,
        },
    ),
]
