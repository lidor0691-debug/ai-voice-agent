"""
Focused tests for the one-time opening greeting instruction
(app/routes/voice_gemini.py::_inject_opening_instruction).

The Gemini path injects the tenant's first_message as an opening instruction.
The old wording said "פתחי את השיחה תמיד ..." ("ALWAYS open ..."), which made
the model re-emit the greeting on later turns. The instruction must now be
one-time and must not contain "תמיד".
"""
from __future__ import annotations

import os
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

import app.routes.voice_gemini as vg

_ONE_TIME_PHRASE = "בתחילת השיחה בלבד, פתחי במשפט הבא בדיוק"


def test_opening_instruction_injected_once_and_no_always():
    base = "BASE PROMPT BODY (no greeting keywords here)"
    fm = "היי, אני מאיה, המזכירה של רועי."
    out = vg._inject_opening_instruction(base, fm)

    # injected exactly once
    assert out.count(_ONE_TIME_PHRASE) == 1
    # the first_message appears exactly once
    assert out.count(fm) == 1
    # original base prompt is preserved
    assert base in out
    # never uses the word "always"
    assert "תמיד" not in out


def test_instruction_precedes_base_prompt():
    out = vg._inject_opening_instruction("ZZZ_BODY", "hello world")
    assert out.index(_ONE_TIME_PHRASE) < out.index("ZZZ_BODY")


def test_no_first_message_returns_base_unchanged():
    base = "BASE"
    assert vg._inject_opening_instruction(base, "") == base
    assert vg._inject_opening_instruction(base, "   ") == base
    assert vg._inject_opening_instruction(base, None) == base
    # and the one-time phrase is NOT added when there is nothing to say
    assert _ONE_TIME_PHRASE not in vg._inject_opening_instruction(base, "")


def test_deployed_source_no_longer_contains_always_wrapper():
    """Guard against the old 'ALWAYS open' wrapper reappearing in the source."""
    import inspect
    src = inspect.getsource(vg._inject_opening_instruction)
    assert "תמיד" not in src
