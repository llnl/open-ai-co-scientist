"""Generation-failure errors must surface their real cause, not a silent empty
ranking (issue llnl#36). Offline: the LLM boundary is mocked at app.agents.call_llm.
"""

from unittest.mock import patch

import pytest

import app.utils as utils
from app.agents import GenerationAgent, SupervisorAgent
from app.models import ContextMemory, ResearchGoal
from app.utils import classify_llm_error

# --- classifier unit tests (the four required categories + fallback) ---


@pytest.mark.parametrize(
    "error_text, expected",
    [
        ("Error: OpenRouter API key not set.", "Missing or invalid API key"),
        ("Authentication with OpenRouter failed (401 Unauthorized).", "Missing or invalid API key"),
        ("Error: Rate limit exceeded: slow down", "Rate limited by the model provider"),
        ("Error: Model unavailable or delisted ('x/y'). No endpoints found", "Model unavailable or delisted"),
        ("Could not parse LLM response: Expecting value", "Model returned unparsable output"),
        ("Error: LLM model not configured.", "LLM model not configured"),
        ("Error: API call failed: connection reset", "LLM/API error"),
    ],
)
def test_classify_llm_error_categories(error_text, expected):
    assert classify_llm_error(error_text) == expected


# --- generation surfaces errors instead of swallowing them ---


def _goal():
    return ResearchGoal("test goal", num_hypotheses=2)


def test_generate_returns_errors_and_keeps_them_out_of_hypotheses():
    with patch(
        "app.agents.call_llm",
        return_value="Authentication with OpenRouter failed (401 Unauthorized).",
    ):
        hypos, errors = GenerationAgent().generate_new_hypotheses(_goal(), ContextMemory())

    assert hypos == []  # error markers must never enter the ranking flow
    assert len(errors) == 1
    assert classify_llm_error(errors[0]) == "Missing or invalid API key"


def test_generate_happy_path_returns_no_errors():
    payload = '[{"title": "H1", "text": "idea one"}, {"title": "H2", "text": "idea two"}]'
    with patch("app.agents.call_llm", return_value=payload):
        hypos, errors = GenerationAgent().generate_new_hypotheses(_goal(), ContextMemory())

    assert [h.title for h in hypos] == ["H1", "H2"]
    assert errors == []


# --- full cycle propagates the cause to cycle_details["errors"] ---


@pytest.mark.parametrize(
    "llm_error, expected_category",
    [
        ("Authentication with OpenRouter failed (401 Unauthorized).", "Missing or invalid API key"),
        ("Error: Rate limit exceeded: too many requests", "Rate limited by the model provider"),
        ("Error: Model unavailable or delisted ('x'). No endpoints found", "Model unavailable or delisted"),
    ],
)
def test_run_cycle_propagates_generation_error(llm_error, expected_category):
    with patch("app.agents.call_llm", return_value=llm_error):
        details = SupervisorAgent().run_cycle(_goal(), ContextMemory())

    assert details.get("errors"), "run_cycle must expose the failure cause"
    assert not details["steps"]["generation"]["hypotheses"]
    assert expected_category in {classify_llm_error(e) for e in details["errors"]}


def test_run_cycle_no_errors_key_on_success():
    payload = '[{"title": "H1", "text": "idea one"}]'
    with patch("app.agents.call_llm", return_value=payload):
        details = SupervisorAgent().run_cycle(_goal(), ContextMemory())

    assert "errors" not in details or not details["errors"]
    assert details["steps"]["generation"]["hypotheses"]


def test_surfaced_error_never_contains_key(monkeypatch):
    """End-to-end: a provider error echoing the key must be redacted before it
    reaches cycle_details["errors"]. Exercises the real call_llm redaction (the
    'No endpoints found' branch returns immediately — no retry sleeps)."""
    fake_key = "sk-or-v1-LEAK-CANARY"
    monkeypatch.setenv("OPENROUTER_API_KEY", fake_key)
    with patch.object(utils, "OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.side_effect = Exception(
            f"No endpoints found for model; key was {fake_key}"
        )
        details = SupervisorAgent().run_cycle(_goal(), ContextMemory())

    assert details.get("errors"), "expected the model-unavailable error to surface"
    for e in details["errors"]:
        assert fake_key not in e
    assert any(classify_llm_error(e) == "Model unavailable or delisted" for e in details["errors"])
