"""
In-memory conversation state manager.
Each phone call is tracked by Twilio's CallSid.
For production, replace with Redis or a database-backed store.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


# Ordered conversation steps
STEPS: List[str] = ["name", "interest", "budget", "condition", "test_ride"]

# Hebrew questions for each step
QUESTIONS: Dict[str, str] = {
    "name": (
        "שלום! אני מאיה, הסייעת הדיגיטלית שלנו. "
        "אשמח לעזור לך היום. איך קוראים לך?"
    ),
    "interest": "תודה! איזה סוג של אופנוע מעניין אותך?",
    "budget": "מה התקציב שלך לרכישה?",
    "condition": "האם אתה מחפש אופנוע חדש או יד שנייה?",
    "test_ride": "האם תרצה לתאם נסיעת מבחן? ענה כן או לא.",
}

CLOSING_MESSAGE = (
    "תודה רבה! קיבלנו את הפרטים שלך. "
    "נציג שלנו יצור איתך קשר בהקדם האפשרי. "
    "שיהיה לך יום נפלא!"
)

NO_INPUT_MESSAGE = "לא שמעתי אותך. בבקשה נסה שוב."


@dataclass
class Lead:
    call_sid: str
    phone_number: str
    step: int = 0
    name: str = ""
    interest: str = ""
    budget: str = ""
    condition: str = ""
    test_ride: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def current_step_name(self) -> Optional[str]:
        if self.step < len(STEPS):
            return STEPS[self.step]
        return None

    @property
    def is_complete(self) -> bool:
        return self.step >= len(STEPS)

    def advance(self, answer: str) -> None:
        step_name = STEPS[self.step]
        setattr(self, step_name, answer.strip())
        self.step += 1

    def to_dict(self) -> dict:
        return {
            "call_sid": self.call_sid,
            "phone_number": self.phone_number,
            "name": self.name,
            "interest": self.interest,
            "budget": self.budget,
            "condition": self.condition,
            "test_ride": self.test_ride,
            "created_at": self.created_at,
        }


# In-memory session store: { call_sid: Lead }
_sessions: Dict[str, Lead] = {}


def get_or_create_session(call_sid: str, phone_number: str = "") -> Lead:
    if call_sid not in _sessions:
        _sessions[call_sid] = Lead(call_sid=call_sid, phone_number=phone_number)
    return _sessions[call_sid]


def get_session(call_sid: str) -> Optional[Lead]:
    return _sessions.get(call_sid)


def clear_session(call_sid: str) -> None:
    _sessions.pop(call_sid, None)
