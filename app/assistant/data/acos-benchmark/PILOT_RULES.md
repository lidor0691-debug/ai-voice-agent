# ACOS Morning Brief v0.1 — Pilot Rules

Agent: FND + SLS Morning Brief. Production prompt: `prompts/acos_morning_brief_v0.1.txt`.
Baseline (frozen): ARM B 93% all-4, catastrophic 4/60, token ratio 1.87x (see `VERSION.txt`).

## 1. 7-Day Pilot Success Metrics

Judged by Lidor each morning (yes/no, ~60 sec):

| Metric | Target over 7 days |
|---|---|
| **Zero confabulation** (no invented leads/quotes/numbers/history) | **7/7 days** — any miss = pilot-blocking |
| Top A-task is genuinely the right revenue priority | ≥6/7 |
| Every prospect gets a correct stage + a **dated** NEXT_COMMITMENT | ≥6/7 |
| Ready-to-send messages usable **as-is or with trivial edit** | ≥70% of messages |
| `חסר` raised instead of guessing, whenever data was missing | 7/7 |
| Lidor actually acts on the top task | ≥5/7 |
| Brief scannable in ≤30 sec | 7/7 |

**Pilot passes if:** zero confabulation holds (7/7) AND ≥5 of the remaining rows hit target.

## 2. Daily Log Schema

Append one line per day to `pilot_log.jsonl`:

```json
{"date":"2026-07-04","input":"<paste>","output":"<paste>",
 "top_A_correct":true,"confabulation":false,"stage_errors":0,
 "commitments_dated":true,"msgs_used_as_is":3,"msgs_edited":1,
 "gaps_flagged_ok":true,"catastrophic":false,"acted_on_top":true,
 "note":"<what broke / what worked>"}
```

Minimum viable fields if rushed: `date`, `confabulation` (bool), `top_A_correct` (bool),
`catastrophic` (bool), `note`. That alone drives the change-decision in §3.

## 3. Rules for When ACOS Can Be Changed Again

1. **No vibes edits.** A change is allowed only for a failure that is **logged and repeats ≥2 of 7 days** (systematic), not a one-day flake.
2. **One variable at a time.** Change one clause (or the model, or `max_tokens`) — never two together. Prompt + model in the same edit is forbidden (it breaks attribution).
3. **Eval gate before re-freeze.** Any change must re-run the **frozen v0.1 eval** (`run_benchmark.py` → `judge_results.py` at `max_tokens=2048`) and show **no regression** vs the v0.1 baseline (ARM B ≥93% all-4, catastrophic ≤4/60) **and** that it fixes the logged failure. Then bump to `acos-v0.2` and re-freeze the artifact list in `VERSION.txt`.
4. **Catastrophic override.** A confabulation in production (invented lead/quote/number) is a same-day hotfix-eligible event — but the hotfix still must pass the eval gate before it replaces the frozen prompt; until then, flag the brief as "verify manually".
5. **Attribution discipline.** Cross-category deltas from a single-file prompt edit are noise unless causally traceable (a C-FND edit cannot regress C-SLS). Don't chase re-run variance.
6. **Record every change:** date, one-line rationale, the diff, before/after eval scores, new version tag.
