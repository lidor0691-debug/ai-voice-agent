"""
M6.1 tests — tenant-dynamic Stage-2 identity for the two-stage phone greeting.

The Stage-2 self-introduction must name the CURRENT tenant's office, resolved
from configuration — never a hardcoded one. Requirements proven here:

  • Roi (given his configured office phrase) stays BYTE-IDENTICAL to M6.
  • A different tenant (the demo) says its OWN office, never Roi's.
  • Missing/unknown identity falls back to a safe, name-free generic phrase.
  • No tenant name is hardcoded in the generic Stage-2 templates.
  • greeting-only (fixed), substantive, and fallback Stage 2 ALL use the
    controller's tenant office — no path leaks another tenant's name.

The assistant's own product name ("מאיה"/Maya) is identical for every tenant
and is not a per-tenant identity, so it legitimately stays in the template;
only the OFFICE owner ("מהמשרד של רועי") is made tenant-dynamic.
"""
from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pathlib

import pytest

import app.routes.voice_openai_live as vol
import app.services.voice_shared as vs
from app.routes.voice_openai_live import TurnController, CallState, Action

# ── fixtures ──────────────────────────────────────────────────────────────────
ROI_CID = "c3a8c2a0-8841-4c9b-9a59-3f9795c4e7de"
DEMO_CID = "ec87b6ae-b28c-4bef-8562-fd4f530d41d5"
ROI_OFFICE = "מהמשרד של רועי"
DEMO_OFFICE = "מהמשרד של אלירן"        # Eliran Zussman (demo tenant)

# The exact Stage-2 lines each tenant must hear (byte-for-byte).
ROI_CALLER_LINE = "כן, מדברת מאיה מהמשרד של רועי. איך אפשר לעזור?"
ROI_FALLBACK_LINE = "היי, מדברת מאיה מהמשרד של רועי. איך אפשר לעזור?"
DEMO_CALLER_LINE = "כן, מדברת מאיה מהמשרד של אלירן. איך אפשר לעזור?"
DEMO_FALLBACK_LINE = "היי, מדברת מאיה מהמשרד של אלירן. איך אפשר לעזור?"
SUBSTANTIVE_TEXT = "שלום, אני צריך שיחזרו אליי לגבי דוח כספי."


def _val(pairs, action):
    for a, v in pairs:
        if a == action:
            return v
    return None


def _mark_name(pairs):
    return _val(pairs, Action.SEND_MARK)


def _to_waiting(c):
    """Drive a two-stage controller to WAITING_FOR_CALLER after "הלו?"."""
    c.on_session_updated()
    c.on_response_created()
    c.on_output_delta()
    done = c.on_response_done("completed")
    c.on_twilio_mark(_mark_name(done))
    assert c.state == CallState.WAITING_FOR_CALLER


def _turn(c, text, dur=2.0, item_id="i1"):
    c.on_speech_started(0.0)
    c.on_speech_stopped(dur, item_id=item_id)
    return c.on_input_transcription(text, dur=dur, item_id=item_id)


# ── resolver (pure): identity comes ONLY from agents_config, never env ────────
class TestResolveOffice:
    def test_voice_office_label_wins_over_business_name(self):
        cfg = {"voice_office_label": ROI_OFFICE, "business_name": "אחר"}
        assert vs.resolve_two_stage_office(cfg) == ROI_OFFICE

    def test_roi_resolves_to_roi_office(self):
        assert vs.resolve_two_stage_office({"voice_office_label": ROI_OFFICE}) == "מהמשרד של רועי"

    def test_eliran_resolves_to_eliran_office(self):
        assert vs.resolve_two_stage_office({"voice_office_label": DEMO_OFFICE}) == "מהמשרד של אלירן"

    def test_business_name_fallback_when_no_label(self):
        got = vs.resolve_two_stage_office({"business_name": "המרכז לביטוח ופנסיה"})
        assert got == "מהמשרד של המרכז לביטוח ופנסיה"

    def test_generic_fallback_when_nothing_configured(self):
        assert vs.resolve_two_stage_office({}) == vs.GENERIC_OFFICE_LABEL
        assert vs.resolve_two_stage_office(None) == vs.GENERIC_OFFICE_LABEL
        assert vs.resolve_two_stage_office({"voice_office_label": None, "business_name": None}) == vs.GENERIC_OFFICE_LABEL
        assert vs.resolve_two_stage_office({"voice_office_label": "  ", "business_name": " "}) == vs.GENERIC_OFFICE_LABEL
        assert vs.GENERIC_OFFICE_LABEL == "מהמשרד"

    def test_no_env_office_map_exists(self):
        # Identity must not be maintained in Railway/env any more.
        assert not hasattr(vs, "OPENAI_TWO_STAGE_OFFICE_LABELS")
        assert not hasattr(vs, "_parse_office_labels")


# ── controller builds Stage-2 lines from ITS office ───────────────────────────
class TestRoiByteIdentical:
    def test_caller_line(self):
        c = TurnController(two_stage=True, office=ROI_OFFICE)
        _to_waiting(c)
        acts = _turn(c, "כן")            # bare ack → fixed question
        assert ROI_CALLER_LINE in _val(acts, Action.SPEAK_SCRIPTED)

    def test_fallback_line(self):
        c = TurnController(two_stage=True, office=ROI_OFFICE)
        c.on_session_updated()           # → Stage 1
        acts = c.on_greeting_fallback()
        assert ROI_FALLBACK_LINE in _val(acts, Action.SPEAK_SCRIPTED)

    def test_substantive_instruction(self):
        c = TurnController(two_stage=True, office=ROI_OFFICE)
        _to_waiting(c)
        acts = _turn(c, SUBSTANTIVE_TEXT)
        instr = _val(acts, Action.SPEAK_SCRIPTED)
        assert "כמאיה מהמשרד של רועי" in instr
        assert "לחזור על סיבת הפנייה" in instr   # never re-ask the reason


class TestDemoUsesItsOwnOffice:
    def test_caller_line(self):
        c = TurnController(two_stage=True, office=DEMO_OFFICE)
        _to_waiting(c)
        v = _val(_turn(c, "כן"), Action.SPEAK_SCRIPTED)
        assert DEMO_CALLER_LINE in v and "רועי" not in v

    def test_fallback_line(self):
        c = TurnController(two_stage=True, office=DEMO_OFFICE)
        c.on_session_updated()
        v = _val(c.on_greeting_fallback(), Action.SPEAK_SCRIPTED)
        assert DEMO_FALLBACK_LINE in v and "רועי" not in v

    def test_substantive_instruction(self):
        c = TurnController(two_stage=True, office=DEMO_OFFICE)
        _to_waiting(c)
        v = _val(_turn(c, SUBSTANTIVE_TEXT), Action.SPEAK_SCRIPTED)
        assert "כמאיה מהמשרד של אלירן" in v and "רועי" not in v
        assert "לחזור על סיבת הפנייה" in v


class TestGenericFallbackIdentity:
    def test_missing_office_uses_generic_phrase(self):
        c = TurnController(two_stage=True)   # no office → generic
        _to_waiting(c)
        v = _val(_turn(c, "כן"), Action.SPEAK_SCRIPTED)
        assert "כן, מדברת מאיה מהמשרד. איך אפשר לעזור?" in v
        assert "רועי" not in v


class TestNoCrossTenantLeak:
    def test_no_path_leaks_other_tenant(self):
        roi = TurnController(two_stage=True, office=ROI_OFFICE)
        demo = TurnController(two_stage=True, office=DEMO_OFFICE)
        roi_lines = " ".join([
            roi._stage2_caller_instruction(),
            roi._stage2_fallback_instruction(),
            roi._stage2_substantive_instruction(),
        ])
        demo_lines = " ".join([
            demo._stage2_caller_instruction(),
            demo._stage2_fallback_instruction(),
            demo._stage2_substantive_instruction(),
        ])
        assert DEMO_OFFICE not in roi_lines
        assert "רועי" not in demo_lines


class TestNoHardcodedNameInGenericTemplates:
    def test_templates_are_name_free_and_slotted(self):
        for tmpl in (
            vol._GREETING_STAGE2_CALLER_TEMPLATE,
            vol._GREETING_STAGE2_FALLBACK_TEMPLATE,
            vol._STAGE2_SUBSTANTIVE_TEMPLATE,
        ):
            assert "{office}" in tmpl
            assert "רועי" not in tmpl

    def test_source_has_no_hardcoded_roi_office_phrase(self):
        src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
        # The office owner's spoken phrase must not be hardcoded anywhere in the
        # generic module (it now comes from config). The bare token "רועי" may
        # still appear ONLY as a caller-input trigger word, never as Maya's line.
        assert "מהמשרד של רועי" not in src
