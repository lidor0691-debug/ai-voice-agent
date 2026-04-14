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


def build_context() -> str:
    branch = get_current_branch()
    commits = get_recent_commits(n=5)
    commits_str = "\n".join(f"  {c['hash']} {c['message']}" for c in commits)

    # Check for failing tests
    test_status = _run("python -m pytest tests/ --tb=no -q 2>&1 | tail -5")

    return f"""
=== MAYA AI — Dev Agent Context ===

You are an autonomous development agent for the Maya AI project.
Project root: {PROJECT_ROOT}
Current branch: {branch}
Working branch: {AGENT_BRANCH}

Recent commits:
{commits_str}

Test status (last run):
{test_status}

=== RULES YOU MUST FOLLOW ===
1. Do all work on branch '{AGENT_BRANCH}' — never commit directly to main.
2. Before any `git push` or `railway up`: STOP and output a line that starts with
   APPROVAL_REQUIRED: followed by a summary of what you are about to do.
   Wait for the system to handle the approval — do not push yourself.
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

=== YOUR TASK ===
""".strip()
