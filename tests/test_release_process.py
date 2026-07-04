from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from scripts.prepare_upstream_release import (
    ReleasePlan,
    build_pr_body,
    extract_issue_numbers,
    sync_branch_for,
    validate_repo,
    validate_version,
)


def test_validate_version_accepts_release_and_rc_versions():
    assert validate_version("v1.2.3") == "v1.2.3"
    assert validate_version("v1.2.3-rc1") == "v1.2.3-rc1"
    assert sync_branch_for("v1.2.3") == "sync/v1.2.3"


def test_validate_version_rejects_unsafe_branch_text():
    bad_versions = ["1.2.3", "v1", "v1.2", "v1.2.3 && echo nope", "v1.2.3/extra"]
    for version in bad_versions:
        try:
            validate_version(version)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid version: {version}")


def test_validate_repo_accepts_owner_name_only():
    assert validate_repo("llnl/open-ai-co-scientist") == "llnl/open-ai-co-scientist"
    for repo in ["llnl", "llnl/open ai", "https://github.com/llnl/open-ai-co-scientist", "a/b/c"]:
        try:
            validate_repo(repo)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid repo: {repo}")


def test_extract_issue_numbers_preserves_order_and_deduplicates():
    lines = [
        "abc1234 Fixes #7 document release path",
        "def5678 closes #12 and resolves #7",
        "9999999 unrelated docs",
    ]
    assert extract_issue_numbers(lines) == ["7", "12"]


def test_build_pr_body_includes_publication_gate_and_auto_deploy_contract():
    body = build_pr_body(
        ReleasePlan(
            version="v0.1.0",
            upstream_repo="llnl/open-ai-co-scientist",
            base_branch="main",
            head_ref="HEAD",
            sync_branch="sync/v0.1.0",
            commit_lines=("abc1234 Fixes #7 create release process",),
        )
    )

    assert "`v0.1.0` release candidate" in body
    assert "Fixes #7" in body
    assert "Public upstream CI is green" in body
    assert "results/`, `.env`, `.worktree/`, and `.audit/`" in body
    assert "Merging this PR with a merge commit triggers the Hugging Face deploy workflow" in body
    assert "The tag is not required to deploy" in body
    assert "Space status" in body


def load_workflow(name: str) -> dict:
    path = Path(".github/workflows") / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_github_actions_use_node24_compatible_versions():
    node20_action_pins = {
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/upload-artifact@v4",
        "actions/upload-artifact@v5",
        "actions/download-artifact@v4",
        "actions/download-artifact@v5",
    }

    for workflow_path in Path(".github/workflows").glob("*.yml"):
        workflow = load_workflow(workflow_path.name)
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                action = step.get("uses")
                assert action not in node20_action_pins, f"{workflow_path}: {action}"


def test_upstream_sync_workflow_is_manual_and_dry_run_by_default():
    workflow = load_workflow("upstream-sync.yml")

    dispatch = workflow[True]["workflow_dispatch"]
    assert dispatch["inputs"]["dry_run"]["default"] == "true"
    assert "pull_request_target" not in workflow.get(True, {})
    assert workflow["permissions"] == {"contents": "read"}

    steps = workflow["jobs"]["prepare"]["steps"]
    joined_steps = "\n".join(str(step) for step in steps)
    assert "UPSTREAM_SYNC_TOKEN" in joined_steps
    assert "scripts/prepare_upstream_release.py" in joined_steps
    assert "validate_repo" in joined_steps


def test_huggingface_deploy_workflow_runs_checks_before_deploy():
    workflow = load_workflow("huggingface-deploy.yml")

    assert "v*" in workflow[True]["push"]["tags"]
    assert "main" in workflow[True]["push"]["branches"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "from llnl/sync/v" in workflow["jobs"]["deploy"]["if"]

    steps = workflow["jobs"]["deploy"]["steps"]
    step_names = [step.get("name", "") for step in steps]
    assert step_names.index("Lint and offline tests") < step_names.index("Deploy to Hugging Face Space")
    assert step_names.index("Hugging Face dependency preflight") < step_names.index("Deploy to Hugging Face Space")
    assert step_names.index("Deploy to Hugging Face Space") < step_names.index("Watch Hugging Face deployment status")

    joined_steps = "\n".join(str(step) for step in steps)
    assert "HF_TOKEN" in joined_steps
    assert "HF_SPACE_ID" in joined_steps
    assert "--exclude .env" in joined_steps
    assert "--exclude results" in joined_steps
    assert "gradio[oauth,mcp]" in joined_steps
    assert "pip install --dry-run" in joined_steps
    assert "scripts/watch_huggingface_space.py" in joined_steps


def test_huggingface_readme_metadata_matches_runtime_pins():
    readme = Path("README.md").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    workflow = load_workflow("huggingface-deploy.yml")

    sdk_version_line = next(line for line in readme.splitlines() if line.startswith("sdk_version:"))
    python_version_line = next(line for line in readme.splitlines() if line.startswith("python_version:"))
    gradio_line = next(line for line in requirements.splitlines() if line.startswith("gradio=="))

    assert sdk_version_line == f"sdk_version: {gradio_line.split('==', 1)[1]}"
    assert python_version_line == f"python_version: {workflow['jobs']['deploy']['steps'][1]['with']['python-version']}"


def test_huggingface_requirements_match_gradio_mcp_constraints():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "gradio==6.19.0" in requirements
    assert "pydantic==2.12.5" in requirements


def test_upstream_sync_workflow_uses_sync_candidate_language():
    workflow = load_workflow("upstream-sync.yml")

    joined_steps = "\n".join(str(step) for step in workflow["jobs"]["prepare"]["steps"])
    assert "Sync $VERSION candidate from loop repo" in joined_steps
    assert "Release $VERSION from loop repo" not in joined_steps


def test_watch_huggingface_space_succeeds_when_space_runs():
    from scripts.watch_huggingface_space import watch_space

    client = SimpleNamespace(get_space_runtime=lambda repo_id, token=None: SimpleNamespace(stage="RUNNING"))

    assert watch_space("user/space", client=client, timeout_seconds=1, poll_seconds=1) == "RUNNING"


def test_watch_huggingface_space_fails_on_build_error():
    from scripts.watch_huggingface_space import watch_space

    client = SimpleNamespace(get_space_runtime=lambda repo_id, token=None: SimpleNamespace(stage="BUILD_ERROR"))

    try:
        watch_space("user/space", client=client, timeout_seconds=1, poll_seconds=1)
    except RuntimeError as exc:
        assert "BUILD_ERROR" in str(exc)
    else:
        raise AssertionError("BUILD_ERROR did not fail the watcher")


def test_watch_huggingface_space_times_out_without_terminal_stage():
    from scripts.watch_huggingface_space import watch_space

    client = SimpleNamespace(get_space_runtime=lambda repo_id, token=None: SimpleNamespace(stage="BUILDING"))

    with (
        patch("scripts.watch_huggingface_space.time.sleep"),
        patch(
            "scripts.watch_huggingface_space.time.monotonic",
            side_effect=[0, 0, 2],
        ),
    ):
        try:
            watch_space("user/space", client=client, timeout_seconds=1, poll_seconds=1)
        except TimeoutError as exc:
            assert "BUILDING" in str(exc)
        else:
            raise AssertionError("non-terminal stage did not time out")
