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
    with (
        patch.object(gradio_app_module.requests, "get", side_effect=RuntimeError("offline test")),
        patch.object(gradio_app_module, "fetch_free_models", return_value=[]),
    ):
        demo = gradio_app_module.create_gradio_interface()
    assert demo is not None
    # The fetch failed, so the module must have fallen back to a non-empty default model list.
    assert gradio_app_module.available_models


def test_run_history_loads_existing_runs_and_delete_controls(gradio_app_module, monkeypatch, tmp_path):
    from app.models import ResearchGoal
    from app.run_store import RUNS_DIR_ENV, save_run

    monkeypatch.setenv(RUNS_DIR_ENV, str(tmp_path))
    save_run(
        research_goal=ResearchGoal(description="Existing saved run"),
        cycle_details={"iteration": 1, "steps": {}},
        status="done",
        references_html="",
        results_html="",
        run_id="run-existing",
    )

    with patch.object(gradio_app_module.requests, "get", side_effect=RuntimeError("offline test")):
        demo = gradio_app_module.create_gradio_interface()

    saved_runs = [
        component
        for component in demo.config["components"]
        if component["type"] == "html" and component["props"].get("label") == "Saved Runs"
    ]
    delete_dropdowns = [
        component
        for component in demo.config["components"]
        if component["type"] == "dropdown" and component["props"].get("label") == "Saved Run to Delete"
    ]
    delete_buttons = [
        component
        for component in demo.config["components"]
        if component["type"] == "button" and component["props"].get("value") == "Delete Selected Run"
    ]

    assert "Existing saved run" in saved_runs[0]["props"]["value"]
    assert any("run-existing" in str(choice) for choice in delete_dropdowns[0]["props"]["choices"])
    assert delete_buttons


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


def test_stale_configured_free_model_is_not_forced_as_default(gradio_app_module, monkeypatch):
    monkeypatch.setattr(gradio_app_module, "CONFIGURED_LLM_MODEL", "delisted/model:free")

    choices = gradio_app_module.get_model_dropdown_choices(["vendor/model-70b:free", "vendor/model-3b:free"])

    assert choices[0] == "vendor/model-3b:free"
    assert "delisted/model:free" not in choices


def test_hf_spaces_model_list_uses_dynamic_free_model_cache(gradio_app_module, monkeypatch):
    monkeypatch.setenv("SPACE_ID", "owner/space")
    with (
        patch.object(gradio_app_module, "fetch_free_models", return_value=["vendor/model-3b:free"]) as mock_fetch,
        patch.object(gradio_app_module.requests, "get") as mock_get,
    ):
        models = gradio_app_module.fetch_available_models()

    assert models == ["vendor/model-3b:free"]
    mock_fetch.assert_called_once()
    mock_get.assert_not_called()


def test_run_cycle_with_progress_streams_active_status(gradio_app_module, monkeypatch, tmp_path):
    from app.models import ContextMemory, ResearchGoal
    from app.run_store import RUNS_DIR_ENV

    monkeypatch.setenv(RUNS_DIR_ENV, str(tmp_path))
    gradio_app_module.current_research_goal = ResearchGoal(description="status test")
    gradio_app_module.global_context = ContextMemory()

    def slow_cycle(research_goal, context, cycle_supervisor):
        time.sleep(0.02)
        context.iteration_number += 1
        return {
            "status": "done",
            "results_html": "<p>done</p>",
            "references_html": "<p>refs</p>",
            "cycle_details": {"iteration": context.iteration_number, "steps": {}},
            "log_file": "",
        }

    monkeypatch.setattr(gradio_app_module, "execute_cycle", slow_cycle)
    monkeypatch.setattr(gradio_app_module, "write_report", lambda run: "report.html")
    monkeypatch.setattr(gradio_app_module, "report_file_url", lambda path: "/report.html")

    updates = list(gradio_app_module.run_cycle_with_progress(timeout_seconds=1, poll_seconds=0.001))

    assert any(
        "Active work: generating, reviewing, ranking, and evolving hypotheses." in update[0] for update in updates
    )
    assert any("Elapsed:" in update[0] for update in updates)
    assert updates[-1][0].startswith("done")
    assert updates[-1][1:] == ("<p>done</p>", "<p>refs</p>")
    assert gradio_app_module.global_context.iteration_number == 1


def test_run_cycle_with_progress_times_out(gradio_app_module, monkeypatch, tmp_path):
    from app.models import ContextMemory, ResearchGoal
    from app.run_store import RUNS_DIR_ENV

    monkeypatch.setenv(RUNS_DIR_ENV, str(tmp_path))
    gradio_app_module.current_research_goal = ResearchGoal(description="timeout test")
    gradio_app_module.global_context = ContextMemory()

    def stuck_cycle(research_goal, context, cycle_supervisor):
        time.sleep(0.05)
        context.iteration_number = 99
        return {
            "status": "late success",
            "results_html": "<p>late</p>",
            "references_html": "",
            "cycle_details": {"iteration": 99, "steps": {}},
            "log_file": "",
        }

    monkeypatch.setattr(gradio_app_module, "execute_cycle", stuck_cycle)

    updates = list(gradio_app_module.run_cycle_with_progress(timeout_seconds=0.01, poll_seconds=0.001))

    assert "timed out" in updates[-1][0]
    assert "time limit" in updates[-1][1]
    run_files = list((tmp_path / "runs").glob("*.json"))
    assert len(run_files) == 1
    assert gradio_app_module.global_context.iteration_number == 0
    time.sleep(0.06)
    assert len(list((tmp_path / "runs").glob("*.json"))) == 1
