"""Pure expected-vs-actual ParsedIntent comparison. DEV-ONLY, network-free.

This is the unit the tests drive directly. It compares ONLY the fields a case
pins in its ``expect`` dict — so a case that omits ``scheduled_at_local`` (e.g.
the missing-recipient case) does not get penalised for it.

Free-text fields are never pass/fail keys: ``clarification`` wording and
``inferred_notes`` vary between LLM runs and carry no contract meaning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from app.assistant.nlp.contract import ParsedIntent

# Never compared, even if a case were to list them: free text / diagnostics.
INFORMATIONAL_FIELDS = frozenset({"clarification", "inferred_notes", "body"})


@dataclass
class FieldDiff:
    field: str
    expected: Any
    actual: Any


@dataclass
class CaseResult:
    case_id: int
    description: str
    must_pass: bool
    passed: bool
    diffs: List[FieldDiff] = field(default_factory=list)

    @property
    def first_diff(self) -> "FieldDiff | None":
        return self.diffs[0] if self.diffs else None


def compare_case(case: Any, actual: ParsedIntent) -> CaseResult:
    """Diff a case's pinned expectations against an actual ParsedIntent.

    ``status`` is enforced first (it gates which other fields are meaningful),
    then every other pinned field is checked exactly. ``RecipientType`` /
    ``MessageType`` / ``ParseStatus`` are ``str`` enums, so member equality
    holds against the values the contract produces.
    """
    diffs: List[FieldDiff] = []
    for key, expected in case.expect.items():
        if key in INFORMATIONAL_FIELDS:
            continue
        actual_value = getattr(actual, key)
        if actual_value != expected:
            diffs.append(FieldDiff(field=key, expected=expected, actual=actual_value))
    # Keep status first in the diff list when it diverges, for readable reports.
    diffs.sort(key=lambda d: 0 if d.field == "status" else 1)
    return CaseResult(
        case_id=case.id,
        description=case.description,
        must_pass=case.must_pass,
        passed=not diffs,
        diffs=diffs,
    )
