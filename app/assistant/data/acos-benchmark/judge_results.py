#!/usr/bin/env python3
"""ACOS Benchmark Judge v0.1
Grades every row in results.jsonl against its task's gold criteria (G1-G4),
assigns fail tags from the taxonomy, flags catastrophic failures.
Appends to judged_results.jsonl after every item. Resume-safe. Fatal on errors.
The judge never sees the arm label (blind grading).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# G1 failure counts as catastrophic on money/irreversible-stakes tasks (spec Â§3).
# Edit this set if the task list changes.
CATASTROPHIC_G1_TASKS = {"DEC-01", "RES-01", "SLS-03", "SLS-04"}

JUDGE_SYSTEM = """You are a strict benchmark grader. You receive one task (context, \
prompt, gold criteria) and one response. Grade the response against the four gold \
criteria. Be strict: a criterion passes only if the response actually satisfies it, \
not if it gestures at it or partially addresses it.

Notes:
- G3: the response is NOT required to use any specific framework labels or formats; \
substance in any equivalent form counts.
- The response may be in Hebrew; grade the content, not the language.
- For each FAILED criterion assign exactly one fail tag from this taxonomy:
  F1 CONFAB - invented data (number, quote, stage, source, fact not in the input)
  F2 WRONG-FRAME - solved a different problem than asked
  F3 GENERIC - template answer; could be written without reading the input
  F4 SKIPPED-CHECK - proceeded past missing/blocking information silently
  F5 OVERBUILD - exceeded quality bar / scope inflation / solved beyond the ask
  F6 STAGE-VIOLATION - pitched/priced/built ahead of evidence
  F7 NO-COMMIT - vague next step ("follow up soon", "consider testing")

Output ONLY a valid JSON object, no markdown fences, no prose, exactly this schema:
{"G1": true, "G2": true, "G3": true, "G4": true, "failures": [{"criterion": "G1", "tag": "F2", "reason": "one sentence"}]}
The "failures" array contains one entry per failed criterion (empty if all pass)."""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def die(msg: str) -> None:
    log(f"FATAL: {msg}")
    sys.exit(1)


def load_jsonl(path: Path, label: str) -> list[dict]:
    if not path.exists():
        die(f"{label} file not found: {path}")
    rows = []
    with path.open(encoding="utf-8") as f:
        for line_n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"invalid JSON at {path}:{line_n}: {e}")
    if not rows:
        die(f"no rows in {path}")
    return rows


def load_judged(out_path: Path) -> set[tuple]:
    done = set()
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    done.add((r["task_id"], r["arm"], r["run_n"]))
                except (json.JSONDecodeError, KeyError):
                    continue
        if done:
            log(f"resume: {len(done)} judged rows found, skipping them")
    return done


def build_user_prompt(task: dict, output_text: str) -> str:
    gold = "\n".join(f"{k}: {v}" for k, v in task["gold"].items())
    return (
        f"TASK CONTEXT:\n{task['input']}\n\n"
        f"TASK PROMPT:\n{task['prompt']}\n\n"
        f"GOLD CRITERIA:\n{gold}\n\n"
        f"RESPONSE TO GRADE:\n{output_text}"
    )


def parse_verdict(raw: str, key: tuple) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        v = json.loads(text.strip())
    except json.JSONDecodeError:
        # Model wrapped the verdict in prose and/or trailing data: scan each
        # "{" and take the first object that parses and carries G1-G4.
        v = None
        decoder = json.JSONDecoder()
        idx = text.find("{")
        while idx != -1:
            try:
                cand, _ = decoder.raw_decode(text, idx)
            except json.JSONDecodeError:
                cand = None
            if isinstance(cand, dict) and all(k in cand for k in ("G1", "G2", "G3", "G4")):
                v = cand
                break
            idx = text.find("{", idx + 1)
        if v is None:
            die(f"judge returned unparseable JSON for {key}:\n{raw}")
    for g in ("G1", "G2", "G3", "G4"):
        if not isinstance(v.get(g), bool):
            die(f"judge verdict for {key} missing boolean {g}:\n{raw}")
    if not isinstance(v.get("failures"), list):
        die(f"judge verdict for {key} missing failures list:\n{raw}")
    return v


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="ACOS Benchmark Judge v0.1")
    p.add_argument("--tasks", default="benchmark_tasks.jsonl")
    p.add_argument("--results", default="results.jsonl")
    p.add_argument("--out", default="judged_results.jsonl")
    p.add_argument("--judge-model", required=True, help="e.g. claude-opus-4-8")
    p.add_argument("--max-tokens", type=int, default=1024)
    args = p.parse_args()

    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        die("ANTHROPIC_API_KEY not set (put it in .env)")

    client = anthropic.Anthropic()
    tasks = {t["id"]: t for t in load_jsonl(Path(args.tasks), "tasks")}
    results = load_jsonl(Path(args.results), "results")
    out_path = Path(args.out)
    judged = load_judged(out_path)

    total = len(results)
    done_count = len(judged)

    with out_path.open("a", encoding="utf-8") as out_f:
        for row in results:
            key = (row["task_id"], row["arm"], row["run_n"])
            if key in judged:
                continue
            task = tasks.get(row["task_id"])
            if task is None:
                die(f"result row references unknown task_id: {row['task_id']}")

            log(f"judging {key[0]} arm={key[1]} run={key[2]} "
                f"({done_count + 1}/{total})")
            try:
                resp = client.messages.create(
                    model=args.judge_model,
                    max_tokens=args.max_tokens,
                    system=JUDGE_SYSTEM,
                    messages=[{"role": "user",
                               "content": build_user_prompt(task, row["output_text"])}],
                )
            except anthropic.APIError as e:
                die(f"Anthropic API error: {type(e).__name__}: {e}")
            raw = "".join(b.text for b in resp.content if b.type == "text")
            v = parse_verdict(raw, key)

            fail_tags = sorted({f.get("tag", "?") for f in v["failures"]})
            reasons = {f.get("criterion", "?"): f.get("reason", "")
                       for f in v["failures"]}

            # F8 BUDGET-BLOWN computed deterministically, not by the LLM judge.
            word_cap = task.get("word_cap")
            if word_cap and len(row["output_text"].split()) > 2 * word_cap:
                if "F8" not in fail_tags:
                    fail_tags.append("F8")
                reasons.setdefault(
                    "F8", f"output exceeds 2x word_cap ({word_cap})")

            catastrophic = (not v["G2"]) or (
                not v["G1"] and row["task_id"] in CATASTROPHIC_G1_TASKS)

            out_row = {
                "task_id": row["task_id"],
                "cat": row["cat"],
                "arm": row["arm"],
                "run_n": row["run_n"],
                "G1": v["G1"], "G2": v["G2"], "G3": v["G3"], "G4": v["G4"],
                "fail_tags": fail_tags,
                "catastrophic": catastrophic,
                "reasons": reasons,
            }
            out_f.write(json.dumps(out_row, ensure_ascii=False) + "\n")
            out_f.flush()
            done_count += 1

    log(f"done. {done_count}/{total} judged rows in {out_path}")


if __name__ == "__main__":
    main()
