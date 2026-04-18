"""
Tests for app/services/lead_intelligence.py
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.lead_intelligence import normalize_text, extract_insights


# ── normalize_text ────────────────────────────────────────────────────────────

def test_normalize_lowercase():
    assert normalize_text("Hello World") == "hello world"


def test_normalize_strips_whitespace():
    assert normalize_text("  hello  ") == "hello"


def test_normalize_collapses_internal_whitespace():
    assert normalize_text("hello   world") == "hello world"


def test_normalize_strips_trailing_punctuation_not_question_mark():
    assert normalize_text("hello world.") == "hello world"
    assert normalize_text("hello world,") == "hello world"
    assert normalize_text("hello world!") == "hello world"
    assert normalize_text("hello world;") == "hello world"
    assert normalize_text("hello world:") == "hello world"
    assert normalize_text("מה המחיר?") == "מה המחיר?"  # ? preserved


def test_normalize_empty_string():
    assert normalize_text("") == ""


def test_normalize_only_whitespace():
    assert normalize_text("   ") == ""


# ── extract_insights ──────────────────────────────────────────────────────────

def test_extract_question_by_trailing_question_mark():
    results = extract_insights("כמה עולה המנוי?")
    assert len(results) == 1
    r = results[0]
    assert r["insight_type"] == "question"
    assert r["metadata"]["matched_rule"] == "ends_with_question_mark"
    assert r["original_text"] == "כמה עולה המנוי?"
    assert r["normalized_text"] == "כמה עולה המנוי"  # ? stripped by caller


def test_extract_question_by_question_word():
    results = extract_insights("מה כולל המחיר")
    assert len(results) == 1
    r = results[0]
    assert r["insight_type"] == "question"
    assert r["metadata"]["matched_rule"] == "question_word"


def test_extract_question_mark_takes_precedence_over_question_word():
    results = extract_insights("מה המחיר?")
    assert results[0]["metadata"]["matched_rule"] == "ends_with_question_mark"


def test_extract_objection():
    results = extract_insights("זה יקר מדי בשבילי")
    assert len(results) == 1
    assert results[0]["insight_type"] == "objection"
    assert results[0]["metadata"]["matched_rule"] == "objection_cue"


def test_extract_multi_pattern_emits_two_insights():
    results = extract_insights("האם זה לא יקר מדי?")
    insight_types = {r["insight_type"] for r in results}
    assert "question" in insight_types
    assert "objection" in insight_types
    assert len(results) == 2


def test_extract_skips_noise_under_2_words_no_match():
    results = extract_insights("אוקי")
    assert results == []


def test_extract_keeps_short_question():
    results = extract_insights("מחיר?")
    assert len(results) == 1
    assert results[0]["insight_type"] == "question"


def test_extract_title_is_first_6_words():
    results = extract_insights("מה כולל החבילה הזאת בדיוק ולמה היא עולה כל כך הרבה?")
    assert results[0]["title"] == "מה כולל החבילה הזאת בדיוק ולמה"


def test_extract_title_fallback_when_too_short():
    results = extract_insights("למה?")
    assert results[0]["title"] == "insight"


def test_extract_splits_on_newline():
    text = "מה המחיר?\nאני לא בטוח שזה מתאים לי"
    results = extract_insights(text)
    types = {r["insight_type"] for r in results}
    assert "question" in types
    assert "objection" in types


def test_extract_does_not_split_on_question_mark():
    text = "מה המחיר? ומה כולל?"
    results = extract_insights(text)
    assert any(r["insight_type"] == "question" for r in results)


def test_extract_english_question_word():
    results = extract_insights("How much does it cost")
    assert results[0]["insight_type"] == "question"
    assert results[0]["metadata"]["matched_rule"] == "question_word"


def test_extract_english_objection():
    results = extract_insights("I'm not sure this is the right fit for me")
    assert results[0]["insight_type"] == "objection"


def test_extract_metadata_has_extraction_version():
    results = extract_insights("מה המחיר?")
    assert results[0]["metadata"]["extraction_version"] == "1.1"


# ── intent_signal detection ───────────────────────────────────────────────────

def test_extract_intent_signal_interest_explicit():
    # "אני מתעניינת לגבי בת מצווה" — real BPM pattern
    results = extract_insights("אני מתעניינת לגבי בת מצווה")
    assert len(results) == 1
    r = results[0]
    assert r["insight_type"] == "intent_signal"
    assert r["metadata"]["matched_rule"] == "interest_cue"


def test_extract_intent_signal_interest_single_word():
    # "מתעניינת" alone — 1 word but matches pattern, should be kept
    results = extract_insights("מתעניינת")
    assert len(results) == 1
    assert results[0]["insight_type"] == "intent_signal"
    assert results[0]["metadata"]["matched_rule"] == "interest_cue"


def test_extract_intent_signal_hesitation_single_word():
    # "מתלבטת" — real BPM response, 1 word, should be captured
    results = extract_insights("מתלבטת")
    assert len(results) == 1
    assert results[0]["insight_type"] == "intent_signal"
    assert results[0]["metadata"]["matched_rule"] == "hesitation_cue"


def test_extract_intent_signal_hesitation_phrase():
    # "כרגע אין תאריך" — real BPM response
    results = extract_insights("כרגע אין תאריך")
    assert len(results) == 1
    assert results[0]["insight_type"] == "intent_signal"
    assert results[0]["metadata"]["matched_rule"] == "hesitation_cue"


def test_extract_intent_signal_context_no_experience():
    # "לא אין לה ניסיון" — real BPM response
    results = extract_insights("לא אין לה ניסיון")
    assert len(results) == 1
    assert results[0]["insight_type"] == "intent_signal"
    assert results[0]["metadata"]["matched_rule"] == "context_cue"


def test_extract_short_noise_not_captured():
    # "כן" and "לא" alone — no pattern match, should be skipped
    assert extract_insights("כן") == []
    assert extract_insights("לא") == []


def test_extract_intent_signal_does_not_fire_on_generic_text():
    # plain response with no signal cue
    results = extract_insights("יום ראשון")
    assert results == []


def test_extract_intent_signal_multi_pattern_with_objection():
    # "לא בטוח, מתלבט" — matches both objection and hesitation → two insights
    results = extract_insights("לא בטוח, מתלבט")
    types = {r["insight_type"] for r in results}
    assert "objection" in types
    assert "intent_signal" in types


def test_extract_intent_title_fallback_single_word():
    # single-word match → title fallback = "insight"
    results = extract_insights("מתלבטת")
    assert results[0]["title"] == "insight"


def test_extract_real_bpm_conversation_user_messages():
    # Simulate the real Conv 1 user messages joined by newline
    text = (
        "שיעור ניסיון בסטודיו\n"
        "היא בת 8\n"
        "יום ראשון\n"
        "אני מתעניינת לגבי בת מצווה\n"
        "כרגע אין תאריך\n"
        "מתלבטת\n"
        "לא אין לה ניסיון"
    )
    results = extract_insights(text)
    types = [r["insight_type"] for r in results]
    rules = [r["metadata"]["matched_rule"] for r in results]

    # Should capture the 4 meaningful signals, skip the noise
    assert "intent_signal" in types
    assert "interest_cue" in rules
    assert "hesitation_cue" in rules
    assert "context_cue" in rules
    # Should NOT capture "שיעור ניסיון בסטודיו", "היא בת 8", "יום ראשון"
    original_texts = [r["original_text"] for r in results]
    assert not any("שיעור ניסיון" in t for t in original_texts)
    assert not any("היא בת 8" in t for t in original_texts)
    assert not any("יום ראשון" in t for t in original_texts)


# ── win_signal detection ──────────────────────────────────────────────────────

def test_extract_win_signal_kabanu():
    results = extract_insights("קבענו לפגישה ביום שלישי")
    types = [r["insight_type"] for r in results]
    assert "win_signal" in types
    win = next(r for r in results if r["insight_type"] == "win_signal")
    assert win["metadata"]["matched_rule"] == "win_signal_cue"


def test_extract_win_signal_lisgor():
    results = extract_insights("אני רוצה לסגור את העניין")
    types = [r["insight_type"] for r in results]
    assert "win_signal" in types


def test_extract_win_signal_lishlaem():
    results = extract_insights("אפשר לשלם עכשיו")
    types = [r["insight_type"] for r in results]
    assert "win_signal" in types


def test_extract_win_signal_matkhilim():
    results = extract_insights("מתי מתחילים את השיעורים")
    types = [r["insight_type"] for r in results]
    assert "win_signal" in types


def test_extract_win_signal_efshar_likboa():
    results = extract_insights("אפשר לקבוע פגישה להשבוע")
    types = [r["insight_type"] for r in results]
    assert "win_signal" in types


def test_extract_win_signal_no_false_positive_general_chat():
    # Generic greeting — should not trigger win_signal
    results = extract_insights("שלום, אני מתעניין בשיעור ניסיון")
    types = [r["insight_type"] for r in results]
    assert "win_signal" not in types


def test_extract_win_signal_no_false_positive_price_question():
    # Price question — should trigger question, not win_signal
    results = extract_insights("כמה עולה השיעור?")
    types = [r["insight_type"] for r in results]
    assert "win_signal" not in types


def test_extract_win_signal_no_false_positive_hesitation():
    # Hesitation — should not trigger win_signal
    results = extract_insights("אני צריך לחשוב על זה")
    types = [r["insight_type"] for r in results]
    assert "win_signal" not in types


def test_extract_win_signal_title_populated():
    results = extract_insights("קבענו לפגישה ביום שלישי")
    win = next(r for r in results if r["insight_type"] == "win_signal")
    assert win["title"] != "insight"  # enough words for a real title


# ── save_insights ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_insights_returns_empty_when_not_configured():
    from app.services.lead_intelligence import save_insights
    with patch("app.services.lead_intelligence._is_configured", return_value=False):
        result = await save_insights(
            insights=[{"insight_type": "question", "normalized_text": "מה המחיר", "title": "מה המחיר", "original_text": "מה המחיר?", "metadata": {}}],
            client_id="client-1",
            agent_id=None,
            source_type="whatsapp",
            source_record_id=None,
        )
    assert result == []


@pytest.mark.asyncio
async def test_save_insights_returns_empty_when_no_insights():
    from app.services.lead_intelligence import save_insights
    with patch("app.services.lead_intelligence._is_configured", return_value=True):
        result = await save_insights(
            insights=[],
            client_id="client-1",
            agent_id=None,
            source_type="whatsapp",
            source_record_id=None,
        )
    assert result == []


@pytest.mark.asyncio
async def test_save_insights_inserts_when_no_existing_row():
    from app.services.lead_intelligence import save_insights

    inserted_row = {"id": "new-id", "insight_type": "question", "frequency_count": 1}

    with patch("app.services.lead_intelligence._is_configured", return_value=True), \
         patch("app.services.lead_intelligence._find_existing", new=AsyncMock(return_value=None)), \
         patch("app.services.lead_intelligence._insert_insight", new=AsyncMock(return_value=inserted_row)):
        result = await save_insights(
            insights=[{"insight_type": "question", "normalized_text": "מה המחיר", "title": "מה המחיר", "original_text": "מה המחיר?", "metadata": {}}],
            client_id="client-1",
            agent_id=None,
            source_type="whatsapp",
            source_record_id=None,
        )

    assert result == [inserted_row]


@pytest.mark.asyncio
async def test_save_insights_increments_frequency_when_existing_row():
    from app.services.lead_intelligence import save_insights

    existing_row = {"id": "existing-id", "frequency_count": 2}
    updated_row = {"id": "existing-id", "frequency_count": 3}

    with patch("app.services.lead_intelligence._is_configured", return_value=True), \
         patch("app.services.lead_intelligence._find_existing", new=AsyncMock(return_value=existing_row)), \
         patch("app.services.lead_intelligence._increment_frequency", new=AsyncMock(return_value=updated_row)):
        result = await save_insights(
            insights=[{"insight_type": "question", "normalized_text": "מה המחיר", "title": "מה המחיר", "original_text": "מה המחיר?", "metadata": {}}],
            client_id="client-1",
            agent_id=None,
            source_type="whatsapp",
            source_record_id=None,
        )

    assert result == [updated_row]


@pytest.mark.asyncio
async def test_save_insights_never_raises_on_error_and_returns_empty():
    from app.services.lead_intelligence import save_insights

    with patch("app.services.lead_intelligence._is_configured", return_value=True), \
         patch("app.services.lead_intelligence._find_existing", new=AsyncMock(side_effect=Exception("network error"))):
        result = await save_insights(
            insights=[{"insight_type": "question", "normalized_text": "מה המחיר", "title": "מה המחיר", "original_text": "מה המחיר?", "metadata": {}}],
            client_id="client-1",
            agent_id=None,
            source_type="whatsapp",
            source_record_id=None,
        )

    assert result == []


# ── API route ─────────────────────────────────────────────────────────────────

def _make_test_app():
    """Minimal FastAPI app with only the lead intelligence router — avoids main.py stream side-effects."""
    from fastapi import FastAPI
    from app.routes.lead_intelligence_api import router as lead_intelligence_router
    _app = FastAPI()
    _app.include_router(lead_intelligence_router)
    return _app


@pytest.mark.asyncio
async def test_test_extract_route_returns_extracted_and_saved():
    from httpx import AsyncClient, ASGITransport

    mock_saved = [{"id": "abc", "insight_type": "question", "frequency_count": 1}]

    with patch("app.routes.lead_intelligence_api.save_insights", new=AsyncMock(return_value=mock_saved)):
        transport = ASGITransport(app=_make_test_app())
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/lead-intelligence/test-extract", json={
                "client_id":        "00000000-0000-0000-0000-000000000001",
                "agent_id":         None,
                "source_type":      "whatsapp",
                "source_record_id": None,
                "text":             "מה המחיר?"
            })

    assert resp.status_code == 200
    body = resp.json()
    assert "extracted" in body
    assert "saved" in body
    assert len(body["extracted"]) >= 1
    assert body["extracted"][0]["insight_type"] == "question"
    assert body["saved"] == mock_saved


@pytest.mark.asyncio
async def test_test_extract_route_validates_source_type():
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=_make_test_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/lead-intelligence/test-extract", json={
            "client_id":   "00000000-0000-0000-0000-000000000001",
            "source_type": "invalid_source",
            "text":        "מה המחיר?"
        })

    assert resp.status_code == 422
