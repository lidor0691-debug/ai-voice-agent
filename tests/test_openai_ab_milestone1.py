"""
Milestone 1 tests — OpenAI Realtime A/B path (Roi-only, flag-gated).

Covers, with no real network:
  1. A/B gate (voice_shared.openai_ab_enabled): default OFF, requires
     flag + allowlisted client_id, empty allowlist = off for everyone.
  2. Entry dispatch (voice_gemini_entry): stream URL targets stream-openai
     ONLY when the gate matches; otherwise stream-gemini (bit-identical
     fallback). <Parameter> handoff is present in both cases.
  3. GA session.update shape: type=realtime, audio/pcmu passthrough both
     directions, server_vad, input transcription enabled, instructions carry
     the one-time greeting exactly once and never the word "תמיד".
  4. Transcript separation: extraction text is built from caller lines ONLY —
     assistant lines can never leak a name into extraction.
  5. Model env default: gpt-realtime-2.1.
"""
from __future__ import annotations

import os
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9999")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "svc_test_key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from unittest.mock import AsyncMock, patch

import pytest

import app.services.voice_shared as vs
import app.routes.voice_gemini as vg
import app.routes.voice_openai_live as vol

ROI_CLIENT_ID = "c-roi-uuid"

VALID_CFG = {
    "client_id":       ROI_CLIENT_ID,
    "client_name":     "מאיה - Roi Insurance",
    "prompt_override": "PROMPT for {{caller_phone}}",
    "first_message":   "שלום, הגעתם לסוכנות הביטוח",
    "webhook_url":     "http://hook.example/roi",
    "fallback_used":   False,
}


# ── 1. Gate ───────────────────────────────────────────────────────────────────

class TestOpenAIABGate:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_REALTIME_AB_ENABLED", False)
        monkeypatch.setattr(vs, "OPENAI_REALTIME_CLIENT_IDS", set())
        assert vs.openai_ab_enabled(ROI_CLIENT_ID) is False

    def test_flag_on_but_empty_allowlist_is_off(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_REALTIME_AB_ENABLED", True)
        monkeypatch.setattr(vs, "OPENAI_REALTIME_CLIENT_IDS", set())
        assert vs.openai_ab_enabled(ROI_CLIENT_ID) is False

    def test_allowlisted_but_flag_off_is_off(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_REALTIME_AB_ENABLED", False)
        monkeypatch.setattr(vs, "OPENAI_REALTIME_CLIENT_IDS", {ROI_CLIENT_ID})
        assert vs.openai_ab_enabled(ROI_CLIENT_ID) is False

    def test_flag_on_and_allowlisted_is_on(self, monkeypatch):
        monkeypatch.setattr(vs, "OPENAI_REALTIME_AB_ENABLED", True)
        monkeypatch.setattr(vs, "OPENAI_REALTIME_CLIENT_IDS", {ROI_CLIENT_ID})
        assert vs.openai_ab_enabled(ROI_CLIENT_ID) is True

    def test_other_tenant_stays_off(self, monkeypatch):
        """Studio (or any other tenant) must never dispatch to OpenAI."""
        monkeypatch.setattr(vs, "OPENAI_REALTIME_AB_ENABLED", True)
        monkeypatch.setattr(vs, "OPENAI_REALTIME_CLIENT_IDS", {ROI_CLIENT_ID})
        assert vs.openai_ab_enabled("c-studio-uuid") is False
        assert vs.openai_ab_enabled("") is False


# ── 2. Entry dispatch ─────────────────────────────────────────────────────────

def _fake_request(form: dict):
    class _URL:
        hostname = "example.railway.app"

    class _Req:
        url = _URL()

        async def form(self):
            return form

    return _Req()


FORM = {"To": "+972533470757", "From": "+972501234567", "CallSid": "CA_test_ab"}


class TestEntryDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_to_openai_when_gate_on(self, monkeypatch):
        monkeypatch.setattr(vg, "_openai_ab_enabled", lambda cid: cid == ROI_CLIENT_ID)
        with patch.object(vg, "fetch_supabase_agent_config", AsyncMock(return_value=dict(VALID_CFG))):
            resp = await vg.voice_gemini_entry(_fake_request(FORM))
        body = resp.body.decode()
        assert "/voice-ai/stream-openai" in body
        assert "stream-gemini" not in body
        # <Parameter> handoff intact
        assert 'name="client_id"' in body and ROI_CLIENT_ID in body
        assert 'name="caller_phone"' in body

    @pytest.mark.asyncio
    async def test_dispatch_to_gemini_when_gate_off(self, monkeypatch):
        monkeypatch.setattr(vg, "_openai_ab_enabled", lambda cid: False)
        with patch.object(vg, "fetch_supabase_agent_config", AsyncMock(return_value=dict(VALID_CFG))):
            resp = await vg.voice_gemini_entry(_fake_request(FORM))
        body = resp.body.decode()
        assert "/voice-ai/stream-gemini" in body
        assert "stream-openai" not in body
        assert 'name="client_id"' in body

    @pytest.mark.asyncio
    async def test_fail_closed_unaffected_by_gate(self, monkeypatch):
        """Unknown number still rejects with error TwiML even when gate is on."""
        monkeypatch.setattr(vg, "_openai_ab_enabled", lambda cid: True)
        bad_cfg = {"fallback_used": True, "prompt_override": "", "client_id": ""}
        with patch.object(vg, "fetch_supabase_agent_config", AsyncMock(return_value=bad_cfg)):
            resp = await vg.voice_gemini_entry(_fake_request(FORM))
        body = resp.body.decode()
        assert "<Say" in body
        assert "stream-openai" not in body and "stream-gemini" not in body


# ── 3. GA session.update shape ────────────────────────────────────────────────

class TestSessionUpdateShape:
    def _session(self, instruction="P"):
        msg = vol._build_session_update(instruction)
        assert msg["type"] == "session.update"
        return msg["session"]

    def test_ga_realtime_type_and_audio_pcmu_passthrough(self):
        s = self._session()
        assert s["type"] == "realtime"
        assert s["audio"]["input"]["format"]["type"] == "audio/pcmu"
        assert s["audio"]["output"]["format"]["type"] == "audio/pcmu"
        assert s["output_modalities"] == ["audio"]

    def test_server_vad_and_input_transcription_enabled(self):
        s = self._session()
        td = s["audio"]["input"]["turn_detection"]
        assert td["type"] == "server_vad"
        assert s["audio"]["input"]["transcription"]["model"] == vol.OPENAI_REALTIME_TRANSCRIBE_MODEL

    def test_no_tools_in_milestone_1(self):
        s = self._session()
        assert "tools" not in s and "tool_choice" not in s

    def test_instructions_carry_one_time_greeting_once(self):
        # M1.1: the OpenAI path uses its own natural opening instruction
        # (greeting-as-intent), not the Gemini "exactly this sentence" one.
        base = "PROMPT BODY"
        fm = "שלום, הגעתם לסוכנות הביטוח"
        instruction = vol._openai_opening_instruction(base, fm)
        s = self._session(instruction)
        assert s["instructions"].count(fm) == 1
        assert "פעם אחת בלבד" in s["instructions"]
        assert "תמיד" not in s["instructions"]
        assert s["instructions"].endswith(base)


# ── 4. Transcript separation ──────────────────────────────────────────────────

class TestTranscriptSeparation:
    def test_extraction_text_is_caller_only(self):
        caller = ["שלום, מדבר דוד", "אני צריך ביטוח רכב"]
        assistant = ["שלום, כאן מאיה מסוכנות הביטוח", "בשמחה, דוד"]
        text = vol._customer_transcript(caller)
        assert "דוד" in text and "ביטוח רכב" in text
        assert "מאיה" not in text          # assistant speech can never leak in
        assert all(line.startswith("לקוח:") for line in text.splitlines())

    def test_empty_caller_lines_skip_extraction_text(self):
        assert vol._customer_transcript([]) == ""
        assert vol._customer_transcript(["", "   "]) == ""

    def test_full_transcript_keeps_roles_separate(self):
        full = vol._full_transcript(["היי"], ["שלום"])
        assert "לקוח: היי" in full and "מאיה: שלום" in full


# ── 5. Model config ───────────────────────────────────────────────────────────

class TestModelConfig:
    def test_default_model_is_gpt_realtime_2_1(self):
        # env not set in CI/test → module default must be the verified GA model
        if not os.getenv("OPENAI_REALTIME_MODEL"):
            assert vol.OPENAI_REALTIME_MODEL == "gpt-realtime-2.1"

    def test_ws_url_carries_model(self):
        assert vol._OPENAI_WS_URL.format(model="gpt-realtime-2.1").endswith(
            "/v1/realtime?model=gpt-realtime-2.1"
        )
