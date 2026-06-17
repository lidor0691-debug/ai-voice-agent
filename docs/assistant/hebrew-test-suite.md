# Maya Assistant — Hebrew Eval Suite (25 cases)

Human-readable companion to `tests/assistant/nlp/cases.py`. TEST-ONLY.

Frozen clock: **NOW = 2026-06-15 12:00 (Mon), Asia/Jerusalem**
→ today `2026-06-15`, tomorrow `2026-06-16`, day-after `2026-06-17`.

**Must-pass set** (event-date vs send-date): **1, 12, 13, 14, 15, 21, 22, 23**.

| # | Command (he) | Expected outcome |
|--:|---|---|
| 1*  | שלח לדנה תזכורת ב-29.6 בשעה 18:00 | parsed · send `2026-06-29T18:00` (explicit) · no event |
| 2  | שלח לדנה הודעה מחר בשעה 14:00 | parsed · send `2026-06-16T14:00` |
| 3  | תזכיר ליוסי על השיעור היום ב-20:00 | parsed · teacher · lesson_coordination · `2026-06-15T20:00` |
| 4  | שלח לרבקה הסכם מחר ב-09:30 | parsed · agreement · `2026-06-16T09:30` |
| 5  | שלח לדנה הודעה | needs_clarification · missing send time |
| 6  | שלח לקבוצת בוקר הודעה מחר ב-09:00 | parsed · group → resolves `group_manual` |
| 7  | שלח לרבקה מקדמה מחר ב-12:00 | parsed · deposit → no template → `manual_fallback` |
| 8  | שלח לאבי הסכם היום ב-16:30 | parsed · agreement → active template → `api_template` |
| 9  | תאם שיעור עם יוסי מחר ב-08:00 | parsed · teacher · lesson_coordination · `2026-06-16T08:00` |
| 10 | שלח לדנה סרטון מחר ב-19:00 | parsed · video · `2026-06-16T19:00` |
| 11 | שלח לדנה הודעה מחרתיים ב-11:00 | parsed · `2026-06-17T11:00` |
| 12* | תשלח לרבקה את ההסכם ל-29.6 | needs_clarification · event `2026-06-29`, no send time |
| 13* | תשלח לרבקה את ההסכם ל-29.6 מחר ב-10:00 | parsed · send `2026-06-16T10:00` · event `2026-06-29` |
| 14* | שלח לאבי מקדמה עד 29.6 | needs_clarification · event `2026-06-29`, no send time |
| 15* | שלח לאבי מקדמה עד 29.6, תשלח היום ב-15:00 | parsed · send `2026-06-15T15:00` · event `2026-06-29` |
| 16 | שלח לרבקה הודעה ב-25.6 בשעה 13:00 | parsed · send `2026-06-25T13:00` |
| 17 | שלח לאבי הסכם ב-30.6 | parsed · send `2026-06-30T10:00` (inferred 10:00) |
| 18 | שלח לדנה הודעה של 28.6 | needs_clarification · event `2026-06-28`, no send time |
| 19 | שלח ליוסי תיאום שיעור ב-18.6 | parsed · teacher · send `2026-06-18T10:00` (inferred) |
| 20 | שלח לדנה הודעה מחר | parsed · send **`2026-06-16T10:00`** (inferred 10:00) |
| 21* | שלח לדנה סרטון של 29.6 | needs_clarification · video · event `2026-06-29` |
| 22* | שלח לדנה סרטון ב-29.6 | parsed · video · send `2026-06-29T10:00` (inferred) |
| 23* | שלח ליוסי תיאום שיעור ל-20.6 ב-17.6 בשעה 09:00 | parsed · send `2026-06-17T09:00` · event `2026-06-20` |
| 24 | שלח לדנה agreement ב-26.6 at 14:00 | parsed (mixed he/en) · inside window → `api_freeform` |
| 25 | שלח תזכורת מחר ב-10:00 | needs_clarification · missing recipient |

`*` = must-pass.

## Notes

- Case 20 is the corrected expectation: relative day with **no** time defaults to
  **10:00**, i.e. `2026-06-16T10:00:00` (not 09:00).
- Cases 6/7/8/24 also assert the Stage-2 `SendPlan`, covering all four plans
  except the no-phone path, which is covered by dedicated resolver unit tests in
  `test_parsing.py`.
