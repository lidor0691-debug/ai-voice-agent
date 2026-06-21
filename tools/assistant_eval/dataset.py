"""Canonical eval dataset loader. DEV-ONLY.

Per the PR5 decision (2a), the 25 Hebrew cases are read DIRECTLY from the
existing test oracle (``tests/assistant/nlp``) — they are NOT copied, lifted,
or refactored here. This module only re-exposes them and supplies a correctly
anchored ``now`` for the live parser.

Importable because ``tests`` is a real package (``tests/__init__.py`` exists)
on the repo root path.
"""
from __future__ import annotations

from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

# Direct import of the canonical oracle — single source of truth.
from tests.assistant.nlp.cases import CASES, Case
from tests.assistant.nlp.clock import NOW, TZ_NAME

__all__ = ["CASES", "Case", "NOW", "TZ_NAME", "anchored_now", "select_cases"]


def anchored_now() -> datetime:
    """The frozen clock as a timezone-aware Asia/Jerusalem datetime.

    The cases' ``NOW`` is a NAIVE wall-clock value (2026-06-15 12:00 local).
    ``ClaudeParser`` treats a naive ``now`` as UTC, which would shift the
    anchor by the IDT offset. Attaching the Jerusalem zone here makes the
    parser anchor relative dates ("מחר", "מחרתיים") against the same instant
    the expectations were written for.
    """
    return NOW.replace(tzinfo=ZoneInfo(TZ_NAME))


def select_cases(only: List[int] | None = None) -> List[Case]:
    """All cases, or just the given ids (preserving canonical order)."""
    if not only:
        return list(CASES)
    wanted = set(only)
    return [c for c in CASES if c.id in wanted]
