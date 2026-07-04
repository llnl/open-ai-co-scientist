"""Offline tests: imports, environment detection, and Gradio UI construction.

The OpenRouter model-list fetch inside create_gradio_interface() is mocked so
these tests are deterministic and make no network calls.
"""

import importlib.util
import os
import time
from unittest.mock import patch

import pytest


def test_core_imports():
    import gradio  # noqa: F401

    from app.agents import SupervisorAgent  # noqa: F401
    from app.models import ContextMemory, ResearchGoal  # noqa: F401
    from app.tools.arxiv_search import ArxivSearchTool  # noqa: F401
    from app.utils import get_deployment_environment, is_huggingface_space, logger  # noqa: F401


def test_environment_detection_outside_hf_spaces(monkeypatch):
    from app.utils import get_deployment_environment, is_huggingface_space

    for var in ("SPACE_ID", "SPACE_AUTHOR_NAME", "SPACES_BUILDKIT_VERSION", "HF_HOME"):
        monkeypatch.delenv(var, raising=False)

    assert is_huggingface_space() is False
    assert isinstance(get_deployment_environment(), str)


@pytest.fixture(scope="module")
def gradio_app_module():
    """Load the root app.py as a module (the app/ package shadows it on import)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location("gradio_app", os.path.join(repo_root, "app.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gradio_interface_constructs_without_network(gradio_app_module):
    with patch.object(gradio_app_module.requests, "get", side_effect=RuntimeError("offline test")):
        demo = gradio_app_module.create_gradio_interface()
    assert demo is not None
    # The fetch failed, so the module must have fallen back to a non-empty default model list.
    assert gradio_app_module.available_models


def test_default_model_is_selected_and_first_choice(gradio_app_module):
    gradio_app_module.available_models = [
        "another/model",
        gradio_app_module.CONFIGURED_LLM_MODEL,
    ]

    choices = gradio_app_module.get_model_dropdown_choices()

    assert choices[0] == gradio_app_module.CONFIGURED_LLM_MODEL
    assert choices.count(gradio_app_module.CONFIGURED_LLM_MODEL) == 1


def test_free_model_is_default_when_configured_model_is_not_free(gradio_app_module, monkeypatch):
    monkeypatch.setattr(gradio_app_module, "CONFIGURED_LLM_MODEL", "paid/model")

    choices = gradio_app_module.get_model_dropdown_choices(["paid/model", "free/model:free"])

    assert choices[0] == "free/model:free"


def test_run_cycle_with_progress_streams_active_status(gradio_app_module, monkeypatch):
    from app.models import ContextMemory, ResearchGoal

    gradio_app_module.current_research_goal = ResearchGoal(description="status test")
    gradio_app_module.global_context = ContextMemory()

    def slow_cycle():
        time.sleep(0.02)
        return "done", "<p>done</p>", "<p>refs</p>"

    monkeypatch.setattr(gradio_app_module, "run_cycle", slow_cycle)

    updates = list(gradio_app_module.run_cycle_with_progress(timeout_seconds=1, poll_seconds=0.001))

    assert any(
        "Active work: generating, reviewing, ranking, and evolving hypotheses." in update[0] for update in updates
    )
    assert updates[-1] == ("done", "<p>done</p>", "<p>refs</p>")


def test_run_cycle_with_progress_times_out(gradio_app_module, monkeypatch, tmp_path):
    from app.models import ContextMemory, ResearchGoal
    from app.run_store import RUNS_DIR_ENV

    monkeypatch.setenv(RUNS_DIR_ENV, str(tmp_path))
    gradio_app_module.current_research_goal = ResearchGoal(description="timeout test")
    gradio_app_module.global_context = ContextMemory()

    def stuck_cycle():
        time.sleep(0.05)
        return "late", "", ""

    monkeypatch.setattr(gradio_app_module, "run_cycle", stuck_cycle)

    updates = list(gradio_app_module.run_cycle_with_progress(timeout_seconds=0.01, poll_seconds=0.001))

    assert "timed out" in updates[-1][0]
    assert "time limit" in updates[-1][1]
    assert list((tmp_path / "runs").glob("*.json"))
