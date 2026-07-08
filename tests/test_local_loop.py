from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.local_loop import (
    Issue,
    LoopConfig,
    LoopError,
    build_implement_prompt,
    build_plan_prompt,
    default_root,
    issue_sort_key,
    parse_args,
    parse_score,
    run_codex,
    run_once,
    select_issue,
)


class FakeRunner:
    def __init__(self, json_responses=None):
        self.json_responses = list(json_responses or [])
        self.run_calls = []
        self.json_calls = []

    def json(self, args, *, cwd=None):
        self.json_calls.append((args, cwd))
        if not self.json_responses:
            raise AssertionError(f"unexpected json call: {args}")
        return self.json_responses.pop(0)

    def run(self, args, *, cwd=None, input_text=None, env=None, capture_output=True):
        self.run_calls.append(
            {
                "args": args,
                "cwd": cwd,
                "input_text": input_text,
                "env": env,
                "capture_output": capture_output,
            }
        )
        return SimpleNamespace(stdout="", stderr="", returncode=0)


def issue(number: int, title: str, body: str = "", labels: tuple[str, ...] = ("loop:ready",)) -> Issue:
    return Issue(number=number, title=title, body=body, url=f"https://example.test/{number}", labels=labels)


def config(tmp_path: Path, *, dry_run=True, issue_number=None) -> LoopConfig:
    return LoopConfig(
        repo="owner/repo",
        root=tmp_path,
        worktree_root=tmp_path / ".worktree",
        issue=issue_number,
        dry_run=dry_run,
        max_open_loop_prs=2,
        codex_bin="codex",
        codex_model=None,
        codex_extra_args=(),
        skip_codex=False,
        skip_validation=False,
        skip_pr=False,
    )


def test_parse_score_reads_triage_score_and_defaults_when_absent():
    assert parse_score("Score: `score:5/2/1`").value == 5
    assert parse_score("Score: `score:5/2/1`").effort == 2
    assert parse_score("Score: `score:5/2/1`").risk == 1
    assert parse_score("no score here").value == 3
    assert parse_score("no score here").effort == 3
    assert parse_score("no score here").risk == 3


def test_select_issue_prioritizes_value_then_effort_then_risk():
    issues = [
        issue(10, "low effort", "score:4/1/1"),
        issue(11, "highest value", "score:5/3/2"),
        issue(12, "highest value lower effort", "score:5/2/3"),
        issue(13, "highest value lower effort lower risk", "score:5/2/1"),
    ]

    assert sorted(issues, key=issue_sort_key)[0].number == 13
    assert select_issue(issues).number == 13
    assert select_issue(issues, requested=10).number == 10


def test_select_issue_rejects_missing_requested_issue():
    with pytest.raises(LoopError, match="Requested issue #99"):
        select_issue([issue(1, "one")], requested=99)


def test_dry_run_selects_specific_issue_without_claiming_or_codex(tmp_path, capsys):
    fake = FakeRunner(
        json_responses=[
            [],  # open loop PRs
            {
                "number": 25,
                "title": "Fix SSL",
                "body": "score:5/2/2",
                "url": "https://github.test/issues/25",
                "labels": [{"name": "loop:ready"}],
            },
        ]
    )

    assert run_once(config(tmp_path, dry_run=True, issue_number=25), fake) == 0

    out = capsys.readouterr().out
    assert "Selected issue #25" in out
    assert "DRY RUN: would use worktree" in out
    assert not fake.run_calls
    assert fake.json_calls[0][0][:4] == ["gh", "pr", "list", "--repo"]
    assert fake.json_calls[1][0][:4] == ["gh", "issue", "view", "25"]


def test_dry_run_honors_open_pr_throttle(tmp_path):
    fake = FakeRunner(json_responses=[[{"number": 1}, {"number": 2}]])

    with pytest.raises(LoopError, match="Open loop PR throttle hit"):
        run_once(config(tmp_path, dry_run=True), fake)


def test_prompt_builders_include_versioned_prompt_and_issue_context(tmp_path):
    prompt_dir = tmp_path / "docs" / "loop" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "plan.md").write_text("PLAN RULES", encoding="utf-8")
    (prompt_dir / "implement.md").write_text("IMPLEMENT RULES", encoding="utf-8")
    cfg = config(tmp_path)
    selected = issue(25, "Fix SSL", "Acceptance criteria")

    plan = build_plan_prompt(cfg, selected)
    implement = build_implement_prompt(cfg, selected, "Do the thing")

    assert "PLAN RULES" in plan
    assert "Issue context" in plan
    assert "Fix SSL" in plan
    assert "IMPLEMENT RULES" in implement
    assert "Approved local plan" in implement
    assert "Do the thing" in implement


def test_run_codex_constructs_read_only_and_model_command(tmp_path):
    fake = FakeRunner()
    output = tmp_path / ".loop" / "plan.md"
    cfg = LoopConfig(
        repo="owner/repo",
        root=tmp_path,
        worktree_root=tmp_path / ".worktree",
        issue=None,
        dry_run=False,
        max_open_loop_prs=2,
        codex_bin="codex-test",
        codex_model="gpt-test",
        codex_extra_args=("--json",),
        skip_codex=False,
        skip_validation=False,
        skip_pr=False,
    )

    run_codex(cfg, tmp_path, prompt="hello", output_path=output, read_only=True, runner=fake)

    call = fake.run_calls[0]
    assert call["args"][:2] == ["codex-test", "exec"]
    assert "--cd" in call["args"]
    assert "--sandbox" in call["args"]
    assert "read-only" in call["args"]
    assert "--model" in call["args"]
    assert "gpt-test" in call["args"]
    assert "--json" in call["args"]
    assert call["input_text"] == "hello"


def test_parse_args_resolves_worktree_root_relative_to_root(tmp_path):
    cfg = parse_args(["--root", str(tmp_path), "--worktree-root", ".worktree", "--dry-run"])

    assert cfg.root == tmp_path.resolve()
    assert cfg.worktree_root == tmp_path.resolve() / ".worktree"
    assert cfg.dry_run is True


def test_default_root_uses_parent_checkout_when_started_inside_worktree(tmp_path):
    primary = tmp_path / "repo"
    nested = primary / ".worktree" / "29" / "subdir"
    nested.mkdir(parents=True)

    assert default_root(nested) == primary
