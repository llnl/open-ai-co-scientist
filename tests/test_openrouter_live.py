"""Live OpenRouter model-list smoke tests.

These tests query only the public /models endpoint. They do not call chat
completions, do not require OPENROUTER_API_KEY, and should not spend money.
They run in GitHub Actions as a focused network smoke test; the default local
`make test` suite still excludes `network` tests.
"""

import importlib.util
import time
from pathlib import Path

import pytest

import app.utils as utils


@pytest.fixture(autouse=True)
def isolated_model_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "OPENROUTER_MODEL_CACHE_PATH", str(tmp_path / "openrouter_free_models.json"))
    utils._free_models_cache = None
    utils._free_models_cache_checked_at = None
    yield
    utils._free_models_cache = None
    utils._free_models_cache_checked_at = None


def _fetch_live_free_models_with_retries(attempts: int = 3):
    models = []
    for attempt in range(attempts):
        models = utils.fetch_free_models(force_refresh=True)
        if models:
            return models
        if attempt < attempts - 1:
            time.sleep(2)
    return models


@pytest.mark.network
def test_live_openrouter_free_model_discovery_without_api_key(monkeypatch):
    """The public model catalog should expose currently available free models."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    models = _fetch_live_free_models_with_retries()

    assert models, "OpenRouter /models returned no free models"
    assert len(models) == len(set(models))
    assert all(":free" in model for model in models)

    sizes = [utils._estimate_model_size_b(model) for model in models]
    seen_unknown_size = False
    previous_size = -1.0
    for size in sizes:
        if size is None:
            seen_unknown_size = True
            continue
        assert not seen_unknown_size, "size-known models should sort before unknown-size models"
        assert size >= previous_size
        previous_size = size


@pytest.mark.network
def test_live_default_dropdown_choice_comes_from_openrouter_free_list(monkeypatch):
    """A stale configured free model must not override the live free-model list."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    live_free_models = _fetch_live_free_models_with_retries()
    assert live_free_models, "OpenRouter /models returned no free models"

    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("gradio_app_live_openrouter", repo_root / "app.py")
    gradio_app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gradio_app)

    monkeypatch.setattr(gradio_app, "CONFIGURED_LLM_MODEL", "definitely-delisted/model:free")
    choices = gradio_app.get_model_dropdown_choices(live_free_models)

    assert choices[0] == live_free_models[0]
    assert choices[0] in live_free_models
    assert "definitely-delisted/model:free" not in choices
