# tests/test_agent_route.py
import os
os.environ.setdefault("OWNER_PHONE", "+972500000000")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "token_test")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+1234567890")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Patch queue before importing app
with patch("agent.queue.TaskQueue") as mock_queue_cls:
    mock_q = MagicMock()
    mock_queue_cls.return_value = mock_q
    from app.routes.dev_agent import router, get_queue
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

def twilio_form(from_number: str, body: str) -> dict:
    return {"From": f"whatsapp:{from_number}", "Body": body}

def test_unknown_sender_is_rejected():
    resp = client.post("/agent/command", data=twilio_form("+972599999999", "do something"))
    assert resp.status_code == 200
    xml = resp.text
    assert "<Response/>" in xml or "<Response>" in xml

def test_known_sender_creates_task():
    mock_q.handle_incoming_message.return_value = False
    resp = client.post(
        "/agent/command",
        data=twilio_form("+972500000000", "fix the bug in whatsapp_history.py"),
    )
    assert resp.status_code == 200
    mock_q.enqueue.assert_called_with("fix the bug in whatsapp_history.py")

def test_approval_reply_is_not_enqueued():
    mock_q.handle_incoming_message.return_value = True  # consumed as approval
    mock_q.enqueue.reset_mock()
    resp = client.post(
        "/agent/command",
        data=twilio_form("+972500000000", "כן"),
    )
    assert resp.status_code == 200
    mock_q.enqueue.assert_not_called()
