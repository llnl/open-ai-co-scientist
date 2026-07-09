"""Model fallback: a delisted primary model must not fail every run (issue llnl#26).

Fallback candidates come from OpenRouter's live free-model list; a static list
is only a last resort. Offline — the client and the model fetch are mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

import app.utils as utils
from app.utils import _model_candidates, call_llm, classify_llm_error, order_free_models_for_demo


@pytest.fixture(autouse=True)
def _reset_model_cache():
    """The free-model list is cached in a module global; reset between tests."""
    utils._free_models_cache = None
    yield
    utils._free_models_cache = None


def _ok_completion(content: str):
    completion = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    completion.choices = [choice]
    return completion


def _client_that(behavior):
    """Mocked OpenAI client whose create() dispatches on the model kwarg."""
    client = MagicMock()

    def create(model=None, messages=None, temperature=None):
        return behavior(model)

    client.chat.completions.create.side_effect = create
    return client


def _raise(msg):
    def _b(model):
        raise Exception(msg)

    return _b


# --- candidate ordering ---


def test_model_candidates_dedup_and_order():
    assert _model_candidates("a", ["b", "a", "c"]) == ["a", "b", "c"]
    assert _model_candidates("a", None) == ["a"]
    assert _model_candidates("a", []) == ["a"]


def test_order_free_models_for_demo_prefers_compact_models():
    preferred = utils.PREFERRED_FREE_MODELS[0]
    models = ["z/large:free", "paid/model", preferred, "a/other:free", preferred]

    assert order_free_models_for_demo(models) == [preferred, "z/large:free", "a/other:free"]


# --- fetch_free_models: filtering + caching, never raises ---


def test_fetch_free_models_filters_and_caches(monkeypatch):
    payload = {"data": [{"id": "x/y:free"}, {"id": "a/b"}, {"id": "c/d:free"}, {"id": None}]}
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    with patch.object(utils.requests, "get", return_value=resp) as mock_get:
        first = utils.fetch_free_models()
        second = utils.fetch_free_models()  # cached — no second HTTP call
    assert first == ["c/d:free", "x/y:free"]
    assert second == first
    assert mock_get.call_count == 1


def test_fetch_free_models_returns_empty_on_error(monkeypatch):
    with patch.object(utils.requests, "get", side_effect=Exception("network down")):
        assert utils.fetch_free_models() == []


def test_get_fallback_models_orders_live_preferred_models_first(monkeypatch):
    preferred = utils.PREFERRED_FREE_MODELS[0]
    with patch.object(utils, "fetch_free_models", return_value=["z/large:free", preferred, "a/other:free"]):
        fallbacks = utils.get_fallback_models(primary="selected/model:free")

    assert fallbacks[:3] == [preferred, "z/large:free", "a/other:free"]


# --- fallback behavior (explicit list) ---


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
    client = _client_that(_raise("Error code: 401 - No auth credentials found"))
    with patch.object(utils, "OpenAI", return_value=client):
        result = call_llm("prompt", model="primary:free", fallback_models=["fallback:free"])
    assert "401" in result or "Authentication with OpenRouter failed" in result
    assert client.chat.completions.create.call_count == 1  # never tries other models


def test_primary_success_skips_fallback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    client = _client_that(lambda model: _ok_completion("PRIMARY OK"))
    with patch.object(utils, "OpenAI", return_value=client):
        result = call_llm("prompt", model="primary:free", fallback_models=["fallback:free"])
    assert result == "PRIMARY OK"
    assert client.chat.completions.create.call_count == 1  # no fallback fetch/attempt


# --- dynamic fallback: live list is the source of truth ---


def test_dynamic_fallback_uses_live_free_models(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")

    def behavior(model):
        if model == "live-b:free":
            return _ok_completion("FROM LIVE LIST")
        raise Exception("No endpoints found for model")  # primary + live-a dead

    with (
        patch.object(utils, "fetch_free_models", return_value=["live-a:free", "live-b:free"]),
        patch.object(utils, "OpenAI", return_value=_client_that(behavior)),
    ):
        result = call_llm("prompt", model="dead-primary:free")  # no explicit fallback_models
    assert result == "FROM LIVE LIST"


def test_static_fallback_when_live_list_unavailable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    working = utils.STATIC_FALLBACK_MODELS[0]

    def behavior(model):
        if model == working:
            return _ok_completion("FROM STATIC FALLBACK")
        raise Exception("No endpoints found for model")

    with (
        patch.object(utils, "fetch_free_models", return_value=[]),  # live fetch failed
        patch.object(utils, "OpenAI", return_value=_client_that(behavior)),
    ):
        result = call_llm("prompt", model="dead-primary:free")
    assert result == "FROM STATIC FALLBACK"


def test_all_unavailable_surfaces_clear_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    client = _client_that(_raise("No endpoints found"))
    with (
        patch.object(utils, "fetch_free_models", return_value=["b:free", "c:free"]),
        patch.object(utils, "OpenAI", return_value=client),
    ):
        result = call_llm("prompt", model="a:free")
    assert classify_llm_error(result) == "Model unavailable or delisted"
    assert client.chat.completions.create.call_count == 3  # primary + 2 live fallbacks


def test_fallback_attempts_are_bounded(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    client = _client_that(_raise("No endpoints found"))
    many = [f"m{i}:free" for i in range(20)]
    with (
        patch.object(utils, "fetch_free_models", return_value=many),
        patch.object(utils, "OpenAI", return_value=client),
    ):
        call_llm("prompt", model="a:free")
    # primary + at most MAX_FALLBACK_ATTEMPTS, never all 20.
    assert client.chat.completions.create.call_count == 1 + utils.MAX_FALLBACK_ATTEMPTS


def test_missing_key_still_short_circuits(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = call_llm("prompt", model="x:free", fallback_models=["y:free"])
    assert result.startswith("Error:") and "key" in result.lower()


# --- rate-limited free models: move to the next model, don't hang (found via
#     live testing — a free model returning 429 must not block the whole run) ---


def test_rate_limited_primary_falls_back(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")

    def behavior(model):
        if model == "good:free":
            return _ok_completion("OK AFTER RATE LIMIT")
        raise Exception("Error code: 429 - temporarily rate-limited upstream")

    with patch.object(utils, "OpenAI", return_value=_client_that(behavior)):
        result = call_llm("prompt", model="busy:free", fallback_models=["good:free"])
    assert result == "OK AFTER RATE LIMIT"


def test_all_rate_limited_surfaces_clear_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    client = _client_that(_raise("Error code: 429 - rate-limited"))
    with (
        patch.object(utils, "fetch_free_models", return_value=["b:free"]),
        patch.object(utils, "OpenAI", return_value=client),
    ):
        result = call_llm("prompt", model="a:free")
    assert classify_llm_error(result) == "Rate limited by the model provider"
    assert client.chat.completions.create.call_count == 2  # primary + 1 fallback, no long retry


def test_timed_out_primary_falls_back(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")

    def behavior(model):
        if model == "good:free":
            return _ok_completion("OK AFTER TIMEOUT")
        raise Exception("Request timed out while waiting for provider")

    with patch.object(utils, "OpenAI", return_value=_client_that(behavior)):
        result = call_llm("prompt", model="slow:free", fallback_models=["good:free"])
    assert result == "OK AFTER TIMEOUT"


def test_all_timed_out_surfaces_clear_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    client = _client_that(_raise("Request timeout from provider"))
    with (
        patch.object(utils, "fetch_free_models", return_value=["b:free"]),
        patch.object(utils, "OpenAI", return_value=client),
    ):
        result = call_llm("prompt", model="a:free")
    assert classify_llm_error(result) == "Model provider timed out"
    assert client.chat.completions.create.call_count == 2


def test_generic_provider_error_also_falls_back(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")

    def behavior(model):
        if model == "good:free":
            return _ok_completion("RECOVERED")
        raise Exception("Error code: 502 - Provider returned error")

    with patch.object(utils, "OpenAI", return_value=_client_that(behavior)):
        result = call_llm("prompt", model="broken:free", fallback_models=["good:free"])
    assert result == "RECOVERED"
