"""Model fallback: a delisted primary model must not fail every run (issue llnl#26).

Offline — the OpenAI client is mocked at app.utils.OpenAI.
"""

from unittest.mock import MagicMock, patch

import app.utils as utils
from app.utils import _model_candidates, call_llm, classify_llm_error


def _ok_completion(content: str):
    completion = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    completion.choices = [choice]
    return completion


def _client_that(behavior):
    """Build a mocked OpenAI client whose create() dispatches on the model kwarg."""
    client = MagicMock()

    def create(model=None, messages=None, temperature=None):
        return behavior(model)

    client.chat.completions.create.side_effect = create
    return client


# --- candidate ordering ---


def test_model_candidates_dedup_and_order():
    assert _model_candidates("a", ["b", "a", "c"]) == ["a", "b", "c"]
    assert _model_candidates("a", None) == ["a", *[m for m in utils.DEFAULT_FREE_FALLBACK_MODELS if m != "a"]]


# --- fallback behavior ---


def test_falls_back_to_working_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")

    def behavior(model):
        if model == "good/model:free":
            return _ok_completion("RECOVERED CONTENT")
        raise Exception("No endpoints found for model")

    with patch.object(utils, "OpenAI", return_value=_client_that(behavior)):
        result = call_llm("prompt", model="dead/model:free", fallback_models=["good/model:free"])

    assert result == "RECOVERED CONTENT"


def test_no_fallback_on_auth_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    client = _client_that(lambda model: (_ for _ in ()).throw(Exception("Error code: 401 - No auth credentials found")))

    with patch.object(utils, "OpenAI", return_value=client):
        result = call_llm("prompt", model="primary:free", fallback_models=["fallback:free"])

    assert "401" in result or "Authentication with OpenRouter failed" in result
    # Auth failure must stop immediately — never burn calls on other models.
    assert client.chat.completions.create.call_count == 1


def test_all_unavailable_surfaces_clear_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    client = _client_that(lambda model: (_ for _ in ()).throw(Exception("No endpoints found")))

    with patch.object(utils, "OpenAI", return_value=client):
        result = call_llm("prompt", model="a:free", fallback_models=["b:free", "c:free"])

    assert classify_llm_error(result) == "Model unavailable or delisted"
    # Every candidate attempted (primary + 2 fallbacks).
    assert client.chat.completions.create.call_count == 3


def test_primary_success_skips_fallback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    client = _client_that(lambda model: _ok_completion("PRIMARY OK"))

    with patch.object(utils, "OpenAI", return_value=client):
        result = call_llm("prompt", model="primary:free", fallback_models=["fallback:free"])

    assert result == "PRIMARY OK"
    assert client.chat.completions.create.call_count == 1


def test_missing_key_still_short_circuits(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = call_llm("prompt", model="x:free", fallback_models=["y:free"])
    assert result.startswith("Error:") and "key" in result.lower()
