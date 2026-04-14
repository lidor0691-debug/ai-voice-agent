# agent/context.py
"""
Builds the context preamble injected before every task prompt.
Gives Claude Code full situational awareness of the project.
"""
import subprocess
from agent.config import PROJECT_ROOT, AGENT_BRANCH
from agent.git_ops import get_current_branch, get_recent_commits


def _run(cmd: str) -> str:
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip()
    except Exception:
        return "(unavailable)"


def _pytest_status() -> str:
    """Run pytest and return last 5 lines of output. Windows-compatible."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "--tb=no", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=60,
        )
        lines = (result.stdout + result.stderr).splitlines()
        return "\n".join(lines[-5:]) or "(no output)"
    except Exception:
        return "(unavailable)"


def build_context(history: str = "") -> str:
    try:
        branch = get_current_branch()
    except RuntimeError:
        branch = "(unavailable)"

    try:
        commits = get_recent_commits(n=5)
    except RuntimeError:
        commits = []

    commits_str = "\n".join(f"  {c['hash']} {c['message']}" for c in commits) or "  (none)"
    test_status = _pytest_status()

    history_section = ""
    if history:
        history_section = f"""
=== CONVERSATION HISTORY ===
{history}

"""

    return f"""
=== MAYA AI — Dev Agent Context ===

You are an autonomous development agent for the Maya AI project.
Always communicate in Hebrew (עברית) — all responses must be in Hebrew.
Project root: {PROJECT_ROOT}
Current branch: {branch}
Working branch: {AGENT_BRANCH}

Recent commits:
{commits_str}

Test status (last run):
{test_status}

=== IMPORTANT ===
IGNORE all memory files and previous session context. Base your answers ONLY on the actual current state of the codebase. Read files directly to answer questions.

=== RULES YOU MUST FOLLOW ===
1. Do all work on branch '{AGENT_BRANCH}' — never commit directly to main.
2. Before any `git push`, `railway up`, or ANY file modification: STOP and output a line that starts with
   APPROVAL_REQUIRED: followed by a summary of what you are about to do.
   Wait for the system to handle the approval — do not make changes yourself.
3. If you encounter an error, retry up to 2 times before giving up.
4. When done, output a line starting with TASK_COMPLETE: followed by a summary.
5. If you need the owner's physical input (test UX, visual check), output a line
   starting with GUIDANCE_NEEDED: followed by step-by-step instructions.
6. Keep the production FastAPI server untouched while working — do not kill uvicorn.

=== PROJECT OVERVIEW ===
- Backend: FastAPI (Python), deployed on Railway
- Frontend: Next.js dashboard in ./dashboard/
- Database: Supabase (PostgreSQL)
- WhatsApp: Twilio + Make.com
- AI: OpenAI Realtime API for voice, OpenAI chat for WhatsApp replies (Maya)
- Main entry: main.py → app/routes/
{history_section}
=== CURRENT MESSAGE (ענה בעברית בלבד!) ===
""".strip()
