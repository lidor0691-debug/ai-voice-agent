"""Opt-in live Claude eval runner. DEV-ONLY.

Run manually from the repo root:

    ASSISTANT_RUN_LIVE_EVAL=1 ANTHROPIC_API_KEY=... \
        python -m tools.assistant_eval.run_eval [--model M] [--only 1,12,13] [--out NAME]

SAFETY: this never calls Claude unless BOTH gates pass:
  * env ``ASSISTANT_RUN_LIVE_EVAL=1``
  * env ``ANTHROPIC_API_KEY`` present
With the gates unset, it prints the pre-flight summary and the blockers, makes
no network call, and constructs no Anthropic client.

The evaluation loop (``evaluate_cases``) is parser-agnostic and import-clean,
so the tests drive it with a fake parser — no network, no key.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .compare import CaseResult, compare_case
from .dataset import anchored_now, select_cases
from .report import format_report, to_dict

RUN_FLAG = "ASSISTANT_RUN_LIVE_EVAL"
KEY_ENV = "ANTHROPIC_API_KEY"

# Local artifacts live under a gitignored directory; never committed.
RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ── safety gates ──────────────────────────────────────────────────────────────

def gate_blockers() -> List[str]:
    """Return human-readable reasons a live run is blocked (empty == allowed).

    Never echoes the key value — only whether it is present.
    """
    blockers: List[str] = []
    if os.getenv(RUN_FLAG) != "1":
        blockers.append(f"{RUN_FLAG} is not set to '1' (live eval disabled).")
    if not os.getenv(KEY_ENV):
        blockers.append(f"{KEY_ENV} is not set (no API key available).")
    return blockers


def live_allowed() -> bool:
    return not gate_blockers()


# ── parser-agnostic evaluation (network-free; tests drive this) ───────────────

async def evaluate_cases(parser: Any, cases: List[Any], *, now: Any) -> List[CaseResult]:
    """Run every case through ``parser`` and compare against its expectation.

    ``parser.parse`` may be sync or async (ParserProtocol allows both); an
    awaitable result is awaited. No DB, no network of our own — the only
    external effect is whatever ``parser`` itself does.
    """
    results: List[CaseResult] = []
    for case in cases:
        intent = parser.parse(case.text, now=now)
        if inspect.isawaitable(intent):
            intent = await intent
        results.append(compare_case(case, intent))
    return results


# ── live runner ───────────────────────────────────────────────────────────────

def _resolve_model(cli_model: Optional[str]) -> str:
    if cli_model:
        return cli_model
    # Defer to ClaudeParser's own resolution (env ASSISTANT_PARSER_MODEL,
    # else DEFAULT_MODEL = claude-sonnet-4-6). Imported lazily.
    from app.assistant.core.llm_parser import DEFAULT_MODEL

    return os.getenv("ASSISTANT_PARSER_MODEL", DEFAULT_MODEL)


def _write_results(doc: dict, out: str) -> Path:
    path = Path(out)
    if not path.is_absolute() and path.parent == Path("."):
        # A bare name lands in the gitignored results dir.
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / path
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix != ".json":
        path = path.with_suffix(".json")
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run(
    *,
    model: Optional[str] = None,
    only: Optional[List[int]] = None,
    out: Optional[str] = None,
    do_print: bool = True,
) -> Tuple[int, Optional[dict]]:
    """Entry point. Returns (exit_code, result_doc_or_None).

    exit codes: 0 ok/blocked-cleanly, 1 soft fail, 2 hard fail (must-pass).
    """
    cases = select_cases(only)
    resolved_model = _resolve_model(model)
    anchor = anchored_now().strftime("%Y-%m-%dT%H:%M:%S %Z")

    # Pre-flight: always state the spend BEFORE any client is built.
    print(
        f"[eval] About to run {len(cases)} live Claude call(s) "
        f"(model={resolved_model}, now={anchor})."
    )

    blockers = gate_blockers()
    if blockers:
        print("[eval] LIVE EVAL BLOCKED — no Anthropic call made:")
        for b in blockers:
            print(f"        - {b}")
        print(f"[eval] To run: set {RUN_FLAG}=1 and {KEY_ENV}, then re-run.")
        return 0, None

    # Gates passed — construct the real parser lazily (only now).
    from app.assistant.core.llm_parser import ClaudeParser

    parser = ClaudeParser(model=resolved_model)
    results = asyncio.run(evaluate_cases(parser, cases, now=anchored_now()))

    doc = to_dict(results, model=resolved_model, now_anchor=anchor, mode="live")
    if do_print:
        print(format_report(results, model=resolved_model, now_anchor=anchor, mode="live"))
    if out:
        written = _write_results(doc, out)
        print(f"[eval] results written to {written}")

    return (2 if doc["summary"]["hard_fail"] else (1 if doc["summary"]["failed"] else 0)), doc


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tools.assistant_eval.run_eval",
        description="Opt-in live Claude eval against the Hebrew NLP oracle.",
    )
    p.add_argument("--model", default=None, help="Override model (else env / default).")
    p.add_argument("--only", default=None,
                   help="Comma-separated case ids to run (e.g. 1,12,13).")
    p.add_argument("--out", default=None,
                   help="Write JSON results (bare name -> gitignored results/ dir).")
    p.add_argument("--no-print", dest="do_print", action="store_false",
                   help="Suppress the human-readable report on stdout.")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    only = [int(x) for x in args.only.split(",") if x.strip()] if args.only else None
    code, _ = run(model=args.model, only=only, out=args.out, do_print=args.do_print)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
