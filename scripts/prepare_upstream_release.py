#!/usr/bin/env python3
"""Prepare a private-loop to public-upstream release sync."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+(?:[-.](?:rc|alpha|beta)\d*)?$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISSUE_RE = re.compile(r"(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class ReleasePlan:
    version: str
    upstream_repo: str
    base_branch: str
    head_ref: str
    sync_branch: str
    commit_lines: tuple[str, ...]


def validate_version(version: str) -> str:
    """Return a normalized release version or raise ValueError."""
    version = version.strip()
    if not VERSION_RE.fullmatch(version):
        raise ValueError("version must look like vMAJOR.MINOR.PATCH, optionally with -rcN")
    return version


def sync_branch_for(version: str) -> str:
    return f"sync/{validate_version(version)}"


def validate_repo(repo: str) -> str:
    repo = repo.strip()
    if not REPO_RE.fullmatch(repo):
        raise ValueError("repository must look like owner/name")
    return repo


def extract_issue_numbers(lines: list[str] | tuple[str, ...]) -> list[str]:
    """Extract unique GitHub issue numbers from commit/PR text, preserving order."""
    seen: set[str] = set()
    issues: list[str] = []
    for line in lines:
        for issue in ISSUE_RE.findall(line):
            if issue not in seen:
                seen.add(issue)
                issues.append(issue)
    return issues


def build_pr_body(plan: ReleasePlan) -> str:
    issue_numbers = extract_issue_numbers(plan.commit_lines)
    commits = "\n".join(f"- `{line}`" for line in plan.commit_lines) or "- No commits listed."
    fixes = "\n".join(f"Fixes #{issue}" for issue in issue_numbers) or "_No upstream issues auto-closed._"

    return f"""## Summary

Release {plan.version} from the private loop repo to `{plan.upstream_repo}`.

## Included Commits

{commits}

## Upstream Issue Links

{fixes}

## Validation Required Before Merge

- [ ] Public upstream CI is green.
- [ ] Sync diff was reviewed for secrets, private trails, generated outputs, and accidental local files.
- [ ] `results/`, `.env`, `.worktree/`, and `.audit/` are absent from the public diff.
- [ ] Hugging Face deployment notes are understood before tagging/deploying.

## Deployment

After this PR merges with a merge commit, tag the upstream merge commit as `{plan.version}`.
That tag is the input for Hugging Face deployment.
"""


def run_git(args: list[str]) -> str:
    completed = subprocess.run(["git", *args], check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def collect_commit_lines(base_ref: str, head_ref: str) -> tuple[str, ...]:
    output = run_git(["log", "--oneline", f"{base_ref}..{head_ref}"])
    return tuple(line for line in output.splitlines() if line.strip())


def build_plan(args: argparse.Namespace) -> ReleasePlan:
    version = validate_version(args.version)
    commit_lines = tuple(args.commit) if args.commit else collect_commit_lines(args.base_ref, args.head_ref)
    return ReleasePlan(
        version=version,
        upstream_repo=validate_repo(args.upstream_repo),
        base_branch=args.base_branch,
        head_ref=args.head_ref,
        sync_branch=args.sync_branch or sync_branch_for(version),
        commit_lines=commit_lines,
    )


def write_github_output(plan: ReleasePlan, body_path: Path) -> None:
    output_env = os.environ.get("GITHUB_OUTPUT")
    if not output_env:
        return
    output_path = Path(output_env)
    with output_path.open("a", encoding="utf-8") as fh:
        fh.write(f"version={plan.version}\n")
        fh.write(f"sync_branch={plan.sync_branch}\n")
        fh.write(f"body_file={body_path}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Release version, for example v0.1.0")
    parser.add_argument("--upstream-repo", default="llnl/open-ai-co-scientist")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--base-ref", default="upstream/main")
    parser.add_argument("--head-ref", default="origin/main")
    parser.add_argument("--sync-branch", help="Override the sync branch name")
    parser.add_argument("--body-file", type=Path, default=Path("upstream-sync-pr.md"))
    parser.add_argument(
        "--commit",
        action="append",
        default=[],
        help="Commit summary line. Repeat in tests or dry runs to avoid calling git log.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_plan(args)
    body = build_pr_body(plan)
    args.body_file.write_text(body, encoding="utf-8")
    write_github_output(plan, args.body_file)
    print(f"Prepared {plan.sync_branch} for {plan.upstream_repo}; PR body: {args.body_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
