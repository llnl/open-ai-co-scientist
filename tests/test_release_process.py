from pathlib import Path

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


def test_build_pr_body_includes_publication_gate_and_release_tag():
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

    assert "Release v0.1.0" in body
    assert "Fixes #7" in body
    assert "Public upstream CI is green" in body
    assert "results/`, `.env`, `.worktree/`, and `.audit/`" in body
    assert "tag the upstream merge commit as `v0.1.0`" in body


def load_workflow(name: str) -> dict:
    path = Path(".github/workflows") / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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
    assert workflow["permissions"] == {"contents": "read"}

    steps = workflow["jobs"]["deploy"]["steps"]
    step_names = [step.get("name", "") for step in steps]
    assert step_names.index("Lint and offline tests") < step_names.index("Deploy to Hugging Face Space")

    joined_steps = "\n".join(str(step) for step in steps)
    assert "HF_TOKEN" in joined_steps
    assert "HF_SPACE_ID" in joined_steps
    assert "--exclude .env" in joined_steps
    assert "--exclude results" in joined_steps
