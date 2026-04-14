# tests/test_agent_whatsapp.py
import os
os.environ.setdefault("OWNER_PHONE", "+972500000000")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "token_test")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+1234567890")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

from unittest.mock import patch, MagicMock
from agent.whatsapp import send_to_owner

def test_send_to_owner_calls_twilio():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SM123")
    with patch("agent.whatsapp.Client", return_value=mock_client):
        send_to_owner("Task complete!")
    mock_client.messages.create.assert_called_once_with(
        from_="whatsapp:+1234567890",
        to="whatsapp:+972500000000",
        body="Task complete!",
    )

def test_send_to_owner_truncates_long_message():
    long_msg = "x" * 2000
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SM123")
    with patch("agent.whatsapp.Client", return_value=mock_client):
        send_to_owner(long_msg)
    sent_body = mock_client.messages.create.call_args[1]["body"]
    assert len(sent_body) <= 1600
    assert sent_body.endswith("... [truncated]")
