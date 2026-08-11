"""
Roi Insurance prompt-behavior tests — insurance-category integrity + the "reached
Yon" scenario.

Incident 2026-08-05 (call from +972528490633, name יון): the caller asked for
**car** insurance ("רכב" said twice), but Maya's live spoken turns substituted
**life** insurance ("בביטוח חיים") — a model improvisation with no source in the
prompt or code (the prompt had zero insurance-category strings and no rule to
preserve the caller's stated topic). The email summary was correct; only the live
turns failed.

Fix = prompt-level (Supabase agents_config.system_prompt for Roi's voice agent):
- preserve the caller's stated insurance topic; never substitute one category for
  another; ask to confirm instead of guessing; never invent policy/price/coverage.
- handle "הגעתי ליון?" naturally as Roi's office WITHOUT redirecting to Yon.

The proposed prompt lives at tests/fixtures/roi_insurance_system_prompt.txt (the
review artifact and the source the eval runs against).

Two layers here:
  1. STRUCTURAL pins (always run, deterministic) — prove the fix text is present
     and that existing successful behavior is preserved.
  2. BEHAVIORAL eval (opt-in: RUN_PROMPT_EVAL=1 + a real OPENAI_API_KEY) — runs the
     5 required caller cases against the prompt via gpt-4o-mini as a *text proxy*
     for the realtime model. Skipped by default so normal CI stays offline/free.
"""
from __future__ import annotations

import os
import pathlib

import pytest

_PROMPT_PATH = pathlib.Path(__file__).parent / "fixtures" / "roi_insurance_system_prompt.txt"
PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# The eight categories Maya must recognize and never substitute — kept as a
# reference for the behavioral eval. Deliberately NOT enumerated in the prompt
# (see TestPromptStructure.test_no_eight_category_list_added).
CATEGORIES = [
    "ביטוח רכב", "ביטוח דירה", "ביטוח חיים", "ביטוח בריאות",
    "פנסיה", "קרן השתלמות", "אובדן כושר עבודה", "ביטוח עסק",
]


# ── 1. STRUCTURAL pins — the CONCISE fix is present, old behavior preserved ───
# Wording matches the approved short version (2 blocks, +644 chars). No
# eight-category list; no forced per-call topic confirmation.

class TestPromptStructure:
    def test_category_preservation_rule_present(self):
        # the core fix: keep the explicitly-stated topic, never swap categories
        assert "שמרי על הנושא שהלקוח אמר במפורש" in PROMPT
        assert "אל תחליפי אותו בסוג ביטוח אחר" in PROMPT

    def test_ask_to_confirm_instead_of_guessing(self):
        assert "בקשי מהלקוח לחזור עליו או לאשר אותו במקום לנחש" in PROMPT

    def test_multiple_topics_preserved(self):
        assert "אם הלקוח הזכיר כמה נושאים, שמרי את כולם" in PROMPT

    def test_no_category_menu_recited(self):
        # must not read out a product menu / suggest an unmentioned topic
        assert "אל תקריאי רשימת סוגי ביטוח ואל תציעי נושא שהלקוח לא הזכיר" in PROMPT

    def test_uncertain_expertise_takes_details(self):
        assert "אם אינך בטוחה אם רועי מטפל בנושא" in PROMPT
        assert "שרועי יחזור עם תשובה מדויקת" in PROMPT

    def test_no_eight_category_list_added(self):
        # requirement: do NOT add the eight-category enumeration. These tokens
        # appear only in such a list, so their absence pins the concise version.
        for cat in ["ביטוח בריאות", "פנסיה", "קרן השתלמות", "אובדן כושר עבודה"]:
            assert cat not in PROMPT, f"eight-category list must not be added: {cat!r}"

    def test_no_forced_per_call_confirmation(self):
        # requirement: don't force Maya to repeat/confirm the category every call
        assert "רשמתי שמדובר בביטוח רכב" not in PROMPT

    def test_yon_section_present(self):
        assert "━━ פניות שמיועדות ליון ━━" in PROMPT
        assert "אם הלקוח שואל אם הגיע ליון או אומר שניסה להשיג את יון" in PROMPT
        assert "הגעת למשרד של רועי. אני יכולה לקחת את הפרטים ולוודא שרועי יחזור אליך בנושא." in PROMPT

    def test_yon_is_never_a_redirect_destination(self):
        # must NOT hand the caller off to Yon or confirm they reached Yon
        assert "אל תפני את הלקוח ליון ואל תאשרי שהגיע ליון" in PROMPT
        # no transfer-to-Yon phrasing anywhere
        for bad in ["אעביר אותך ליון", "תתקשר ליון", "המספר של יון", "אני אחבר אותך ליון"]:
            assert bad not in PROMPT, f"prompt must not redirect to Yon: {bad!r}"

    def test_existing_successful_behavior_preserved(self):
        # the parts that already worked must remain intact (no unrelated changes)
        assert "את מאיה, המזכירה הדיגיטלית של רועי" in PROMPT      # identity
        assert "שאלה אחת בכל פעם" in PROMPT                        # one-question style
        assert "עם מי אני מדברת?" in PROMPT                        # neutral name protocol
        assert "אל תדברי על מחירים, הצעות או סכומים" in PROMPT      # no-prices
        assert "תודה, רשמתי הכל ואני מעבירה לרועי עכשיו" in PROMPT  # closing
        assert "טלפון המתקשר: {{caller_phone}}" in PROMPT          # placeholder intact

    def test_not_a_long_faq(self):
        # keep it tight — concise rules, not an FAQ (bumped for the ack-rule
        # polish: 2535 + 352 = 2887)
        assert len(PROMPT) < 3100, f"prompt grew too long ({len(PROMPT)} chars)"


# ── acknowledgment rules (live-call polish, Aug 2026) ─────────────────────────
# Incident: the old rule REQUIRED a short ack before every question, producing
# stacked acks for one caller thought ("אממ, סבבה." → "בסדר גמור, רק כדי...")
# and acks of nonexistent content after silence/echo turns.

class TestAckRules:
    def test_ack_no_longer_mandatory(self):
        # the old unconditional before-every-question rule must be gone
        assert "לפני שאלה, תני תגובה קצרה וטבעית" not in PROMPT
        # replaced by an explicitly OPTIONAL rule
        assert "אופציונלי" in PROMPT
        assert "אל תפתחי כל תשובה באישור אוטומטי" in PROMPT

    def test_single_ack_per_caller_turn(self):
        assert "לכל היותר אישור אחד לכל תור של הלקוח" in PROMPT

    def test_no_reack_after_interruption(self):
        assert "גם אם התשובה הקודמת נקטעה — אל תאשרי אותו שוב" in PROMPT
        assert "המשיכי ישר לשאלה או לתשובה הבאה" in PROMPT

    def test_no_ack_for_empty_content(self):
        assert "אם הלקוח לא מסר מידע חדש" in PROMPT
        assert 'אל תגידי "בסדר גמור" או "הבנתי" כאילו נמסר משהו' in PROMPT
        assert '"איך אפשר לעזור?"' in PROMPT              # the direct prompt instead

    def test_acks_not_banned_entirely(self):
        # natural single acks stay allowed (don't make Maya robotic)
        assert '"הבנתי"' in PROMPT and '"בסדר גמור"' in PROMPT
        # the good example still opens with a single ack
        assert '"הבנתי, על איזה ביטוח מדובר?"' in PROMPT

    def test_content_mirroring_rule_present(self):
        # The old mandatory ack doubled as a content mirror ("הבנתי, רכב וגם
        # דירה"); removing it silently dropped multi-topic echo (case4 went
        # 4/4→0/4 on the proxy). The explicit mirror rule restores it without
        # bringing back mandatory ack-noise.
        assert "שקפי בקצרה במילים שלך את מה שנמסר" in PROMPT
        assert 'אז ביטוח רכב וגם דירה — נתחיל ברכב?' in PROMPT
        assert "בלי לחזור על זה שוב בתורים הבאים" in PROMPT


# ── 2. BEHAVIORAL eval — the 5 required caller cases (opt-in) ─────────────────

RUN_EVAL = os.getenv("RUN_PROMPT_EVAL") == "1"
_HAS_KEY = bool((os.getenv("OPENAI_API_KEY") or "").strip()) and \
    (os.getenv("OPENAI_API_KEY") or "").strip() != "test-openai-key"

pytestmark_reason = "set RUN_PROMPT_EVAL=1 with a real OPENAI_API_KEY to run the live prompt eval"


def _ask(caller_line: str) -> str:
    """One-turn probe: system=Roi prompt, user=caller line. Text proxy (gpt-4o-mini)
    for the realtime model — checks the PROMPT's category integrity, not the exact
    voice model. Never used in normal CI."""
    import httpx
    key = os.environ["OPENAI_API_KEY"].strip()
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": PROMPT.replace("{{caller_phone}}", "+972500000000")},
            {"role": "user", "content": caller_line},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    r = httpx.post("https://api.openai.com/v1/chat/completions", json=body,
                   headers={"Authorization": f"Bearer {key}"}, timeout=30.0)
    r.raise_for_status()
    return (r.json()["choices"][0]["message"]["content"] or "").strip()


@pytest.mark.skipif(not (RUN_EVAL and _HAS_KEY), reason=pytestmark_reason)
class TestBehavioralEval:
    def test_case1_reached_yon_wants_car_quote(self):
        # Single-turn probe → assert the SAFETY invariants (Roi's office, no Yon
        # redirect, no category substitution). Explicit "רכב" echo-back happens
        # over multiple turns and is a live-realtime-model validation item.
        out = _ask("הגעתי ליון? אני רוצה הצעה לביטוח רכב.")
        assert "רועי" in out                          # clarify it's Roi's office
        assert "חיים" not in out                      # NO life-insurance substitution
        # no redirect to Yon / no claim the caller reached Yon
        for bad in ["אעביר אותך ליון", "תתקשר ליון", "המספר של יון", "הגעת ליון"]:
            assert bad not in out
        # the car topic must not be swapped for a different category
        for other in ["ביטוח דירה", "ביטוח בריאות", "פנסיה", "קרן השתלמות",
                      "אובדן כושר עבודה", "ביטוח עסק"]:
            assert other not in out

    def test_case2_home_insurance_preserved(self):
        out = _ask("אני צריכה ביטוח דירה.")
        assert "דירה" in out
        for other in ["ביטוח רכב", "ביטוח חיים", "ביטוח בריאות"]:
            assert other not in out                  # no substitution

    def test_case3_business_insurance_unsure_expertise(self):
        # The safety-critical invariant: never fabricate a definitive claim about
        # whether Roi handles the product (neither a "yes we do" nor a "no we
        # don't"). Saying explicitly "Roi will return with an answer" is the
        # multi-turn ideal and is a live-realtime-model validation item.
        out = _ask("אני לא בטוחה אם אתם מטפלים בביטוח עסק.")
        for bad in ["בוודאי שאנחנו מטפלים", "בהחלט מטפלים", "אנחנו מטפלים בכל",
                    "אנחנו לא מטפלים", "רועי לא מטפל"]:
            assert bad not in out
        # no substitution away from the business-insurance topic
        for other in ["ביטוח רכב", "ביטוח חיים", "ביטוח דירה", "ביטוח בריאות"]:
            assert other not in out

    def test_case4_multiple_topics_preserved(self):
        out = _ask("ביטוח רכב וגם דירה.")
        assert "רכב" in out and "דירה" in out         # both preserved

    def test_case5_quote_request_no_invented_price(self):
        out = _ask("כמה יעלה לי ביטוח רכב? תני לי מחיר.")
        # no invented shekel amount / concrete price
        import re
        assert not re.search(r"\d[\d,]*\s*(₪|שקל|ש\"ח)", out), f"invented a price: {out}"
        assert "רכב" in out


def _ask_multi(messages: list) -> str:
    """Multi-turn probe (same text proxy): messages = [(role, content), ...]."""
    import httpx
    key = os.environ["OPENAI_API_KEY"].strip()
    body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "system",
                      "content": PROMPT.replace("{{caller_phone}}", "+972500000000")}]
                    + [{"role": r, "content": c} for r, c in messages],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    r = httpx.post("https://api.openai.com/v1/chat/completions", json=body,
                   headers={"Authorization": f"Bearer {key}"}, timeout=30.0)
    r.raise_for_status()
    return (r.json()["choices"][0]["message"]["content"] or "").strip()


_ACK_TOKENS = ["אהמ", "אממ", "הבנתי", "אוקיי", "בסדר גמור", "סבבה"]


def _count_acks(text: str) -> int:
    return sum(text.count(t) for t in _ACK_TOKENS)


@pytest.mark.skipif(not (RUN_EVAL and _HAS_KEY), reason=pytestmark_reason)
class TestAckBehavioralEval:
    def test_one_fact_no_stacked_acks(self):
        # one caller fact → at most one ack, then progress (a question)
        out = _ask_multi([("user", "אני רוצה ביטוח חיים.")])
        assert _count_acks(out) <= 1, f"stacked acks: {out}"
        assert "?" in out, f"no forward progress: {out}"

    def test_interrupted_response_not_reacknowledged(self):
        # Maya already acked ("אממ, סבבה") and was cut off; the caller's fact is
        # already acknowledged → the next reply must not re-ack, must progress.
        out = _ask_multi([
            ("user", "אני רוצה ביטוח חיים."),
            ("assistant", "אממ, סבבה"),          # the interrupted partial reply
            ("user", "כן, ביטוח חיים."),
        ])
        assert _count_acks(out) <= 1, f"re-acknowledged after interruption: {out}"
        assert "?" in out, f"no forward progress: {out}"

    def test_meaningless_content_gets_direct_prompt_not_ack(self):
        # a bare hesitation carries no information → no "בסדר גמור"/"הבנתי"
        out = _ask_multi([("user", "אה...")])
        assert "בסדר גמור" not in out and "הבנתי" not in out, f"acked nothing: {out}"
