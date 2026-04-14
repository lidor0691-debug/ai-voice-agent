import os
import time
import pytest
from unittest.mock import MagicMock, patch

def test_save_and_load_history():
    from agent.conversation import ConversationStore

    mock_sb = MagicMock()
    mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock()
    mock_sb.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "1", "role": "user", "content": "שלום", "created_at": 1.0},
            {"id": "2", "role": "assistant", "content": "שלום! מה שלומך?", "created_at": 2.0},
        ]
    )

    store = ConversationStore(sb=mock_sb)
    store.save("user", "שלום")
    history = store.get_history(limit=20)

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_format_history_for_prompt():
    from agent.conversation import format_history

    messages = [
        {"role": "user", "content": "שלום"},
        {"role": "assistant", "content": "היי! איך אני יכול לעזור?"},
    ]
    result = format_history(messages)
    assert "[user]: שלום" in result
    assert "[assistant]: היי! איך אני יכול לעזור?" in result
