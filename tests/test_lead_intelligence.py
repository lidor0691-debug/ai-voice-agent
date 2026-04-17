"""
Tests for app/services/lead_intelligence.py
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
    assert results[0]["metadata"]["extraction_version"] == "1.0"


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
async def test_save_insights_never_raises_on_error():
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
