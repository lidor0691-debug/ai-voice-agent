import os, subprocess, tempfile, pytest

os.environ.setdefault("OWNER_PHONE", "+972500000000")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "token_test")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+1234567890")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

from agent.git_ops import get_diff_summary, get_recent_commits, get_current_branch

def test_get_current_branch_returns_string():
    branch = get_current_branch()
    assert isinstance(branch, str)
    assert len(branch) > 0

def test_get_recent_commits_returns_list():
    commits = get_recent_commits(n=3)
    assert isinstance(commits, list)
    assert len(commits) <= 3
    for c in commits:
        assert "hash" in c
        assert "message" in c

def test_get_diff_summary_returns_string():
    summary = get_diff_summary(base="HEAD~1", head="HEAD")
    assert isinstance(summary, str)
