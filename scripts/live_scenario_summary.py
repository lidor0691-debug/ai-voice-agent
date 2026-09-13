"""Side-by-side summary of live_scenario_results_<mode>.json files.

    python scripts/live_scenario_summary.py            # responses vs client
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"


def load(mode: str):
    p = ROOT / f"live_scenario_results_{mode}.json"
    return {r["scenario"]: r for r in json.loads(p.read_text(encoding="utf-8"))} if p.exists() else {}


def lat(r):
    """(audio_ms, transcript_ms) for the LAST labelled caller turn of the scenario."""
    by = r.get("reply_ms_by_turn") or {}
    if not by:
        return (None, None)
    last = list(by.values())[-1]
    return (last.get("audio"), last.get("transcript"))


def verdict(sid, r):
    if "exception" in r:
        return "EXC"
    if sid == "S1":
        return "ok" if r.get("non_hebrew_assistant_turns", 0) == 0 else "FAIL"
    if sid == "S2":
        s = r.get("stop_after_ms")
        return "ok" if s is not None and s <= 1200 else f"FAIL({s}ms)"
    if sid == "S3":
        return "ok" if r.get("maya_replied") and "רועי" in (r.get("caller_transcribed") or "") else "FAIL"
    if sid == "S4":
        return "ok" if r.get("says_lidor") and not r.get("still_says_sharon") else "FAIL"
    if sid == "S5":
        return "ok" if not r.get("opens_with_filler") else "FAIL"
    if sid == "S6":
        return "ok" if r.get("mentions_mortgage") and not r.get("still_on_car") else "FAIL"
    if sid == "S7":
        return "ok" if not r.get("closed") and r.get("extra_assistant_turns_in_15s_silence", 0) <= 1 else "FAIL"
    if sid == "S8":
        return "ok" if not r.get("non_hebrew") else "FAIL"
    if sid == "S9":
        return "ok" if r.get("reply_is_hebrew") and not r.get("reply_has_latin") else "FAIL"
    if sid == "S10":
        return "ok" if r.get("closing_phrases_total", 0) <= 1 and r.get("repeated_sentences", 0) == 0 else "FAIL"
    if sid == "S11":
        return "ok" if r.get("maya_replied_after_objection") and not r.get("poc_would_have_hung_up_during_objection") else "FAIL"
    return "?"


def main():
    modes = sys.argv[1:] or ["responses", "client"]
    data = {m: load(m) for m in modes}
    sids = sorted({s for d in data.values() for s in d}, key=lambda s: int(s[1:]))
    print(f"{'':5}{'scenario':<34}" + "".join(f"{m:<30}" for m in modes))
    print(f"{'':5}{'':<34}" + "".join(f"{'verdict  audio/transcr ms  deleg':<30}" for _ in modes))
    for sid in sids:
        row = f"{sid:<5}"
        title = next((d[sid]["title"] for d in data.values() if sid in d), "")
        row += f"{title:<34}"
        for m in modes:
            r = data[m].get(sid)
            if not r:
                row += f"{'-':<30}"; continue
            a, t = lat(r)
            row += f"{verdict(sid, r):<9}{str(a):>5}/{str(t):<6}   d={r.get('delegations')}   "
        print(row)
    for m in modes:
        rs = data[m]
        audio = [lat(r)[0] for r in rs.values() if lat(r)[0] is not None]
        tr = [lat(r)[1] for r in rs.values() if lat(r)[1] is not None]
        nh = sum(r.get("non_hebrew_assistant_turns", 0) for r in rs.values())
        secs = sum(r.get("session_seconds") or 0 for r in rs.values())
        print(f"\n[{m}] reply latency median audio={statistics.median(audio) if audio else None}ms "
              f"transcript={statistics.median(tr) if tr else None}ms | non-Hebrew turns={nh} | "
              f"session-seconds={secs:.0f} (≈${secs*0.05/60:.2f} voice)")


if __name__ == "__main__":
    main()
