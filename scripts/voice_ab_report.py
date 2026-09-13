"""
A/B report: gpt-realtime-2.1 (production, [OPENAI-DIAG]) vs GPT-Live 1 POC
([LIVE-DIAG]) from Railway logs.

    railway logs > logs.txt
    python scripts/voice_ab_report.py logs.txt            # all calls
    python scripts/voice_ab_report.py logs.txt CAxxxx CAyyyy

Per call it reports the same metrics on both arms so they can be compared on
one line each:

  reply_ms      caller finished → Maya's first audio (median / max)
                  realtime: speech_stopped → first_outbound_audio
                  live:     last caller transcript fragment → first audio
                            (includes transcript lag; slightly pessimistic)
  turns         caller turns / assistant turns
  interrupts    realtime: onset_barge_cancel + CANCEL_AND_CLEAR
                live:     barge_flush
  missed_barge  realtime: onset_guard_aborted   live: n/a (model-owned)
  repeats       duplicate assistant sentences (needs assistant transcript;
                realtime logs have none → "n/a")
  non_hebrew    assistant turns with no Hebrew (live only — realtime logs
                carry no assistant text)
  closing       closing_hangup / closing_detected count
  exit          pump exit reason
  cost          live: usage_seconds × $0.05/60 (+ backend not included)
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict


def parse(path: str):
    calls = defaultdict(lambda: {"arm": None, "events": []})
    last_sid = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            # Production logs the pump exit as a plain line right before session_ended.
            if "[OPENAI-WS] Twilio pump exited — reason=" in line and last_sid:
                calls[last_sid]["events"].append(
                    {"event": "pump_exited", "call_sid": last_sid,
                     "reason": line.split("reason=", 1)[1].strip()})
                continue
            for tag, arm in (("[OPENAI-DIAG] ", "realtime"), ("[LIVE-DIAG] ", "live")):
                i = line.find(tag)
                if i >= 0:
                    try:
                        ev = json.loads(line[i + len(tag):])
                    except json.JSONDecodeError:
                        break
                    sid = ev.get("call_sid") or "?"
                    last_sid = sid
                    calls[sid]["arm"] = arm
                    calls[sid]["events"].append(ev)
                    break
    return calls


def _med(xs):
    return round(statistics.median(xs)) if xs else None


def realtime_metrics(evs):
    lat, last_stop = [], None
    caller = assistant = 0
    interrupts = missed = closing = 0
    exit_reason = ""
    for e in evs:
        k = e.get("event")
        if k == "speech_stopped":
            last_stop = e["t"]
        elif k == "input_transcription" and e.get("decision") == "accepted":
            caller += 1
        elif k == "first_outbound_audio" and last_stop is not None:
            lat.append(round((e["t"] - last_stop) * 1000)); last_stop = None
        elif k == "response_completed":
            assistant += 1
        elif k in ("onset_barge_cancel",):
            interrupts += 1
        elif k == "onset_guard_aborted":
            missed += 1
        elif k == "closing_hangup":
            closing += 1
        elif k == "pump_exited":
            exit_reason = e.get("reason", "")
        elif k == "session_ended":
            caller = e.get("caller_lines", caller); assistant = e.get("assistant_lines", assistant)
    return {"reply_ms_med": _med(lat), "reply_ms_max": max(lat) if lat else None,
            "turns": f"{caller}/{assistant}", "interrupts": interrupts, "missed_barge": missed,
            "repeats": "n/a", "non_hebrew": "n/a", "closing": closing, "exit": exit_reason, "cost_usd": "token-billed"}


def live_metrics(evs):
    lat = [e["ms"] for e in evs if e.get("event") == "reply_latency"]
    caller = assistant = 0
    flushes = closing = 0
    non_hebrew = "?"
    usage = None
    exit_reason = ""
    assistant_text = []
    for e in evs:
        k = e.get("event")
        if k == "assistant_transcript":
            assistant_text.append(e.get("delta", ""))
        elif k == "barge_flush":
            flushes += 1
        elif k in ("closing_detected",):
            closing += 1
        elif k == "session_ended":
            caller = e.get("caller_lines", 0); assistant = e.get("assistant_lines", 0)
            non_hebrew = e.get("assistant_non_hebrew_turns", "?")
            usage = e.get("live_usage_seconds"); exit_reason = e.get("exit_reason", "")
    text = "".join(assistant_text)
    sentences = [s.strip() for s in text.replace("?", ".").split(".") if len(s.strip()) > 12]
    repeats = len(sentences) - len(set(sentences))
    cost = round(usage * 0.05 / 60, 4) if usage else None
    return {"reply_ms_med": _med(lat), "reply_ms_max": max(lat) if lat else None,
            "turns": f"{caller}/{assistant}", "interrupts": flushes, "missed_barge": "n/a",
            "repeats": repeats, "non_hebrew": non_hebrew, "closing": closing, "exit": exit_reason,
            "cost_usd": cost}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    calls = parse(sys.argv[1])
    only = set(sys.argv[2:])
    rows = []
    for sid, c in calls.items():
        if only and sid not in only:
            continue
        m = realtime_metrics(c["events"]) if c["arm"] == "realtime" else live_metrics(c["events"])
        rows.append((c["arm"], sid, m))
    cols = ["reply_ms_med", "reply_ms_max", "turns", "interrupts", "missed_barge", "repeats",
            "non_hebrew", "closing", "exit", "cost_usd"]
    print(f"{'arm':<9}{'call_sid':<36}" + "".join(f"{c:<14}" for c in cols))
    for arm, sid, m in sorted(rows, key=lambda r: r[0]):
        print(f"{arm:<9}{sid:<36}" + "".join(f"{str(m.get(c)):<14}" for c in cols))


if __name__ == "__main__":
    main()
