"""
Runs `claude -p "<prompt>"` as a subprocess and parses the output for
special signals (APPROVAL_REQUIRED, TASK_COMPLETE, GUIDANCE_NEEDED).
"""
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
    context = build_context()
    full_prompt = f"{context}\n{command}"

    logger.info("Running claude -p for command: %r", command[:80])

    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--allowedTools", "all"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,  # 30 min max per task
            env=_env_with_api_key(),
        )
        output = result.stdout + result.stderr
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
    import os
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
    return env


def _parse_output(output: str) -> ExecutionResult:
    approval_required = None
    task_complete = None
    guidance_needed = None

    for line in output.splitlines():
        if line.startswith("APPROVAL_REQUIRED:"):
            approval_required = line[len("APPROVAL_REQUIRED:"):].strip()
        elif line.startswith("TASK_COMPLETE:"):
            task_complete = line[len("TASK_COMPLETE:"):].strip()
        elif line.startswith("GUIDANCE_NEEDED:"):
            # Collect everything from here
            idx = output.find("GUIDANCE_NEEDED:")
            guidance_needed = output[idx + len("GUIDANCE_NEEDED:"):].strip()
            break

    return ExecutionResult(
        raw_output=output,
        approval_required=approval_required,
        task_complete=task_complete,
        guidance_needed=guidance_needed,
        error=None,
    )
