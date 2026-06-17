"""Grader for the Hebrew parsing eval suite + Stage-2 resolver unit tests.

Run: pytest tests/assistant/nlp -q

The 25 parametrized cases pin Stage-1 parse output (and Stage-2 resolution for
cases that carry a ``resolve`` spec). Additional resolver unit tests cover the
decision-tree branches not reachable through the 25 cases.
"""
from __future__ import annotations

import pytest

from app.assistant.nlp.contract import (
    Contact,
    MessageType,
    ParseStatus,
    ParsedIntent,
    RecipientType,
    SendPlan,
)
from app.assistant.nlp.resolver import resolve_send_plan
from tests.assistant.nlp import fixtures
from tests.assistant.nlp.cases import CASES, Case
from tests.assistant.nlp.parser import parse

MUST_PASS_IDS = {1, 12, 13, 14, 15, 21, 22, 23}


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"case{c.id}")
def test_case(case: Case) -> None:
    intent = parse(case.text)

    for field_name, expected in case.expect.items():
        actual = getattr(intent, field_name)
        assert actual == expected, (
            f"case {case.id} ({case.description}): "
            f"{field_name} expected {expected!r}, got {actual!r}"
        )

    # Contract invariant: an inferred (non-explicit) send time must be surfaced.
    if intent.scheduled_at_local is not None and not intent.is_explicit_time:
        assert intent.inferred_notes, (
            f"case {case.id}: inferred time must be surfaced in inferred_notes"
        )

    # Stage-2 resolution, when the case specifies it.
    if case.resolve is not None:
        contact = fixtures.lookup(case.resolve["contact_name"])
        plan = resolve_send_plan(
            intent,
            contact,
            within_24h_window=case.resolve["within_window"],
            active_templates=case.resolve["active_templates"],
        )
        assert plan.send_plan == case.resolve["plan"], (
            f"case {case.id}: send_plan expected {case.resolve['plan']}, "
            f"got {plan.send_plan} ({plan.reason})"
        )


def test_must_pass_set_is_intact() -> None:
    """The event-date vs send-date must-pass set is exactly these 8 cases."""
    declared = {c.id for c in CASES if c.must_pass}
    assert declared == MUST_PASS_IDS


def test_exactly_25_cases() -> None:
    ids = sorted(c.id for c in CASES)
    assert ids == list(range(1, 26))


# ── Stage-2 resolver decision-tree unit tests ─────────────────────────────────

def _intent(message_type: MessageType, recipient_type: RecipientType) -> ParsedIntent:
    return ParsedIntent(
        status=ParseStatus.PARSED,
        recipient_name="x",
        recipient_type=recipient_type,
        message_type=message_type,
        scheduled_at_local="2026-06-16T10:00:00",
        is_explicit_time=True,
    )


def test_resolve_group_is_manual() -> None:
    contact = Contact("קבוצת בוקר", RecipientType.GROUP, phone=None)
    plan = resolve_send_plan(_intent(MessageType.CUSTOM, RecipientType.GROUP), contact)
    assert plan.send_plan == SendPlan.GROUP_MANUAL


def test_resolve_group_from_intent_when_no_contact() -> None:
    plan = resolve_send_plan(_intent(MessageType.CUSTOM, RecipientType.GROUP), None)
    assert plan.send_plan == SendPlan.GROUP_MANUAL


def test_resolve_no_phone_is_manual_fallback() -> None:
    contact = fixtures.lookup("נועה")  # client with phone=None
    plan = resolve_send_plan(
        _intent(MessageType.AGREEMENT, RecipientType.CLIENT),
        contact,
        within_24h_window=False,
        active_templates=[MessageType.AGREEMENT],
    )
    assert plan.send_plan == SendPlan.MANUAL_FALLBACK


def test_resolve_no_contact_is_manual_fallback() -> None:
    plan = resolve_send_plan(_intent(MessageType.CUSTOM, RecipientType.CLIENT), None)
    assert plan.send_plan == SendPlan.MANUAL_FALLBACK


def test_resolve_inside_window_is_freeform() -> None:
    contact = fixtures.lookup("דנה")
    plan = resolve_send_plan(
        _intent(MessageType.CUSTOM, RecipientType.CLIENT),
        contact,
        within_24h_window=True,
        active_templates=[],
    )
    assert plan.send_plan == SendPlan.API_FREEFORM


def test_resolve_outside_window_with_template_is_api_template() -> None:
    contact = fixtures.lookup("אבי")
    plan = resolve_send_plan(
        _intent(MessageType.DEPOSIT, RecipientType.CLIENT),
        contact,
        within_24h_window=False,
        active_templates=[MessageType.DEPOSIT],
    )
    assert plan.send_plan == SendPlan.API_TEMPLATE


def test_resolve_outside_window_without_template_is_manual_fallback() -> None:
    contact = fixtures.lookup("אבי")
    plan = resolve_send_plan(
        _intent(MessageType.CUSTOM, RecipientType.CLIENT),
        contact,
        within_24h_window=False,
        active_templates=[],
    )
    assert plan.send_plan == SendPlan.MANUAL_FALLBACK
