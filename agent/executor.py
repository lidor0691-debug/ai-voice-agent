# agent/executor.py
"""
Runs `claude -p "<prompt>"` as a subprocess and parses the output for
special signals (APPROVAL_REQUIRED, TASK_COMPLETE, GUIDANCE_NEEDED).
"""
import os
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

from agent.config import PROJECT_ROOT, ANTHROPIC_API_KEY
from agent.context import build_context

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    raw_output: str
    approval_required: Optional[str]   # summary string if approval needed, else None
    task_complete: Optional[str]        # summary string if done, else None
    guidance_needed: Optional[str]      # instructions string if owner needed, else None
    error: Optional[str]               # error message if execution failed


def run_task(command: str) -> ExecutionResult:
    """Run a dev task via Claude Code CLI and return the parsed result."""
    try:
        context = build_context()
    except Exception as exc:
        return ExecutionResult(
            raw_output="",
            approval_required=None,
            task_complete=None,
            guidance_needed=None,
            error=f"Failed to build context: {exc}",
        )

    full_prompt = f"{context}\n\n{command}"

    logger.info("Running claude -p for command: %r", command[:80])

    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--allowedTools", "all"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout preserving order
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,  # 30 min max per task
            env=_env_with_api_key(),
        )
        output = result.stdout or ""
        if result.returncode != 0:
            logger.warning("claude exited with code %d", result.returncode)
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            raw_output="",
            approval_required=None,
            task_complete=None,
            guidance_needed=None,
            error="Task timed out after 30 minutes",
        )
    except FileNotFoundError:
        return ExecutionResult(
            raw_output="",
            approval_required=None,
            task_complete=None,
            guidance_needed=None,
            error="Claude CLI not found. Is 'claude' in PATH?",
        )

    return _parse_output(output)


def _env_with_api_key() -> dict:
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
    return env


def _parse_output(output: str) -> ExecutionResult:
    """
    Scan output for special signal lines. First-wins for all three signals.
    GUIDANCE_NEEDED collects all content from its line to end of output.
    """
    approval_required = None
    task_complete = None
    guidance_needed = None

    lines = output.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("APPROVAL_REQUIRED:") and approval_required is None:
            approval_required = stripped[len("APPROVAL_REQUIRED:"):].strip()
        elif stripped.startswith("TASK_COMPLETE:") and task_complete is None:
            task_complete = stripped[len("TASK_COMPLETE:"):].strip()
        elif stripped.startswith("GUIDANCE_NEEDED:") and guidance_needed is None:
            # Collect first line + all remaining lines as the guidance body
            first_line = stripped[len("GUIDANCE_NEEDED:"):].strip()
            rest = "\n".join(lines[i + 1:]).strip()
            guidance_needed = f"{first_line}\n{rest}".strip() if rest else first_line
            break  # GUIDANCE_NEEDED is terminal — stop parsing

    return ExecutionResult(
        raw_output=output,
        approval_required=approval_required,
        task_complete=task_complete,
        guidance_needed=guidance_needed,
        error=None,
    )
