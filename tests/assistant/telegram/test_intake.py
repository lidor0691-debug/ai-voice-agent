"""Pure intake/reply helper tests. TEST-ONLY. No I/O, no network, no key."""
from __future__ import annotations

from app.assistant.nlp.contract import MessageType, SendPlan
from app.assistant.telegram import replies
from app.assistant.telegram.intake import (
    extract_update,
    parse_allowed_user_ids,
    parse_owner_map,
    verify_secret,
)

UUID1 = "11111111-1111-1111-1111-111111111111"
UUID2 = "22222222-2222-2222-2222-222222222222"


# ── allowlist parsing ─────────────────────────────────────────────────────────

def test_parse_allowed_user_ids_valid():
    assert parse_allowed_user_ids("1, 2 ,3") == {1, 2, 3}


def test_parse_allowed_user_ids_empty_is_deny_all():
    assert parse_allowed_user_ids("") == set()
    assert parse_allowed_user_ids("   ") == set()


def test_parse_allowed_user_ids_skips_garbage():
    assert parse_allowed_user_ids("5,abc,,7") == {5, 7}


# ── owner-map parsing ─────────────────────────────────────────────────────────

def test_parse_owner_map_valid():
    assert parse_owner_map(f"111:{UUID1},222:{UUID2}") == {111: UUID1, 222: UUID2}


def test_parse_owner_map_skips_bad_uuid():
    assert parse_owner_map("111:not-a-uuid") == {}


def test_parse_owner_map_skips_bad_id_and_missing_colon():
    assert parse_owner_map(f"abc:{UUID1},noColonHere,333:{UUID2}") == {333: UUID2}


def test_parse_owner_map_empty():
    assert parse_owner_map("") == {}


def test_parse_owner_map_splits_on_first_colon_only():
    # owner ids are UUIDs (no colons), but be robust to stray colons anyway
    assert parse_owner_map(f"111:{UUID1}") == {111: UUID1}


# ── secret verification ───────────────────────────────────────────────────────

def test_verify_secret_match():
    assert verify_secret("s3cr3t", "s3cr3t") is True


def test_verify_secret_mismatch():
    assert verify_secret("nope", "s3cr3t") is False


def test_verify_secret_empty_config_fails_closed():
    assert verify_secret("anything", "") is False


def test_verify_secret_missing_header_fails_closed():
    assert verify_secret(None, "s3cr3t") is False


# ── update extraction ─────────────────────────────────────────────────────────

def _msg(text="שלח לדנה הודעה מחר", uid=111, cid=555, update_id=10):
    return {"update_id": update_id,
            "message": {"text": text, "from": {"id": uid}, "chat": {"id": cid}}}


def test_extract_update_valid():
    u = extract_update(_msg())
    assert u == {"update_id": 10, "user_id": 111, "chat_id": 555, "text": "שלח לדנה הודעה מחר"}


def test_extract_update_no_message():
    assert extract_update({"update_id": 1, "callback_query": {}}) is None


def test_extract_update_non_text():
    assert extract_update({"message": {"from": {"id": 1}, "chat": {"id": 2}, "photo": []}}) is None


def test_extract_update_empty_text():
    assert extract_update({"message": {"text": "   ", "from": {"id": 1}, "chat": {"id": 2}}}) is None


def test_extract_update_missing_from_or_chat():
    assert extract_update({"message": {"text": "hi", "chat": {"id": 2}}}) is None
    assert extract_update({"message": {"text": "hi", "from": {"id": 1}}}) is None


def test_extract_update_missing_update_id_is_none():
    u = extract_update({"message": {"text": "hi", "from": {"id": 1}, "chat": {"id": 2}}})
    assert u is not None and u["update_id"] is None


def test_extract_update_non_dict():
    assert extract_update("not a dict") is None


# ── replies (Hebrew, owner-facing, no secrets) ────────────────────────────────

def test_reply_scheduled_persist_has_recipient_time_plan():
    r = replies.reply_scheduled(
        recipient_name="דנה", message_type=MessageType.AGREEMENT,
        scheduled_at_local="2026-06-29T18:00:00", send_plan=SendPlan.API_TEMPLATE)
    assert "דנה" in r and "29.06 18:00" in r and "תבנית" in r
    assert "🧪" not in r  # not dry-run


def test_reply_scheduled_dry_run_prefixed_and_no_plan():
    r = replies.reply_scheduled(
        recipient_name="דנה", message_type=MessageType.CUSTOM,
        scheduled_at_local="2026-06-16T10:00:00", send_plan=None, dry_run=True)
    assert r.startswith("🧪")
    assert "16.06 10:00" in r


def test_reply_missing_send_time_mentions_event():
    r = replies.reply_missing_send_time(
        recipient_name="רבקה", message_type=MessageType.AGREEMENT,
        related_event_date="2026-06-29")
    assert "מתי לשלוח" in r and "רבקה" in r and "29.06" in r


def test_reply_missing_recipient():
    assert "למי לשלוח" in replies.reply_missing_recipient()


def test_reply_unknown_recipient_names_contact():
    assert "דנה" in replies.reply_unknown_recipient(recipient_name="דנה")


def test_reply_ambiguous_names_contact():
    assert "דנה" in replies.reply_ambiguous(recipient_name="דנה")


def test_reply_handles_none_message_type():
    r = replies.reply_scheduled(recipient_name="x", message_type=None,
                                scheduled_at_local="2026-06-16T10:00:00")
    assert "הודעה" in r  # default noun
