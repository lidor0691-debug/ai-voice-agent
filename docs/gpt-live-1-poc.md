# GPT-Live 1 POC — isolated experiment vs the production `gpt-realtime-2.1` path

Status: **experiment, gated OFF, not on any production number.** Branch
`feat/gpt-live-1-poc`. Nothing in Roi's live path changes.

## 1. What GPT-Live 1 is (verified on this account, 2026-09-13)

| | Realtime API (production) | Live API / `gpt-live-1` (POC) |
|---|---|---|
| Endpoint | `wss://api.openai.com/v1/realtime?model=…` | `wss://api.openai.com/v1/live/sessions` (model in the first message) |
| First message | `session.update` (after `session.created`) | `session.start` → wait for `session.started` |
| Audio | `audio.input.format` / `audio.output.format` separately; `audio/pcmu` | ONE `audio.format` for both directions; **`audio/pcmu` 8 kHz accepted and echoed** → Twilio passthrough, no transcoding |
| Turn-taking | Client-owned: `server_vad`/`semantic_vad`, `create_response:false`, `interrupt_response:false`, app sends `response.create` | **Model-owned, full duplex.** No `turn_detection` (probe: `unknown_parameter`), no `response.create` for voice turns, no `response.cancel`, no `speech_started/stopped`, no `output_audio.done`, no `truncate` |
| Barge-in | App decides (onset energy guard, valid-turn gate, `response.cancel` + Twilio `clear`) | Model stops on its own; **client must still flush Twilio's buffer** (API gives no event for it) |
| Backchannels | None (would be a "response") | Native ("אהמ", "כן"), steered by prompt |
| Caller transcript | Configurable (`gpt-4o-transcribe`, `language`, `prompt`, `keywords`) | Built-in, **not configurable**, fragments by cadence (`session.input_transcript.delta`) |
| Assistant transcript | `response.output_audio_transcript.done` per response | `session.output_transcript.delta`, no turn boundary |
| Prompt | One long system prompt | **Short voice prompt** (`session.instructions`) + **backend prompt** (`delegation.responses.instructions`) |
| Reasoning / business rules | Same model, same prompt | Delegated to a backend model (`gpt-5.6-luna` / `gpt-5.6-terra`) while the voice keeps talking |
| Tools | On the voice model | Backend only |
| Ending | App detects closing phrase → `response.done` → REST hangup | App detects closing phrase → `session.close` → `session.closed` → REST hangup. No model-initiated hangup |
| Cost | Audio tokens: $32 in / $64 out per 1M (+$0.40 cached) | **$0.05/min flat, per second**, + backend tokens (luna $0.20/$1.20 per 1M in/out) |
| Session cap | — | `expires_at` in `session.started`; 128k context with auto-summarization |

## 2. Access

`gpt-live-1` is listed on the project key (`/v1/models`). Three probe sessions
opened, spoke Hebrew, and closed cleanly (`usage.seconds` billed). A
Realtime-style field (`turn_detection`) was rejected with `unknown_parameter`,
confirming strict config.

## 3. Architecture of the POC

```
Twilio ── µ-law 8k ──► /voice-ai/stream-live ──► wss://api.openai.com/v1/live/sessions
   ▲                        │                                    │
   │   media / clear        │ session.input_audio.append         │ delegation (responses)
   └────────────────────────┤ session.output_audio.delta         ▼
                            │                              gpt-5.6-luna (backend prompt)
                            ▼
              transcript ► extraction ► name status ► summary ► lead upsert
                        ► customer history ► Make webhook (source=voice_live) ► REST hangup
```

Files: `app/routes/voice_live_poc.py` (route + bridge + pure helpers),
`tests/test_voice_live_poc.py`, `scripts/live_scenario_harness.py`,
`scripts/voice_ab_report.py`. One additive line in `main.py`.

### Gates (both closed by default)

| Variable | Default | Effect |
|---|---|---|
| `LIVE_POC_ENABLED` | unset (off) | Endpoints refuse everything |
| `LIVE_POC_ALLOWED_TO_NUMBERS` | empty | Even with the flag on, only listed E.164 numbers are served. **Roi's number is refused unless explicitly listed.** |

Rollback: remove the two variables. Nothing else to undo.

### Tuning

| Variable | Default |
|---|---|
| `LIVE_POC_MODEL` | `gpt-live-1` |
| `LIVE_POC_VOICE` | `marin` |
| `LIVE_POC_DELEGATION` | `responses` (`client` = voice model only, no backend — the A/B control) |
| `LIVE_POC_BACKEND_MODEL` | `gpt-5.6-luna` |
| `LIVE_POC_BACKEND_REASONING` | `low` |
| `LIVE_POC_BACKEND_INCLUDE_TENANT_PROMPT` | `true` — Roi's Supabase prompt is appended to the backend prompt as "כללי המשרד" |
| `LIVE_POC_IDLE_HANGUP_SECONDS` | `30` |
| `LIVE_POC_CLOSING_GRACE_SECONDS` | `2.0` |
| `LIVE_POC_CLOSING_CALLER_QUIET_SECONDS` | `2.5` — no hangup on a closing phrase if the caller spoke this recently |
| `LIVE_POC_FLUSH_GRACE_SECONDS` | `0.25` — wait this long after caller speech for the model to keep talking before flushing Twilio |

## 4. Which production mechanisms survive

| Mechanism (production) | POC | Why |
|---|---|---|
| Two-stage greeting (Stage-1 "הלו?", Stage-2 fallback timer, greeting protection) | **Dropped**. One scripted opening line via `session.instructions.append` | The model owns the opening exchange; the probe showed it speaks the exact line |
| `TurnController` state machine, valid-turn gate, `response.create` accounting, playback marks | **Dropped** | Nothing to attach to — the API has no turn events and no client-side response creation |
| Onset energy guard (barge-in confirmation) | **Dropped** | Model decides to yield; the guard would fight it |
| Echo guard (shadow) | **Dropped** | Server-side transcript is not our gate any more; revisit only if echo pollutes the lead email |
| Silence re-prompt state machine (50s → check-in → 40s → close) | **Replaced** by a simple idle watchdog (30s) | The model can re-prompt itself; watchdog only prevents zombie sessions |
| Closing-phrase detection + grace + REST hangup | **Kept**, plus a **caller-quiet guard** | No model-initiated hangup exists. The guard fixes the "hangup mid-objection" incident |
| Twilio `clear` on barge-in | **Kept** as a playback clock + grace | The API stops emitting but cannot recall audio Twilio already buffered |
| Dead-socket detector, heartbeat marks | **Dropped for the POC** (add before pilot) | Transport hardening, orthogonal to the model |
| Post-call: extraction, name status, summary, RTL transcript HTML, lead upsert, history, webhook | **Kept verbatim** (same helpers, same payload shape, `source: "voice_live"`) | The Make scenario and the email do not change |
| Fail-closed agent resolution via Twilio `<Parameter>` | **Kept** | |
| Hebrew language pin + speech anchor | **Kept in spirit**: the voice prompt pins Hebrew; the greeting append says "בעברית" | The Sept-2 English incident must not recur |

**Conflicts to avoid:** anything that tries to decide *when* the model may
speak (gating, cancelling, re-issuing responses) will fight the model's own
turn-taking. Mute (`session.input_audio.mute`) and corrective
`session.instructions.append` are the only server-side levers.

## 5. Prompts

- **Voice prompt** (`build_voice_instructions`): identity, Hebrew-only pin,
  one-or-two-sentence turns, no filler before answers, name confirm/correct,
  backchannel + interruption policy, delegation policy, close once. ~1,400
  chars. Contains **no** insurance business rules.
- **Backend prompt** (`build_backend_instructions`): "you are Maya's backend,
  return one or two spoken-ready Hebrew sentences", what to collect, corrections
  win, denied topics don't exist, no invention, then Roi's Supabase prompt
  appended as **כללי המשרד**.

## 6. Hebrew scenario matrix (executable)

`scripts/live_scenario_harness.py` synthesises Hebrew caller speech with
`gpt-4o-mini-tts`, converts it to the exact µ-law 8 kHz stream Twilio would
send, and drives a real `gpt-live-1` session through each scenario with the
POC's own `session.start` and prompts. No Twilio, no phone, no production.

| ID | Scenario | Measured |
|---|---|---|
| S1 | "הלו" during the greeting | did she stop / continue; reply |
| S2 | interrupt mid-sentence | ms of audio after the interruption started |
| S3 | quiet speech (gain 0.2) | replied? transcript? latency |
| S4 | "לא שרון, לידור" | reply mentions לידור, not שרון |
| S5 | "תוך כמה זמן רועי חוזר אליי?" | reply does not open with "בסדר גמור"/"אוקיי"/"סבבה" |
| S6 | topic change (רכב → משכנתא) | reply follows the new topic |
| S7 | 15s silence | extra turns, no close |
| S8 | unclear audio (noise) | no English, no invented request |
| S9 | English sentence from the caller | reply is Hebrew |
| S10 | "לא, תודה רבה, זה הכל" | exactly one closing phrase, no repeated script |
| S11 | objection right after the closing phrase | she answers; POC close-decision is False during the objection |

Results: see §8.

## 7. First live A/B call — exact procedure

Precondition: PR merged, deploy SUCCESS, `/health` 200. Roi's number untouched.

1. Use a **test Twilio number** (not `+972533470757`). Set its Voice webhook to
   `https://ai-voice-agent-production-0a55.up.railway.app/voice-ai/voice-live`.
   Make sure the number has an `agents_config` row (it can point at Roi's
   agent config for identical prompts).
2. Railway: `LIVE_POC_ENABLED=true`,
   `LIVE_POC_ALLOWED_TO_NUMBERS=<test number E.164>`. Redeploy happens
   automatically.
3. Call the test number. Then call Roi's production number. Same script both
   times, in this order: say "הלו" over the greeting → give the reason → give
   a wrong name and correct it → ask "תוך כמה זמן רועי חוזר אליי?" → change
   the topic → interrupt her mid-sentence → say "לא, תודה רבה" → object
   immediately after she says goodbye.
4. `railway logs > logs.txt` then `python scripts/voice_ab_report.py logs.txt`
   — one row per call, same columns for both arms.
5. Compare the two lead emails in Roi's inbox side by side.
6. Rollback: unset the two variables (or repoint the test number).

## 8. Results

_Filled from `scripts/live_scenario_results.json` — see the PR description._
