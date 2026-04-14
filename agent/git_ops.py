import subprocess
import logging
from typing import List, Dict

from agent.config import PROJECT_ROOT, AGENT_BRANCH

logger = logging.getLogger(__name__)


def _git(*args: str) -> str:
    """Run a git command in the project root and return stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def get_current_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD")


def get_recent_commits(n: int = 5) -> List[Dict[str, str]]:
    log = _git("log", f"-{n}", "--pretty=format:%h|%s")
    commits = []
    for line in log.splitlines():
        if "|" in line:
            hash_, msg = line.split("|", 1)
            commits.append({"hash": hash_, "message": msg})
    return commits


def get_diff_summary(base: str = "main", head: str = AGENT_BRANCH) -> str:
    """Return a human-readable summary of changes between base and head."""
    try:
        stat = _git("diff", "--stat", f"{base}...{head}")
        diff = _git("diff", "--unified=3", f"{base}...{head}")
        # Cap diff at 3000 chars to keep WhatsApp message reasonable
        if len(diff) > 3000:
            diff = diff[:3000] + "\n... [diff truncated, see git log for full changes]"
        return f"=== Changed files ===\n{stat}\n\n=== Diff ===\n{diff}"
    except RuntimeError as e:
        return f"Could not compute diff: {e}"


def prepare_agent_branch() -> None:
    """Reset agent/work branch from current main. Called before each task."""
    try:
        current = get_current_branch()
        if current != "main":
            _git("checkout", "main")
        _git("pull", "origin", "main")
        # Force-reset agent/work to main
        try:
            _git("branch", "-D", AGENT_BRANCH)
        except RuntimeError:
            pass  # branch didn't exist yet
        _git("checkout", "-b", AGENT_BRANCH)
        logger.info("Agent branch '%s' ready", AGENT_BRANCH)
    except RuntimeError as e:
        logger.error("Failed to prepare agent branch: %s", e)
        raise


def merge_to_main() -> None:
    """Merge agent/work into main and push."""
    _git("checkout", "main")
    _git("merge", "--no-ff", AGENT_BRANCH, "-m", "chore: merge agent/work into main")
    _git("push", "origin", "main")
    logger.info("Merged agent/work into main and pushed")
