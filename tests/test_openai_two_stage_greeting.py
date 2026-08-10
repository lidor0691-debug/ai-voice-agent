"""
M6 tests — two-stage phone greeting (Roi-only, client-allowlisted).

Goal: Maya sounds like a person answering the phone, so callers are less likely
to assume voicemail and hang up.

  Stage 1  → a short scripted "הלו?", then wait.
  Stage 2  → self-identification, chosen by what the caller actually said:
             • bare greeting / ack / identity check → the FIXED question
             • substantive content                → a normal reply that
               self-introduces and continues from the request (never re-asks)
  Fallback → ~0.6s of post-"הלו?" silence → Stage 2 fires automatically, once.

`stage2_done` is the single race guard; with the client NOT allowlisted
(two_stage=False) the controller is byte-identical to the M2–M5 flow.
"""
from __future__ import annotations

import os
import pathlib

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pytest

import app.routes.voice_openai_live as vol
import app.services.voice_shared as vs
from app.routes.voice_openai_live import TurnController, CallState, Action


# ── helpers (mirror the M4 harness) ───────────────────────────────────────────

def _acts(pairs):
    return [a for a, _ in pairs]


def _val(pairs, action):
    for a, v in pairs:
        if a == action:
            return v
    return None


def _mark_name(pairs):
    return _val(pairs, Action.SEND_MARK)


# M6 was Roi-only; these tests assert Roi's exact spoken lines. The Stage-2
# lines are now name-free templates filled per-tenant (M6.1), so the controller
# is built with Roi's configured office and the expected lines are rendered the
# same way — behavior is byte-identical to the original M6.
ROI_OFFICE = "מהמשרד של רועי"
CALLER_LINE = vol._GREETING_STAGE2_CALLER_TEMPLATE.format(office=ROI_OFFICE)
FALLBACK_LINE = vol._GREETING_STAGE2_FALLBACK_TEMPLATE.format(office=ROI_OFFICE)
SUBSTANTIVE_INSTR = vol._STAGE2_SUBSTANTIVE_TEMPLATE.format(office=ROI_OFFICE)


def _two_stage_ctrl():
    return TurnController(two_stage=True, office=ROI_OFFICE)


def _to_greeting_playing(c):
    """session.updated → Stage 1 create → first delta → GREETING_PLAYING."""
    first = c.on_session_updated()
    c.on_response_created()
    c.on_output_delta()
    assert c.state == CallState.GREETING_PLAYING
    return first


def _to_waiting(c):
    """Stage 1 finishes playing and its mark returns → WAITING_FOR_CALLER."""
    _to_greeting_playing(c)
    done = c.on_response_done("completed")
    c.on_twilio_mark(_mark_name(done))
    assert c.state == CallState.WAITING_FOR_CALLER


def _segment(c, dur, item_id=None):
    c.on_speech_started(0.0)
    c.on_speech_stopped(dur, item_id=item_id)


def _turn(c, text, dur, item_id=None):
    _segment(c, dur, item_id=item_id)
    return c.on_input_transcription(text, dur=dur, item_id=item_id)


# ── config parser (fallback seconds) ─────────────────────────────────────────

class TestFallbackParser:
    def test_default_is_0_6(self):
        # tuned down from 1.7 (Roi prod data): ~2.3s dead air after "הלו?"
        assert vol.OPENAI_GREETING_STAGE2_FALLBACK_DEFAULT == 0.6

    def test_unset_and_blank_fall_back(self):
        assert vol._parse_stage2_fallback_seconds(None) == 0.6
        assert vol._parse_stage2_fallback_seconds("") == 0.6
        assert vol._parse_stage2_fallback_seconds("   ") == 0.6

    def test_valid_in_range(self):
        assert vol._parse_stage2_fallback_seconds("0.6") == 0.6   # the tuned value
        assert vol._parse_stage2_fallback_seconds("0.4") == 0.4   # floor boundary
        assert vol._parse_stage2_fallback_seconds("1.5") == 1.5
        assert vol._parse_stage2_fallback_seconds("2.0") == 2.0

    def test_unparsable_falls_back(self):
        assert vol._parse_stage2_fallback_seconds("fast") == 0.6

    def test_out_of_range_falls_back(self):
        assert vol._parse_stage2_fallback_seconds("0.3") == 0.6   # below 0.4 floor
        assert vol._parse_stage2_fallback_seconds("0.2") == 0.6   # typo guard
        assert vol._parse_stage2_fallback_seconds("17") == 0.6    # typo guard
        assert vol._parse_stage2_fallback_seconds("nan") == 0.6
        assert vol._parse_stage2_fallback_seconds("inf") == 0.6


# ── setup-head instrumentation (monotonic marks across the opening) ───────────

class TestSetupHeadInstrumentation:
    def _src(self):
        import pathlib
        return pathlib.Path(vol.__file__).read_text(encoding="utf-8")

    def test_monotonic_marks_captured(self):
        src = self._src()
        for mark in ["_t_entry = time.monotonic()", "_t_media_start = time.monotonic()",
                     "_t_ctx       = time.monotonic()", "_t_oai = time.monotonic()"]:
            assert mark in src, f"missing setup mark: {mark!r}"

    def test_setup_diag_events_emitted(self):
        src = self._src()
        for ev in ['_diag("setup_media_start"', '_diag("setup_context_fetched"',
                   '_diag("setup_openai_connected"']:
            assert ev in src, f"missing setup diag: {ev!r}"
        # session.created and first audio carry a since-entry offset for the tail
        assert "since_entry_ms=round((time.monotonic() - _t_entry) * 1000)" in src
        assert "since_media_start_ms=round((_now - _t_media_start) * 1000)" in src

    def test_instrumentation_is_diag_only(self):
        # pure logging: the setup diags must not gate on / mutate call state
        src = self._src()
        # each setup diag call is a bare _diag(...) statement, not in a condition
        for ev in ["setup_media_start", "setup_context_fetched", "setup_openai_connected"]:
            assert f'if _diag("{ev}"' not in src


# ── caller-content classifier ────────────────────────────────────────────────

class TestGreetingOnlyClassifier:
    @pytest.mark.parametrize("text", [
        "הלו", "הלו?", "כן", "כן?", "שלום", "היי",
        "רועי?", "רועי", "מי זה?", "מי זה", "מי מדבר?", "אוקיי", "תודה",
    ])
    def test_bare_greeting_or_identity_check_is_greeting_only(self, text):
        assert vol._is_greeting_only_turn(text) is True

    @pytest.mark.parametrize("text", [
        "שלום, אני צריך שרועי יחזור אליי לגבי דוחות כספיים.",
        "אני רוצה לבדוק ביטוח רכב",
        "כן, יש לי שאלה על הפוליסה",
        "רועי, אני צריך אישור",
    ])
    def test_substantive_content_is_not_greeting_only(self, text):
        assert vol._is_greeting_only_turn(text) is False

    def test_stage1_line_is_holo(self):
        assert vol._GREETING_STAGE1_LINE == "הלו?"

    def test_stage2_lines_identify_maya_and_office(self):
        assert CALLER_LINE == "כן, מדברת מאיה מהמשרד של רועי. איך אפשר לעזור?"
        assert FALLBACK_LINE == "היי, מדברת מאיה מהמשרד של רועי. איך אפשר לעזור?"


# ── client allowlist (not a global boolean) ──────────────────────────────────

class TestAllowlist:
    def test_empty_allowlist_off_for_everyone(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_TWO_STAGE_GREETING_CLIENT_IDS", set())
        assert vs.two_stage_greeting_enabled("roi-client-id") is False
        assert vs.two_stage_greeting_enabled("") is False

    def test_only_allowlisted_client_enabled(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_TWO_STAGE_GREETING_CLIENT_IDS", {"roi-client-id"})
        assert vs.two_stage_greeting_enabled("roi-client-id") is True
        assert vs.two_stage_greeting_enabled("other-client") is False
        assert vs.two_stage_greeting_enabled("") is False
        assert vs.two_stage_greeting_enabled(None) is False


# ── regression: two_stage OFF is byte-identical to M2–M5 ─────────────────────

class TestFlagOffUnchanged:
    def test_default_controller_is_single_greeting(self):
        c = TurnController()
        assert c.two_stage is False
        assert c.greeting_stage == 0
        acts = c.on_session_updated()
        assert _acts(acts) == [Action.RESPONSE_CREATE]      # plain create, no script
        assert c.greeting_stage == 0

    def test_fallback_is_noop_when_flag_off(self):
        c = TurnController()
        _to_waiting(c)
        assert c.on_greeting_fallback() == []               # never speaks


# ── requirement 1: Stage 1 says only "הלו?" ──────────────────────────────────

class TestStage1:
    def test_call_start_speaks_only_holo(self):
        c = _two_stage_ctrl()
        acts = c.on_session_updated()
        assert _acts(acts) == [Action.SPEAK_SCRIPTED]
        instr = _val(acts, Action.SPEAK_SCRIPTED)
        assert "הלו?" in instr
        # Stage 1 must NOT leak the identification line.
        assert "מאיה" not in instr and "רועי" not in instr and "איך אפשר לעזור" not in instr
        assert c.greeting_stage == 1
        assert c.stage2_done is False

    def test_no_duplicate_stage1(self):                     # requirement 7
        c = _two_stage_ctrl()
        c.on_session_updated()
        assert c.on_session_updated() == []                 # greeting_done guard


# ── requirement 2: greeting-only / identity check → FIXED Stage 2 question ────

class TestStage2Fixed:
    @pytest.mark.parametrize("text", ["כן", "שלום", "רועי", "מי זה"])
    def test_bare_turn_gets_fixed_question(self, text):
        c = _two_stage_ctrl()
        _to_waiting(c)
        acts = _turn(c, text, 0.5)
        assert _acts(acts) == [Action.SPEAK_SCRIPTED]
        assert CALLER_LINE in _val(acts, Action.SPEAK_SCRIPTED)
        assert c.last_stage2_kind == "fixed"
        assert c.stage2_done is True
        assert c.last_decision == "accepted"               # turn is NOT discarded

    def test_stage2_fires_only_once_more_turns_normal(self):  # requirement 8
        c = _two_stage_ctrl()
        _to_waiting(c)
        _turn(c, "כן", 0.5)                                 # Stage 2 (fixed)
        # drive Stage 2 through playback back to a waiting state
        c.on_response_created(); c.on_output_delta()
        done = c.on_response_done("completed"); c.on_twilio_mark(_mark_name(done))
        acts = _turn(c, "אני רוצה לבדוק ביטוח רכב", 1.0)     # a real later turn
        assert _acts(acts) == [Action.RESPONSE_CREATE]      # normal model flow, no 2nd Stage 2


# ── requirement 3 + 4: substantive request → identify + continue, preserved ──

class TestStage2Substantive:
    def test_substantive_request_identifies_and_continues(self):
        c = _two_stage_ctrl()
        _to_waiting(c)
        acts = _turn(c, "שלום, אני צריך שרועי יחזור אליי לגבי דוחות כספיים.", 2.0)
        assert Action.SPEAK_SCRIPTED in _acts(acts)
        instr = _val(acts, Action.SPEAK_SCRIPTED)
        assert instr == SUBSTANTIVE_INSTR
        # must self-introduce, must NOT re-ask the reason
        assert "מאיה" in instr and "רועי" in instr
        assert "אל תבקשי מהפונה לחזור" in instr
        assert "איך אפשר לעזור" in instr and "אל תשאלי" in instr  # explicitly forbidden
        assert c.last_stage2_kind == "substantive"

    def test_substantive_turn_preserved_for_transcript_and_summary(self):
        c = _two_stage_ctrl()
        _to_waiting(c)
        text = "אני צריך שרועי יחזור אליי לגבי דוחות כספיים"
        _turn(c, text, 2.0)
        # the accepted turn is retained on the controller and (in the wiring) is
        # appended to _caller_lines / _transcript_turns → summary sees it.
        assert c.last_decision == "accepted"
        assert c.last_turn_text == text
        assert c.valid_turns == 1


# ── mixed opening turns: greeting/identity PREFIX must not swallow content ────
# A turn that STARTS with a greeting/ack/identity word but continues into a real
# request must be treated as substantive — the classifier only matches when the
# ENTIRE normalized turn is a bare trigger (trailing punctuation stripped from
# the ends only, never mid-string).

_MIXED_SUBSTANTIVE = [
    "כן, אני צריך שרועי יחזור אליי",
    "שלום, רציתי לשאול לגבי הביטוח שלי",
    "מי זה? אני מחפש את רועי",
    "כן... רציתי לבדוק משהו בפוליסה",
]


class TestMixedOpeningTurns:
    @pytest.mark.parametrize("text", _MIXED_SUBSTANTIVE)
    def test_classifier_does_not_treat_mixed_as_greeting_only(self, text):
        assert vol._is_greeting_only_turn(text) is False

    @pytest.mark.parametrize("text", _MIXED_SUBSTANTIVE)
    def test_mixed_turn_drives_substantive_stage2_and_is_preserved(self, text):
        c = _two_stage_ctrl()
        _to_waiting(c)
        acts = _turn(c, text, 1.5)
        # substantive self-intro instruction — NOT the fixed "איך אפשר לעזור?" line
        assert Action.SPEAK_SCRIPTED in _acts(acts)
        assert _val(acts, Action.SPEAK_SCRIPTED) == SUBSTANTIVE_INSTR
        assert CALLER_LINE not in _val(acts, Action.SPEAK_SCRIPTED)
        assert c.last_stage2_kind == "substantive"
        # full caller content preserved (transcript + summary see the whole turn)
        assert c.last_decision == "accepted"
        assert c.last_turn_text == text


# ── requirement 3 (fallback): no caller → fallback Stage 2 once ───────────────

class TestStage2Fallback:
    def test_silence_fires_fallback_line_once(self):
        c = _two_stage_ctrl()
        _to_waiting(c)
        acts = c.on_greeting_fallback()
        assert _acts(acts) == [Action.SPEAK_SCRIPTED]
        assert FALLBACK_LINE in _val(acts, Action.SPEAK_SCRIPTED)
        assert c.last_stage2_kind == "fallback"
        assert c.stage2_done is True
        assert c.on_greeting_fallback() == []              # requirement 8: once only

    def test_caller_then_fallback_no_double_speak(self):   # requirement 8
        c = _two_stage_ctrl()
        _to_waiting(c)
        _turn(c, "כן", 0.5)                                 # caller drove Stage 2
        assert c.on_greeting_fallback() == []              # fallback suppressed

    def test_fallback_then_late_caller_is_normal(self):
        c = _two_stage_ctrl()
        _to_waiting(c)
        c.on_greeting_fallback()                            # fallback drove Stage 2
        c.on_response_created(); c.on_output_delta()
        done = c.on_response_done("completed"); c.on_twilio_mark(_mark_name(done))
        acts = _turn(c, "אני רוצה לבדוק ביטוח", 1.0)
        assert _acts(acts) == [Action.RESPONSE_CREATE]     # normal flow, not a 2nd Stage 2


# ── requirement 4/5/6: noise, held fragments, valid interruption ─────────────

class TestGreetingProtectionInteraction:
    def test_junk_during_greeting_does_not_trigger_stage2(self):   # requirement 4
        c = _two_stage_ctrl()
        _to_greeting_playing(c)
        acts = _turn(c, "زبد", 0.4)                          # non-Hebrew junk
        assert acts == []
        assert c.last_decision == "rejected_gate"
        assert c.stage2_done is False and c.greeting_stage == 1
        # fallback still available afterwards
        assert FALLBACK_LINE in _val(c.on_greeting_fallback(), Action.SPEAK_SCRIPTED)

    def test_held_greeting_fragment_does_not_cancel_fallback(self):  # requirement 5
        c = _two_stage_ctrl()
        _to_greeting_playing(c)
        acts = _turn(c, "כן", 0.5)                          # weak → HELD during greeting
        assert acts == []
        assert c.last_decision == "held_greeting"
        assert c.stage2_done is False and c.greeting_stage == 1
        # the fallback can still fire (its timer was never cancelled)
        assert c.on_greeting_fallback() != []

    def test_valid_interruption_during_holo_drives_stage2(self):    # requirement 6
        c = _two_stage_ctrl()
        _to_greeting_playing(c)
        # strong barge-in (≥10 chars, ≥1.2s) cuts "הלו?" and drives Stage 2
        acts = _turn(c, "אני צריך לדבר עם רועי בדחיפות בבקשה", 1.5)
        kinds = _acts(acts)
        assert Action.CANCEL_AND_CLEAR in kinds            # barge-in handled naturally
        assert Action.SPEAK_SCRIPTED in kinds
        assert c.stage2_done is True                       # → wiring cancels the fallback timer
        assert c.last_stage2_kind == "substantive"
        assert c.last_decision == "accepted"


# ── requirement 11: Roi-only routing / wiring is source-correct ──────────────

class TestWiringSource:
    def _src(self):
        return pathlib.Path(vol.__file__).read_text(encoding="utf-8")

    def test_controller_gated_by_client_allowlist(self):
        src = self._src()
        assert "_two_stage = _two_stage_greeting_enabled(client_id or \"\")" in src
        assert "TurnController(two_stage=_two_stage, office=_office," in src

    def test_fallback_task_armed_and_cancelled(self):
        src = self._src()
        assert "_greeting_fallback_runner" in src
        assert "on_greeting_fallback()" in src
        assert "_cancel_greeting_fallback()" in src
        # armed only after Stage 1's playback mark, in a real waiting state
        assert 'CallState.WAITING_FOR_CALLER' in src

    def test_scripted_response_still_app_owned(self):
        src = self._src()
        # every response.create still funnels through _send_response_create
        assert "elif act == Action.SPEAK_SCRIPTED:" in src
        assert src.count("await openai_ws.send(json.dumps({\"type\": \"response.create\"") == 0 \
            or "_send_response_create" in src
