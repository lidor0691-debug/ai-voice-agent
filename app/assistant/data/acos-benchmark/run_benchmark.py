#!/usr/bin/env python3
"""ACOS Benchmark Runner v0.1
Runs each task through ARM A (bare) and ARM B (ACOS), 3 runs each, temperature 0.
Appends results to results.jsonl. Stops immediately on API errors.
Resume-safe: already-completed (task_id, arm, run_n) rows are skipped on restart.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

RUNS_PER_ARM = 3
TEMPERATURE = 0


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def die(msg: str) -> None:
    log(f"FATAL: {msg}")
    sys.exit(1)


def load_tasks(path: Path) -> list[dict]:
    if not path.exists():
        die(f"tasks file not found: {path}")
    tasks = []
    with path.open(encoding="utf-8") as f:
        for line_n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except json.JSONDecodeError as e:
                die(f"invalid JSON at {path}:{line_n}: {e}")
            for field in ("id", "cat", "input", "prompt"):
                if field not in t:
                    die(f"task at {path}:{line_n} missing required field '{field}'")
            tasks.append(t)
    if not tasks:
        die(f"no tasks found in {path}")
    log(f"loaded {len(tasks)} tasks from {path}")
    return tasks


def load_prompt(path: Path, label: str) -> str:
    if not path.exists():
        die(f"{label} prompt file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        die(f"{label} prompt file is empty: {path}")
    return text


def load_completed(out_path: Path) -> set[tuple]:
    """Return set of (task_id, arm, run_n) already present in results file."""
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
                    continue  # ignore malformed lines; they will be re-run
        if done:
            log(f"resume: {len(done)} completed runs found in {out_path}, will skip them")
    return done


def call_model(client: anthropic.Anthropic, model: str, system: str,
               user_content: str, max_tokens: int) -> dict:
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIError as e:
        die(f"Anthropic API error: {type(e).__name__}: {e}")
    text = "".join(b.text for b in resp.content if b.type == "text")
    return {
        "output_text": text,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="ACOS Benchmark Runner v0.1")
    p.add_argument("--tasks", default="benchmark_tasks.jsonl")
    p.add_argument("--bare", default="bare_prompt.txt")
    p.add_argument("--acos-dir", default="arm_b_prompts",
                   help="dir with per-category ARM B prompts: acos_<cat>.txt")
    p.add_argument("--model", required=True, help="e.g. claude-sonnet-4-6")
    p.add_argument("--out", default="results.jsonl")
    p.add_argument("--max-tokens", type=int, default=1024)
    args = p.parse_args()

    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        die("ANTHROPIC_API_KEY not set (put it in .env)")

    client = anthropic.Anthropic()
    tasks = load_tasks(Path(args.tasks))
    bare_prompt = load_prompt(Path(args.bare), "bare")
    # Fail fast: load every needed per-category ARM B prompt before any API call.
    acos_dir = Path(args.acos_dir)
    acos_prompts = {}
    for cat in sorted({t["cat"] for t in tasks}):
        acos_prompts[cat] = load_prompt(acos_dir / f"acos_{cat}.txt", f"ACOS {cat}")
    log(f"loaded ARM B prompts for categories: {', '.join(sorted(acos_prompts))}")
    out_path = Path(args.out)
    completed = load_completed(out_path)

    total = len(tasks) * 2 * RUNS_PER_ARM
    done_count = len(completed)

    with out_path.open("a", encoding="utf-8") as out_f:
        for task in tasks:
            user_content = f"{task['input']}\n\n{task['prompt']}"
            arms = {"A": bare_prompt, "B": acos_prompts[task["cat"]]}
            for arm, system_prompt in arms.items():
                for run_n in range(1, RUNS_PER_ARM + 1):
                    key = (task["id"], arm, run_n)
                    if key in completed:
                        continue
                    log(f"running {task['id']} arm={arm} run={run_n} "
                        f"({done_count + 1}/{total})")
                    result = call_model(client, args.model, system_prompt,
                                        user_content, args.max_tokens)
                    row = {
                        "task_id": task["id"],
                        "cat": task["cat"],
                        "arm": arm,
                        "run_n": run_n,
                        **result,
                    }
                    out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out_f.flush()
                    done_count += 1

    log(f"done. {done_count}/{total} runs in {out_path}")


if __name__ == "__main__":
    main()
