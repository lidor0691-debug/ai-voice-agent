"""Pure report formatting + serialization for eval results. DEV-ONLY.

In-memory results -> a human-readable string and a JSON-able dict. No I/O here
(callers print or write); no secrets are ever included.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .compare import CaseResult


def _fmt_value(v: Any) -> str:
    # Enum -> its value; everything else -> str. Keeps Hebrew/ISO readable.
    return str(getattr(v, "value", v))


def summarize(results: List[CaseResult]) -> Dict[str, Any]:
    must = [r for r in results if r.must_pass]
    must_failed = [r.case_id for r in must if not r.passed]
    passed = sum(1 for r in results if r.passed)
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "must_pass_total": len(must),
        "must_pass_passed": len(must) - len(must_failed),
        "must_pass_failed_ids": must_failed,
        "hard_fail": bool(must_failed),
    }


def to_dict(results: List[CaseResult], *, model: str, now_anchor: str, mode: str) -> Dict[str, Any]:
    """JSON-serializable result document (for an optional local artifact)."""
    return {
        "model": model,
        "now_anchor": now_anchor,
        "mode": mode,
        "summary": summarize(results),
        "cases": [
            {
                "id": r.case_id,
                "description": r.description,
                "must_pass": r.must_pass,
                "passed": r.passed,
                "diffs": [
                    {"field": d.field,
                     "expected": _fmt_value(d.expected),
                     "actual": _fmt_value(d.actual)}
                    for d in r.diffs
                ],
            }
            for r in results
        ],
    }


def format_report(results: List[CaseResult], *, model: str, now_anchor: str, mode: str) -> str:
    s = summarize(results)
    lines: List[str] = []
    lines.append("=" * 64)
    lines.append("Hebrew parser eval — Stage-1 ClaudeParser vs NLP oracle")
    lines.append("=" * 64)
    lines.append(f"mode:       {mode}")
    lines.append(f"model:      {model}")
    lines.append(f"now anchor: {now_anchor}")
    lines.append("-" * 64)
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        mp = "★" if r.must_pass else " "
        line = f"[{mark}] {mp} case {r.case_id:>2}  {r.description}"
        lines.append(line)
        if not r.passed:
            d = r.first_diff
            extra = f" (+{len(r.diffs) - 1} more)" if len(r.diffs) > 1 else ""
            lines.append(
                f"          ↳ {d.field}: expected {_fmt_value(d.expected)!r} "
                f"-> actual {_fmt_value(d.actual)!r}{extra}"
            )
    lines.append("-" * 64)
    lines.append(f"passed:    {s['passed']}/{s['total']}")
    lines.append(
        f"must-pass: {s['must_pass_passed']}/{s['must_pass_total']}"
        + (f"  FAILED ids: {s['must_pass_failed_ids']}" if s["must_pass_failed_ids"] else "")
    )
    lines.append("RESULT: " + ("HARD FAIL (must-pass case failed)" if s["hard_fail"]
                               else ("PASS" if s["failed"] == 0 else "SOFT FAIL (non-must-pass)")))
    lines.append("=" * 64)
    return "\n".join(lines)
