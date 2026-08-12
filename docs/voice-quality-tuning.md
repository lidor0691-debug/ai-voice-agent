# Voice quality tuning (OpenAI Realtime path)

Hebrew phone-call quality is a calibration problem: every round costs a live
call, and the right value is found by listening, not by reasoning. So the
session-level levers are **environment variables** — tuning one is a Railway
variable change and a restart, not a code deploy.

**Every variable here is unset by default, and unset reproduces the previous
(M6) behavior byte-for-byte.** Turning something on is always an explicit act,
and rollback is always "remove the variable".

## Levers

| Variable | Default (unset) | Range / values | What it does |
|---|---|---|---|
| `OPENAI_REALTIME_TRANSCRIBE_MODEL` | `gpt-realtime-whisper` | any transcribe model on the account | Caller-side STT. This is the single highest-impact lever for Hebrew: mangled sentence heads and wrong names come from here, and they propagate into the lead email. |
| `OPENAI_TRANSCRIBE_PROMPT` | omitted | free text (Hebrew) | Context hint for the STT — what kind of call this is. |
| `OPENAI_TRANSCRIBE_KEYWORDS` | omitted | comma-separated Hebrew terms | Literal term biasing: the office name, the agent's name, product terms. The documented lever for mangled proper nouns. **Newer models only** (see below). |
| `OPENAI_TRANSCRIBE_DELAY` | omitted | `minimal`…`xhigh` | How much audio context the STT buffers before emitting text. Higher = better word error rate, more delay. **Newer models only.** |
| `OPENAI_INPUT_NOISE_REDUCTION` | omitted | `near_field` \| `far_field` | Input denoising. A handset/headset call is `near_field`; speakerphone is `far_field`. Anything else omits the field. |
| `OPENAI_VAD_TYPE` | `server_vad` | `server_vad` \| `semantic_vad` | How end-of-turn is decided. `semantic_vad` replaces the fixed silence timer with a model judgement — worth trying when callers get cut off mid-thought. |
| `OPENAI_VAD_EAGERNESS` | `medium` | `low` \| `medium` \| `high` \| `auto` | `semantic_vad` only. Lower = waits longer before deciding the caller finished. |
| `OPENAI_VAD_THRESHOLD` | `0.6` | `0.1`–`0.95` | `server_vad` only. Higher = less sensitive to noise, more likely to miss quiet speech. |
| `OPENAI_VAD_SILENCE_MS` | `700` | `200`–`2000` | `server_vad` only. Silence before the turn is considered over. **Lowering this is the most direct way to cut reply latency** — at the cost of cutting off callers who pause mid-sentence. |
| `OPENAI_VAD_PREFIX_MS` | `300` | `0`–`1000` | `server_vad` only. Audio kept from before speech onset. |
| `OPENAI_MAX_OUTPUT_TOKENS` | no cap | `64`–`4096` | Hard ceiling on one spoken reply. **A safety net, not a brevity tool** — hitting it stops the audio mid-sentence. Use the dialogue-discipline instruction for brevity and set this only high enough to stop a runaway monologue. |
| `OPENAI_DIALOGUE_STYLE_CLIENT_IDS` | empty (off) | comma-separated client ids | Appends turn-level dialogue discipline for those tenants: short replies, one question per turn, no repetition, the caller's correction wins, no racing to close. |

Invalid or out-of-range values are ignored with a `[OPENAI-CONFIG]` warning and
the default is used — a typo degrades, it never crashes the service.

## Which transcribe model supports what

Verified by live probe against `gpt-realtime-2.1` on this account:

| Model | `keywords` / `delay` | Notes |
|---|---|---|
| `gpt-live-transcribe` | ✅ | Streaming-oriented; accepts the full field set. |
| `gpt-transcribe` | ✅ | |
| `gpt-4o-transcribe` | ❌ **rejects `keywords`** | Legacy tier. |
| `gpt-4o-mini-transcribe`, `gpt-realtime-whisper`, `whisper-1` | ❌ assumed | `gpt-realtime-whisper` is the current default and is legacy tier. |

A rejected `session.update` kills the session, so **one bad variable pairing
would drop every call**. The code therefore refuses to send `keywords`/`delay`
to a model not on the verified-capable list and logs a `[OPENAI-CONFIG]`
warning instead. You cannot break calls by setting the wrong combination.

Also enforced: only the singular `language` field is ever sent. The API rejects
a session carrying both `language` and `languages`; the newer models normalise
the singular form themselves.

## Two things worth knowing before you tune

**The caller transcript is a side-channel.** In a speech-to-speech session the
model hears the audio directly — `input_audio_transcription` does not feed its
comprehension. So changing the STT model fixes the **lead email, the extraction
and the logs**, and it matters for us specifically because our valid-turn gate
reads that transcript (a garbled transcript can cause a real turn to be
rejected). It does **not** fix the model mishearing something and saying it out
loud. Those are two separate problems with two separate fixes.

**Sentence heads getting clipped is a `prefix_padding_ms` problem, not a
bandwidth problem.** Published measurements put the 8 kHz µ-law penalty at
roughly half a point of word error rate for Whisper-class models — small. Audio
cut off before the model ever sees it is the far larger effect, and that is
what `prefix_padding_ms` controls. Raise it before blaming the phone line.

## Existing related variables

`OPENAI_REALTIME_MODEL`, `OPENAI_REALTIME_VOICE`, `OPENAI_REALTIME_SPEED`
(delivery pace, `0.7`–`1.3`), `OPENAI_ONSET_*` (barge-in energy guard),
`OPENAI_ECHO_GUARD_*`, `OPENAI_WAITING_REPROMPT_SECONDS` /
`OPENAI_WAITING_CLOSE_SECONDS` (silence watchdog).

## How to tune

Change **one** variable per test call. Two changes at once and a bad call tells
you nothing.

Read the result from the logs rather than from memory of how it felt:

```bash
railway logs | grep OPENAI-DIAG
```

| Question | What to look at |
|---|---|
| Is she slow to answer? | `input_transcription` timestamp minus the preceding `speech_stopped`, then `first_outbound_audio`. The first gap is STT; the second is generation. |
| Is she cutting callers off? | `speech_stopped` segments that arrive close together — the caller was still mid-thought. Consider `semantic_vad` or a higher `OPENAI_VAD_SILENCE_MS`. |
| Is she ignoring interruptions? | `onset_guard_aborted` with a low `above` count = the caller spoke too quietly to pass the energy guard. |
| Is the transcript wrong? | Compare `input_transcription` text against what was actually said. This is the STT model's fault, not the state machine's. |
| Is she talking too long? | Time from `first_outbound_audio` to `response_completed`. |

## What is NOT tunable here

Turn-taking, barge-in, greeting protection, closing detection and the
post-call pipeline are code, deliberately. They are covered by tests and
changing them needs a PR.
