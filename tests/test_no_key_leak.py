"""Guard against credential leakage into logs (design doc §8.1 / Phase -1 Step 2.5).

The API key must never appear in log output, whether a call succeeds or fails.
"""

import json
import logging
from unittest.mock import MagicMock, patch

import app.utils as utils
from app.agents import call_llm_for_generation

FAKE_KEY = "sk-or-v1-THIS-FAKE-KEY-MUST-NEVER-BE-LOGGED"


def _completion(content: str):
    completion = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    completion.choices = [choice]
    return completion


def test_key_absent_from_logs_on_success(monkeypatch, caplog):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    payload = json.dumps([{"title": "T", "text": "X"}])
    with caplog.at_level(logging.DEBUG):
        with patch.object(utils, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = _completion(payload)
            call_llm_for_generation("goal", num_hypotheses=1)

    assert FAKE_KEY not in caplog.text


def test_key_absent_from_logs_on_error(monkeypatch, caplog):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    with caplog.at_level(logging.DEBUG):
        with patch.object(utils, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.side_effect = Exception(
                "Error code: 401 - No auth credentials found"
            )
            call_llm_for_generation("goal", num_hypotheses=1)

    assert FAKE_KEY not in caplog.text


def test_key_absent_from_error_message_shown_to_user(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    with patch.object(utils, "OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.side_effect = Exception(f"boom {FAKE_KEY} leaked")
        response = utils.call_llm("prompt")

    # The raw exception text is propagated into the user-facing error today; if a
    # provider ever echoes the key, it must not reach the user or the logs.
    assert FAKE_KEY not in response
