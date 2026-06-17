"""Deterministic, rule-based Stage-1 parser. TEST ORACLE ONLY.

================================ READ THIS ====================================
This parser exists ONLY to pin the parsing contract and grade the Hebrew eval
suite without burning LLM calls. It is NOT the production parser and must NEVER
be wired as the live Stage-1. Production Stage-1 is an LLM (Claude). Importing
this from any module under app/ is a bug.
==============================================================================

It implements just enough Hebrew/mixed-language pattern matching to determinist-
ically parse the 25 eval cases, faithfully applying the locked contract rules:

  * Preposition rule:
      ב-<date>   ("on")        -> SEND date  (scheduled_at_local)
      ל-/עד/של <date> ("for/by/of") -> EVENT date (related_event_date)
    An event date alone does NOT satisfy the send-time requirement.
  * A SEND date with no time-of-day defaults to 10:00 (is_explicit_time=False).
    There is NO special "tomorrow -> 09:00" rule.
  * Missing send time -> needs_clarification (never silently inferred).
  * Missing recipient -> needs_clarification.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from app.assistant.nlp.contract import (
    MessageType,
    ParsedIntent,
    ParseStatus,
    RecipientType,
)
from tests.assistant.nlp.clock import NOW

_HEB = "֐-׿"  # Hebrew Unicode block, written as escapes for portability

# ── recipient patterns ────────────────────────────────────────────────────────
_GROUP_RE = re.compile(rf"ל?(קבוצת|צוות)\s+([{_HEB}]+)")
_LAMED_NAME_RE = re.compile(rf"ל([{_HEB}]{{2,}})")
_IM_NAME_RE = re.compile(rf"עם\s+([{_HEB}]{{2,}})")  # "תאם שיעור עם יוסי"

# Hebrew tokens that are NOT recipient names (keywords/time words).
_NOT_A_NAME = {
    "הסכם",
    "מקדמה",
    "פיקדון",
    "סרטון",
    "וידאו",
    "תזכורת",
    "הודעה",
    "שיעור",
    "תיאום",
    "היום",
    "מחר",
    "מחרתיים",
    "בערב",
    "בשעה",
    "את",
    "על",
}

# ── date / time patterns ──────────────────────────────────────────────────────
# prefix + dotted date, e.g. "ב-29.6", "עד 29.6", "של 28.6", "ל-20.6"
_DATE_RE = re.compile(r"(עד|של|ב|ל)\s*-?\s*(\d{1,2})\.(\d{1,2})")
# time-of-day always carries a colon, e.g. "18:00", "at 14:00"
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

# relative day -> day offset from NOW (check מחרתיים before מחר)
_REL_DAYS: List[Tuple[str, int]] = [
    ("מחרתיים", 2),
    ("מחר", 1),
    ("היום", 0),
]


def _detect_recipient(text: str) -> Tuple[Optional[str], Optional[RecipientType]]:
    group = _GROUP_RE.search(text)
    if group:
        name = f"{group.group(1)} {group.group(2)}"
        return name, RecipientType.GROUP

    name: Optional[str] = None
    for m in _LAMED_NAME_RE.finditer(text):
        candidate = m.group(1)
        if candidate not in _NOT_A_NAME:
            name = candidate
            break
    if name is None:
        m = _IM_NAME_RE.search(text)
        if m and m.group(1) not in _NOT_A_NAME:
            name = m.group(1)

    if name is None:
        return None, None

    # teacher cues: lesson coordination context
    if any(cue in text for cue in ("שיעור", "תיאום", "תאם")):
        return name, RecipientType.TEACHER
    return name, RecipientType.CLIENT


def _detect_message_type(text: str) -> MessageType:
    low = text.lower()
    if "הסכם" in text or "agreement" in low:
        return MessageType.AGREEMENT
    if "מקדמה" in text or "פיקדון" in text or "deposit" in low:
        return MessageType.DEPOSIT
    if "סרטון" in text or "וידאו" in text or "video" in low:
        return MessageType.VIDEO
    if "תיאום" in text or "תאם" in text or "שיעור" in text:
        return MessageType.LESSON_COORDINATION
    return MessageType.CUSTOM


def _resolve_year(month: int, day: int) -> int:
    """Pick the year so the date is not in the past relative to NOW."""
    candidate = date(NOW.year, month, day)
    if candidate < NOW.date():
        return NOW.year + 1
    return NOW.year


def _detect_dates(text: str) -> Tuple[List[date], List[date]]:
    """Return (send_dates, event_dates) from prefixed dotted dates."""
    send_dates: List[date] = []
    event_dates: List[date] = []
    for prep, dd, mm in _DATE_RE.findall(text):
        day, month = int(dd), int(mm)
        d = date(_resolve_year(month, day), month, day)
        if prep == "ב":
            send_dates.append(d)
        else:  # ל / עד / של
            event_dates.append(d)
    return send_dates, event_dates


def _detect_relative_day(text: str) -> Optional[date]:
    for word, offset in _REL_DAYS:
        if word in text:
            return NOW.date() + timedelta(days=offset)
    return None


def _detect_time(text: str) -> Optional[Tuple[int, int]]:
    m = _TIME_RE.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse(text: str) -> ParsedIntent:
    """Parse one natural-language command into a ParsedIntent (TEST ORACLE)."""
    recipient_name, recipient_type = _detect_recipient(text)
    message_type = _detect_message_type(text)

    send_dates, event_dates = _detect_dates(text)
    rel_day = _detect_relative_day(text)
    time_part = _detect_time(text)

    send_date: Optional[date] = send_dates[0] if send_dates else rel_day
    event_date: Optional[date] = event_dates[0] if event_dates else None

    scheduled_at_local: Optional[str] = None
    is_explicit_time = False
    inferred_notes: List[str] = []

    if send_date is not None:
        if time_part is not None:
            hh, mm = time_part
            is_explicit_time = True
        else:
            hh, mm = 10, 0  # contract: date with no time -> default 10:00
            inferred_notes.append("send time not given; defaulted to 10:00")
        dt = datetime(send_date.year, send_date.month, send_date.day, hh, mm, 0)
        scheduled_at_local = dt.isoformat()

    related_event_date = event_date.isoformat() if event_date is not None else None

    # ── status ────────────────────────────────────────────────────────────────
    if recipient_name is None:
        return ParsedIntent(
            status=ParseStatus.NEEDS_CLARIFICATION,
            recipient_name=None,
            recipient_type=None,
            message_type=message_type,
            related_event_date=related_event_date,
            clarification="Who should this message go to?",
            inferred_notes=inferred_notes,
        )

    if scheduled_at_local is None:
        if related_event_date is not None:
            note = (
                "Got the event date but no send time — when should I send it?"
            )
        else:
            note = "When should I send this?"
        return ParsedIntent(
            status=ParseStatus.NEEDS_CLARIFICATION,
            recipient_name=recipient_name,
            recipient_type=recipient_type,
            message_type=message_type,
            scheduled_at_local=None,
            related_event_date=related_event_date,
            clarification=note,
            inferred_notes=inferred_notes,
        )

    return ParsedIntent(
        status=ParseStatus.PARSED,
        recipient_name=recipient_name,
        recipient_type=recipient_type,
        message_type=message_type,
        scheduled_at_local=scheduled_at_local,
        is_explicit_time=is_explicit_time,
        related_event_date=related_event_date,
        inferred_notes=inferred_notes,
    )
