"""
M4 tests — greeting-protection gate, segment/turn-ID binding, cancellation
safety, response.create auditability, and the fresh-per-call state invariant.

Anchored on the real M3-acceptance incident (calls 3–4): line noise during
GREETING_PLAYING was transcribed as plausible short Hebrew ("תודה" @1.10s,
"רק נשמע" @2.16s), passed the generic turn gate, truncated the greeting and
seeded a content-free caller turn — so the model answered "איזה ביטוח?" from
the business prompt. Those exact replays must now be HELD.
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
from app.routes.voice_openai_live import (
    TurnController, CallState, Action,
    is_verified_greeting_interruption,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _acts(pairs):
    return [a for a, _ in pairs]


def _val(pairs, action):
    for a, v in pairs:
        if a == action:
            return v
    return None


def _mark_name(pairs):
    return _val(pairs, Action.SEND_MARK)


def _to_greeting_playing(c):
    c.on_session_updated()
    c.on_response_created()
    c.on_output_delta()
    assert c.state == CallState.GREETING_PLAYING


def _to_waiting(c):
    _to_greeting_playing(c)
    done = c.on_response_done("completed")
    c.on_twilio_mark(_mark_name(done))
    assert c.state == CallState.WAITING_FOR_CALLER


def _segment(c, dur, item_id=None):
    """A completed speech pair of `dur` seconds → mints one segment."""
    c.on_speech_started(0.0)
    c.on_speech_stopped(dur, item_id=item_id)


def _turn(c, text, dur, item_id=None):
    _segment(c, dur, item_id=item_id)
    return c.on_input_transcription(text, dur=dur, item_id=item_id)


# ── 1. fresh-per-call state invariant ────────────────────────────────────────

def test_1_fresh_controller_has_zeroed_state():
    c = TurnController()
    assert c._segment_seq == 0
    assert c._turn_seq == 0
    assert c._resp_seq == 0
    assert c._timeout_gen == 0
    assert c._unconsumed_segment is None
    assert c._pending_item_id is None
    assert c._generation_active is False
    assert c.valid_turns == 0
    assert c.pending_marks == set()
    assert c.last_decision is None
    assert c.last_turn_id is None
    assert c.state == CallState.INITIALIZING


def test_1b_ids_and_transcripts_cannot_be_inherited():
    """A second call's controller shares nothing with the first."""
    c1 = TurnController()
    _to_waiting(c1)
    _turn(c1, "אני צריך לברר לגבי הפנסיה שלי", 2.0)
    assert c1._turn_seq == 1 and c1._segment_seq == 1
    c2 = TurnController()
    assert (c2._turn_seq, c2._segment_seq, c2.valid_turns) == (0, 0, 0)
    assert c2.last_turn_text == "" and c2.last_turn_id is None


def test_1c_single_controller_construction_site_per_call():
    src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
    assert src.count("TurnController()") == 1          # constructed once, in-handler
    assert "_ctrl = TurnController()" in src
    # per-call buffers are handler-locals, not module globals
    assert "\n_caller_lines" not in src and "\n_assistant_lines" not in src


# ── 2/3. REGRESSION — the exact incident fragments are held ──────────────────

@pytest.mark.parametrize("text,dur", [("תודה", 1.10), ("רק נשמע", 2.16)])
def test_2_3_incident_fragments_held_during_greeting(text, dur):
    c = TurnController()
    _to_greeting_playing(c)
    acts = _turn(c, text, dur)
    # no cancel, no clear, no response
    assert acts == []
    assert c.last_decision == "held_greeting"
    # greeting untouched and still playing
    assert c.state == CallState.GREETING_PLAYING
    assert c.valid_turns == 0
    assert c._turn_seq == 0
    # greeting then finishes normally and the REAL mark drives the transition
    done = c.on_response_done("completed")
    assert Action.SEND_MARK in _acts(done)
    c.on_twilio_mark(_mark_name(done))
    assert c.state == CallState.WAITING_FOR_CALLER


def test_2b_held_fragment_never_triggers_a_later_response():
    """A held fragment must not resurface — only a NEW valid turn responds."""
    c = TurnController()
    _to_greeting_playing(c)
    assert _turn(c, "תודה", 1.10) == []
    done = c.on_response_done("completed")
    c.on_twilio_mark(_mark_name(done))
    assert c.state == CallState.WAITING_FOR_CALLER
    # silence: nothing pending can create a response
    assert c._unconsumed_segment is None
    # a genuine later turn still works normally
    acts = _turn(c, "אני רוצה לברר לגבי הפנסיה שלי", 2.0)
    assert Action.RESPONSE_CREATE in _acts(acts)
    assert c.last_decision == "accepted"


# ── 4. stoplist: exact pleasantries held even when long/sustained ────────────

def test_4_stoplist_exact_match_held():
    assert "תודה רבה" in vol._GREETING_FRAGMENT_STOPLIST
    # 8 chars, 3.0s — fails on the stoplist regardless of duration
    assert is_verified_greeting_interruption("תודה רבה", 3.0) is False
    c = TurnController()
    _to_greeting_playing(c)
    assert _turn(c, "תודה רבה", 3.0) == []
    assert c.last_decision == "held_greeting"


def test_4b_gate_thresholds():
    # too short (9 chars) even when long enough in time
    assert is_verified_greeting_interruption("א" * 9, 3.0) is False
    # long enough in chars but too brief
    assert is_verified_greeting_interruption("א" * 12, 1.19) is False
    # both satisfied, not a pleasantry
    assert is_verified_greeting_interruption("א" * 12, 1.2) is True


# ── 5. genuine greeting interruption still accepted ─────────────────────────

def test_5_genuine_greeting_interruption_accepted():
    c = TurnController()
    _to_greeting_playing(c)
    acts = _turn(c, "אני רוצה לברר לגבי הפנסיה שלי", 2.0)
    assert _acts(acts) == [Action.CANCEL_AND_CLEAR, Action.RESPONSE_CREATE]
    assert c.last_decision == "accepted"
    assert c.state == CallState.ASSISTANT_RESPONDING
    assert c.valid_turns == 1
    # generation was active (greeting still generating) → cancel allowed
    assert _val(acts, Action.CANCEL_AND_CLEAR) == {"cancel": True}


# ── 6. normal caller turn after the greeting is unchanged (M2/M3) ───────────

def test_6_normal_turn_after_greeting_unchanged():
    c = TurnController()
    _to_waiting(c)
    acts = _turn(c, "אני צריך שיחזרו אליי לגבי ביטוח רכב", 1.8)
    assert _acts(acts) == [Action.RESPONSE_CREATE]     # no clear when waiting
    assert c.last_decision == "accepted"
    assert c.last_turn_id == 1


def test_6b_short_whitelist_turn_after_greeting_still_valid():
    """The greeting gate applies ONLY to GREETING_PLAYING — a short 'כן' in a
    waiting state is still a valid turn (M2 behavior preserved)."""
    c = TurnController()
    _to_waiting(c)
    acts = _turn(c, "כן", 0.3)
    assert Action.RESPONSE_CREATE in _acts(acts)
    assert c.last_decision == "accepted"


# ── 7/8. orphan, duplicate, late/obsolete rejection ─────────────────────────

def test_7_orphan_transcription_rejected():
    c = TurnController()
    _to_waiting(c)
    acts = c.on_input_transcription("אני רוצה לברר לגבי הפנסיה", dur=2.0)  # no speech pair
    assert acts == []
    assert c.last_decision == "orphan"
    assert c.valid_turns == 0


def test_7b_duplicate_transcription_for_consumed_segment_rejected():
    """A duplicate is rejected on BOTH paths: while the response is still
    generating the M2 state guard drops it; once playback has begun (a state
    that WOULD accept a barge-in) the consumed-segment rule drops it."""
    c = TurnController()
    _to_waiting(c)
    first = _turn(c, "אני רוצה לברר לגבי הפנסיה שלי", 2.0)
    assert Action.RESPONSE_CREATE in _acts(first)

    # (a) duplicate while generating → state guard
    dup_gen = c.on_input_transcription("אני רוצה לברר לגבי הפנסיה שלי", dur=2.0)
    assert dup_gen == []
    assert c.last_decision == "ignored_state"

    # (b) duplicate once PLAYING (barge-in-capable state) → segment rule
    c.on_response_created(); c.on_output_delta()
    assert c.state == CallState.RESPONDING_PLAYING
    dup_play = c.on_input_transcription("אני רוצה לברר לגבי הפנסיה שלי", dur=2.0)
    assert dup_play == []
    assert c.last_decision == "orphan"       # its segment was already consumed
    assert c._turn_seq == 1                  # no second turn minted either way


def test_7c_late_transcription_for_obsolete_segment_rejected():
    """A transcription whose item_id belongs to an older speech item than the
    segment currently awaiting one is dropped."""
    c = TurnController()
    _to_waiting(c)
    _segment(c, 2.0, item_id="item_NEW")
    acts = c.on_input_transcription("טקסט ישן מהסגמנט הקודם", dur=2.0, item_id="item_OLD")
    assert acts == []
    assert c.last_decision == "obsolete_segment"
    assert c.valid_turns == 0
    # the pending segment is still consumable by its own transcription
    ok = c.on_input_transcription("אני רוצה לברר לגבי הפנסיה", dur=2.0, item_id="item_NEW")
    assert Action.RESPONSE_CREATE in _acts(ok)


def test_8_segment_consumed_exactly_once_and_turn_ids_unique():
    c = TurnController()
    _to_waiting(c)
    ids = []
    for i in range(3):
        acts = _turn(c, f"אני רוצה לברר לגבי הפנסיה שלי מספר {i}", 2.0)
        assert Action.RESPONSE_CREATE in _acts(acts)
        ids.append(c.last_turn_id)
        # simulate the response completing back to a waiting state
        c.on_response_created(); c.on_output_delta()
        done = c.on_response_done("completed")
        c.on_twilio_mark(_mark_name(done))
    assert ids == [1, 2, 3]                  # unique, monotonic
    assert len(set(ids)) == 3
    assert c._segment_seq == 3


# ── 9. cancellation safety ──────────────────────────────────────────────────

def test_9_no_cancel_after_response_done_playback_only():
    """Barge-in while only PLAYBACK remains → clear yes, response.cancel NO."""
    c = TurnController()
    _to_waiting(c)
    _turn(c, "אני רוצה לברר לגבי הפנסיה שלי", 2.0)
    c.on_response_created()                  # generating
    c.on_output_delta()                      # → RESPONDING_PLAYING
    c.on_response_done("completed")          # generation finished, audio playing
    assert c._generation_active is False
    acts = _turn(c, "רגע רגע יש לי עוד שאלה", 0.8)
    assert _val(acts, Action.CANCEL_AND_CLEAR) == {"cancel": False}
    assert Action.RESPONSE_CREATE in _acts(acts)


def test_9b_cancel_sent_while_generating():
    c = TurnController()
    _to_waiting(c)
    _turn(c, "אני רוצה לברר לגבי הפנסיה שלי", 2.0)
    c.on_response_created()
    c.on_output_delta()                      # playing AND still generating
    assert c._generation_active is True
    acts = _turn(c, "רגע רגע יש לי עוד שאלה", 0.8)
    assert _val(acts, Action.CANCEL_AND_CLEAR) == {"cancel": True}


def test_9c_executor_honors_cancel_flag():
    src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
    assert '_do_cancel = val.get("cancel", True)' in src
    assert 'if _do_cancel:' in src
    # the Twilio clear is NOT inside the cancel branch (always sent)
    seg = src.split("elif act == Action.CANCEL_AND_CLEAR:")[1].split("elif act ==")[0]
    assert '"event": "clear"' in seg


# ── 10. response.create auditability ────────────────────────────────────────

def test_10_response_create_audit_fields_present():
    src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
    seg = src.split("if act == Action.RESPONSE_CREATE:")[1].split("elif act ==")[0]
    for field in ("segment_id=", "turn_id=", "text=", "state=", 'reason="valid_turn"'):
        assert field in seg, field
    assert 'reason="greeting"' in seg              # the single greeting create
    assert 'reason="watchdog_checkin"' in src      # the state-owned check-in


def test_10b_accepted_turn_exposes_audit_values():
    c = TurnController()
    _to_waiting(c)
    _turn(c, "אני צריך שיחזרו אליי לגבי ביטוח רכב", 1.8)
    assert c.last_decision == "accepted"
    assert c.last_turn_id == 1
    assert c.last_segment_id == 1
    assert c.last_turn_text == "אני צריך שיחזרו אליי לגבי ביטוח רכב"


def test_10c_no_accepted_text_means_no_caller_driven_create():
    """Held / orphan / rejected decisions never expose an accepted turn id."""
    c = TurnController()
    _to_greeting_playing(c)
    _turn(c, "תודה", 1.10)
    assert c.last_decision == "held_greeting"
    assert c.last_turn_id is None and c.last_turn_text == ""


# ── 11. held fragment excluded from caller conversation context ─────────────

def test_11_wiring_excludes_held_fragment_from_caller_lines():
    src = pathlib.Path(vol.__file__).read_text(encoding="utf-8")
    assert 'if _text and _decision != "held_greeting":' in src
    assert "_caller_lines.append(_text)" in src
    # and it is diagnosed
    assert '_diag("greeting_fragment_held"' in src
    assert '_diag("orphan_transcription"' in src
    assert '_diag("obsolete_transcription"' in src


# ── 12. M3 behavior preserved ───────────────────────────────────────────────

def test_12_responding_playing_barge_in_rule_unchanged():
    """Outside the greeting the 0.6s barge-in rule is untouched (M2/M3)."""
    c = TurnController()
    _to_waiting(c)
    _turn(c, "אני רוצה לברר לגבי הפנסיה שלי", 2.0)
    c.on_response_created(); c.on_output_delta()
    assert c.state == CallState.RESPONDING_PLAYING
    acts = _turn(c, "רגע רגע", 0.7)          # 7 chars — would FAIL the greeting gate
    assert Action.CANCEL_AND_CLEAR in _acts(acts)
    assert Action.RESPONSE_CREATE in _acts(acts)


def test_12b_watchdog_and_marks_untouched():
    c = TurnController()
    _to_waiting(c)
    assert c._timeout_gen == 1                       # armed by the greeting mark
    assert c.check_waiting_timeout(0.0) == []        # not elapsed
