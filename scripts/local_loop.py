#!/usr/bin/env python3
"""Run one local loop-engineering implementation cycle.

This is the local counterpart to the future GitHub Actions implement stage:
GitHub issues/labels remain the state machine, while Codex execution happens on
this machine so it can use the user's local authenticated Codex setup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_LOOP_REPO = "chunhualiao/co-scientist-loop"
DEFAULT_MAX_OPEN_LOOP_PRS = 2
PLAN_PROMPT_PATH = Path("docs/loop/prompts/plan.md")
IMPLEMENT_PROMPT_PATH = Path("docs/loop/prompts/implement.md")
SCORE_RE = re.compile(r"score\s*:\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    url: str
    labels: tuple[str, ...]

    @classmethod
    def from_gh(cls, data: dict[str, Any]) -> "Issue":
        return cls(
            number=int(data["number"]),
            title=str(data.get("title") or ""),
            body=str(data.get("body") or ""),
            url=str(data.get("url") or ""),
            labels=tuple(label["name"] for label in data.get("labels", []) if label.get("name")),
        )


@dataclass(frozen=True)
class IssueScore:
    value: int
    effort: int
    risk: int


@dataclass(frozen=True)
class LoopConfig:
    repo: str
    root: Path
    worktree_root: Path
    issue: int | None
    dry_run: bool
    max_open_loop_prs: int
    codex_bin: str
    codex_model: str | None
    codex_extra_args: tuple[str, ...]
    skip_codex: bool
    skip_validation: bool
    skip_pr: bool


class LoopError(RuntimeError):
    """Expected local-loop failure with a concise user-facing message."""


def default_root(start: Path | None = None) -> Path:
    """Return the primary checkout root, even when launched inside .worktree/N."""
    path = (start or Path.cwd()).resolve()
    parts = path.parts
    if ".worktree" in parts:
        index = parts.index(".worktree")
        if index > 0 and index + 1 < len(parts):
            return Path(*parts[:index])
    return path


class CommandRunner:
    """Small subprocess wrapper to keep shelling-out mockable in tests."""

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        print("+ " + shlex.join(args), flush=True)
        return subprocess.run(
            args,
            cwd=cwd,
            input=input_text,
            env=env,
            text=True,
            capture_output=capture_output,
            check=True,
        )

    def json(self, args: list[str], *, cwd: Path | None = None) -> Any:
        completed = self.run(args, cwd=cwd)
        return json.loads(completed.stdout or "null")


def parse_score(text: str) -> IssueScore:
    match = SCORE_RE.search(text or "")
    if not match:
        return IssueScore(value=3, effort=3, risk=3)
    value, effort, risk = (int(part) for part in match.groups())
    return IssueScore(value=value, effort=effort, risk=risk)


def issue_sort_key(issue: Issue) -> tuple[int, int, int, int]:
    score = parse_score(issue.body)
    # Highest value first, then lowest effort/risk, then oldest/smallest issue.
    return (-score.value, score.effort, score.risk, issue.number)


def select_issue(issues: list[Issue], requested: int | None = None) -> Issue:
    if requested is not None:
        for issue in issues:
            if issue.number == requested:
                return issue
        raise LoopError(f"Requested issue #{requested} is not open and loop-ready.")
    if not issues:
        raise LoopError("No open loop:ready issues found.")
    return sorted(issues, key=issue_sort_key)[0]


def shell_env_path(root: Path, worktree: Path) -> None:
    """Link ~/.env into a worktree when present; never read or print it."""
    home_env = Path.home() / ".env"
    if home_env.exists():
        target = worktree / ".env"
        if not target.exists():
            target.symlink_to(home_env)
        root_env = root / ".env"
        if not root_env.exists():
            root_env.symlink_to(home_env)


def current_branch(worktree: Path, runner: CommandRunner) -> str:
    completed = runner.run(["git", "-C", str(worktree), "branch", "--show-current"])
    branch = completed.stdout.strip()
    if not branch:
        raise LoopError(f"Could not determine branch in {worktree}")
    return branch


def open_loop_pr_count(repo: str, runner: CommandRunner) -> int:
    data = runner.json(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--label",
            "loop:auto",
            "--json",
            "number",
        ]
    )
    return len(data or [])


def fetch_ready_issues(repo: str, runner: CommandRunner) -> list[Issue]:
    data = runner.json(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--label",
            "loop:ready",
            "--limit",
            "50",
            "--json",
            "number,title,body,labels,url",
        ]
    )
    return [Issue.from_gh(item) for item in data]


def fetch_issue(repo: str, issue_number: int, runner: CommandRunner) -> Issue:
    data = runner.json(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repo,
            "--json",
            "number,title,body,labels,url",
        ]
    )
    issue = Issue.from_gh(data)
    if "loop:ready" not in issue.labels:
        raise LoopError(f"Issue #{issue_number} is not labeled loop:ready.")
    return issue


def ensure_worktree(config: LoopConfig, issue: Issue, runner: CommandRunner) -> Path:
    worktree = config.worktree_root / str(issue.number)
    if worktree.exists():
        shell_env_path(config.root, worktree)
        return worktree
    if config.dry_run:
        return worktree
    runner.run(["make", "wt", f"ISSUE={issue.number}"], cwd=config.root, capture_output=False)
    shell_env_path(config.root, worktree)
    return worktree


def claim_issue(config: LoopConfig, issue: Issue, runner: CommandRunner) -> None:
    if config.dry_run:
        print(f"DRY RUN: would claim issue #{issue.number}")
        return
    runner.run(
        [
            "gh",
            "issue",
            "edit",
            str(issue.number),
            "--repo",
            config.repo,
            "--remove-label",
            "loop:ready",
            "--add-label",
            "loop:in-progress",
        ]
    )


def read_prompt(root: Path, path: Path) -> str:
    prompt_path = root / path
    if not prompt_path.exists():
        raise LoopError(f"Missing prompt file: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def issue_context(issue: Issue) -> str:
    labels = ", ".join(issue.labels) or "(none)"
    return f"""# Issue context

- Repo issue: #{issue.number}
- Title: {issue.title}
- URL: {issue.url}
- Labels: {labels}

## Body

{issue.body}
"""


def run_codex(
    config: LoopConfig,
    worktree: Path,
    *,
    prompt: str,
    output_path: Path,
    read_only: bool,
    runner: CommandRunner,
) -> None:
    if config.skip_codex:
        print(f"SKIP CODEX: writing placeholder output to {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("Codex execution skipped by --skip-codex.\n", encoding="utf-8")
        return
    sandbox = "read-only" if read_only else "danger-full-access"
    args = [
        config.codex_bin,
        "exec",
        "--cd",
        str(worktree),
        "--sandbox",
        sandbox,
        "--ask-for-approval",
        "never",
        "--output-last-message",
        str(output_path),
    ]
    if config.codex_model:
        args.extend(["--model", config.codex_model])
    args.extend(config.codex_extra_args)
    args.append("-")
    runner.run(args, input_text=prompt, capture_output=False)


def build_plan_prompt(config: LoopConfig, issue: Issue) -> str:
    return "\n\n".join(
        [
            read_prompt(config.root, PLAN_PROMPT_PATH),
            issue_context(issue),
            "Plan only. Do not modify files. Produce a concise Markdown plan.",
        ]
    )


def build_implement_prompt(config: LoopConfig, issue: Issue, plan_text: str) -> str:
    return "\n\n".join(
        [
            read_prompt(config.root, IMPLEMENT_PROMPT_PATH),
            issue_context(issue),
            "# Approved local plan\n\n" + plan_text,
        ]
    )


def comment_issue(repo: str, issue: Issue, body: str, runner: CommandRunner, *, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY RUN: would comment on issue #{issue.number}:\n{body[:1000]}")
        return
    completed = runner.run(
        ["gh", "issue", "comment", str(issue.number), "--repo", repo, "--body-file", "-"], input_text=body
    )
    print(completed.stdout.strip())


def validate_worktree(worktree: Path, runner: CommandRunner, *, skip_validation: bool) -> str:
    if skip_validation:
        return "Validation skipped by --skip-validation."
    runner.run(["make", "lint"], cwd=worktree, capture_output=False)
    runner.run(["make", "test"], cwd=worktree, capture_output=False)
    return "- `make lint`\n- `make test`"


def changed_files(worktree: Path, runner: CommandRunner) -> list[str]:
    completed = runner.run(["git", "-C", str(worktree), "status", "--porcelain"])
    return [line for line in completed.stdout.splitlines() if line.strip()]


def commit_changes(worktree: Path, issue: Issue, runner: CommandRunner) -> None:
    if not changed_files(worktree, runner):
        raise LoopError("Codex finished but produced no working-tree changes.")
    runner.run(["git", "-C", str(worktree), "add", "-A"])
    runner.run(["git", "-C", str(worktree), "commit", "-m", f"Implement loop issue #{issue.number}: {issue.title}"])


def risk_label(issue: Issue) -> str:
    if "meta:loop" in issue.labels:
        return "risk:high"
    return "risk:medium"


def pr_body(issue: Issue, plan_text: str, validation: str) -> str:
    return f"""Fixes #{issue.number}

## Summary

Implemented the changes requested by `{issue.title}`.

## Plan

{plan_text.strip()}

## Validation

{validation}
"""


def open_or_update_pr(config: LoopConfig, worktree: Path, issue: Issue, validation: str, runner: CommandRunner) -> str:
    branch = current_branch(worktree, runner)
    if config.skip_pr:
        return f"PR creation skipped by --skip-pr for branch `{branch}`."
    existing = runner.json(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            config.repo,
            "--state",
            "open",
            "--head",
            branch,
            "--json",
            "number,url",
        ]
    )
    if existing:
        return str(existing[0]["url"])

    body_path = worktree / ".loop" / "pr-body.md"
    plan_path = worktree / ".loop" / "plan.md"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(pr_body(issue, plan_path.read_text(encoding="utf-8"), validation), encoding="utf-8")

    runner.run(["git", "-C", str(worktree), "push", "-u", "origin", branch], capture_output=False)
    completed = runner.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            config.repo,
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            issue.title,
            "--body-file",
            str(body_path),
        ]
    )
    url = completed.stdout.strip().splitlines()[-1]
    runner.run(
        ["gh", "pr", "edit", url, "--repo", config.repo, "--add-label", "loop:auto", "--add-label", risk_label(issue)]
    )
    return url


def run_once(config: LoopConfig, runner: CommandRunner | None = None) -> int:
    runner = runner or CommandRunner()
    open_prs = open_loop_pr_count(config.repo, runner)
    if open_prs >= config.max_open_loop_prs:
        raise LoopError(f"Open loop PR throttle hit: {open_prs} >= {config.max_open_loop_prs}")

    if config.issue is None:
        issue = select_issue(fetch_ready_issues(config.repo, runner))
    else:
        issue = fetch_issue(config.repo, config.issue, runner)

    score = parse_score(issue.body)
    print(f"Selected issue #{issue.number}: {issue.title} (score:{score.value}/{score.effort}/{score.risk})")
    worktree = ensure_worktree(config, issue, runner)
    if config.dry_run:
        print(f"DRY RUN: would use worktree {worktree}")
        print(f"DRY RUN: would run plan + implement prompts with {config.codex_bin}")
        return 0

    claim_issue(config, issue, runner)
    loop_dir = worktree / ".loop"
    loop_dir.mkdir(parents=True, exist_ok=True)

    plan_path = loop_dir / "plan.md"
    run_codex(
        config,
        worktree,
        prompt=build_plan_prompt(config, issue),
        output_path=plan_path,
        read_only=True,
        runner=runner,
    )
    plan_text = plan_path.read_text(encoding="utf-8")
    comment_issue(config.repo, issue, "## Local loop plan\n\n" + plan_text, runner, dry_run=False)

    run_codex(
        config,
        worktree,
        prompt=build_implement_prompt(config, issue, plan_text),
        output_path=loop_dir / "implement-last-message.md",
        read_only=False,
        runner=runner,
    )
    validation = validate_worktree(worktree, runner, skip_validation=config.skip_validation)
    commit_changes(worktree, issue, runner)
    pr_url = open_or_update_pr(config, worktree, issue, validation, runner)
    print(f"Local loop completed issue #{issue.number}: {pr_url}")
    return 0


def parse_args(argv: list[str] | None = None) -> LoopConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.getenv("LOOP_REPO", DEFAULT_LOOP_REPO))
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root(),
        help="Primary checkout root; defaults to parent checkout when run inside .worktree/<issue>",
    )
    parser.add_argument("--worktree-root", type=Path, default=Path(".worktree"))
    parser.add_argument("--issue", type=int, help="Run a specific loop:ready issue instead of auto-selecting")
    parser.add_argument(
        "--dry-run", action="store_true", help="Select and report the next issue without mutating state"
    )
    parser.add_argument("--max-open-loop-prs", type=int, default=DEFAULT_MAX_OPEN_LOOP_PRS)
    parser.add_argument("--codex-bin", default=os.getenv("CODEX_BIN", "codex"))
    parser.add_argument("--codex-model", default=os.getenv("CODEX_MODEL"))
    parser.add_argument("--codex-arg", action="append", default=[], help="Extra argument passed to codex exec")
    parser.add_argument("--skip-codex", action="store_true", help="Testing/debug: do not invoke Codex")
    parser.add_argument("--skip-validation", action="store_true", help="Testing/debug: skip make lint/test")
    parser.add_argument("--skip-pr", action="store_true", help="Testing/debug: do not push or create a PR")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    worktree_root = args.worktree_root
    if not worktree_root.is_absolute():
        worktree_root = root / worktree_root
    return LoopConfig(
        repo=args.repo,
        root=root,
        worktree_root=worktree_root,
        issue=args.issue,
        dry_run=args.dry_run,
        max_open_loop_prs=args.max_open_loop_prs,
        codex_bin=args.codex_bin,
        codex_model=args.codex_model,
        codex_extra_args=tuple(args.codex_arg),
        skip_codex=args.skip_codex,
        skip_validation=args.skip_validation,
        skip_pr=args.skip_pr,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        return run_once(parse_args(argv))
    except subprocess.CalledProcessError as exc:
        print(f"Command failed ({exc.returncode}): {shlex.join(exc.cmd)}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return exc.returncode or 1
    except LoopError as exc:
        print(f"local-loop: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
