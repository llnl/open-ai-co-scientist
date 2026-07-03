# Upstream Release and Hugging Face Deployment Runbook

This runbook explains how approved work from the private loop repo reaches the
public `llnl/open-ai-co-scientist` repo and then deploys to Hugging Face Spaces.
It is the operator-facing version of the architecture in
`docs/loop-engineering-design.md`.

## Repositories and Branches

| Location | Purpose | Merge authority |
|---|---|---|
| `chunhualiao/co-scientist-loop` | Private loop repo. Automation, loop PRs, secrets, audit trails, and local worktrees live here. | Loop policy plus human review according to risk class. |
| `llnl/open-ai-co-scientist` | Public upstream repo. Only vetted sync branches from the loop repo land here. | Human only. |
| Hugging Face Space | Public demo runtime. It should deploy only from a public upstream release or an explicitly approved manual sync. | Human until the loop reaches the deployment graduation gate. |

Use these remotes in local clones and worktrees:

```bash
git remote -v
# origin   git@github.com:chunhualiao/co-scientist-loop.git
# upstream git@github.com:llnl/open-ai-co-scientist.git
```

Local issue work happens in `.worktree/<issue-number>` on
`loop/issue-<issue-number>`, for example:

```bash
make wt ISSUE=7
cd .worktree/7
```

## End-to-End Flow

1. Loop or local Codex work opens PRs inside `chunhualiao/co-scientist-loop`.
2. Each loop PR must pass the offline CI gate: `make lint`, `make test`, and
   the app boot smoke test.
3. Approved loop PRs merge into the private loop repo's `main`.
4. A sync branch is prepared from private `main` and pushed to the public
   upstream repo as `sync/vX.Y` or another explicit release branch name.
5. A public PR is opened inside `llnl/open-ai-co-scientist` from that sync
   branch into `main`.
6. The public upstream PR runs public CI and receives the final human review.
7. The upstream PR is merged with a merge commit, not squash, so the private
   and public histories remain easy to compare.
8. The upstream merge is tagged as a release candidate or release.
9. Hugging Face deploys from the upstream release path after the deployment
   checks pass.

## Automation Created for This Process

The process is implemented by these files:

| File | Purpose |
|---|---|
| `.github/workflows/upstream-sync.yml` | Manual workflow that prepares a public upstream sync PR. It defaults to dry-run mode and uploads the generated PR body as an artifact. |
| `.github/workflows/huggingface-deploy.yml` | Release-tag and manual workflow that runs lint, offline tests, an app boot smoke test, then deploys to the Hugging Face Space. |
| `scripts/prepare_upstream_release.py` | Testable helper used by the sync workflow to validate release versions, compute the sync branch, collect commit summaries, and generate the upstream PR body. |
| `tests/test_release_process.py` | Offline tests for release-helper behavior and workflow safety invariants. |

Required GitHub configuration:

| Name | Type | Repository | Purpose |
|---|---|---|---|
| `UPSTREAM_SYNC_TOKEN` | Secret | Private loop repo | Fine-grained GitHub token that can push sync branches to `llnl/open-ai-co-scientist` and open PRs there. |
| `HF_TOKEN` | Secret | Public upstream repo, if CI/CD deploy is enabled there | Least-privilege Hugging Face token for pushing release files to the Space repo. |
| `HF_SPACE_ID` | Variable | Public upstream repo, if CI/CD deploy is enabled there | Hugging Face Space id, for example `liaoch/open-ai-co-scientist`. |

The workflows intentionally do not use `pull_request_target`, and both declare
only `contents: read` repository permissions. Write access is provided only by
the explicit external token needed for the target system.

## Preparing a Public Sync PR

Before preparing the sync branch, make sure the private loop repo is clean and
current:

```bash
git checkout main
git fetch origin upstream
git pull --ff-only origin main
git log --oneline upstream/main..origin/main
```

Review the commits that will become public. The sync diff is the publication
gate, so check for accidental secrets, private notes, raw trails, generated
artifacts, and anything under `results/`, `.env`, `.worktree/`, or `.audit/`.

Create and push the sync branch to the public repo:

```bash
VERSION=v0.1.0
git switch -c sync/$VERSION origin/main
git push upstream sync/$VERSION
```

Open the PR in the upstream repo:

```bash
gh pr create \
  --repo llnl/open-ai-co-scientist \
  --base main \
  --head sync/$VERSION \
  --title "Release $VERSION from loop repo" \
  --body-file /tmp/upstream-sync-pr.md
```

Or run the manual `Upstream Sync PR` workflow:

1. Set `version` to the intended release tag, for example `v0.1.0`.
2. Keep `dry_run=true` first and review the uploaded PR body artifact.
3. Re-run with `dry_run=false` only after the dry-run output is correct and
   `UPSTREAM_SYNC_TOKEN` is configured.

The PR body should include:

- the list of loop PRs or issue numbers included in the batch;
- `Fixes #N` lines for upstream issues that should close on merge;
- test evidence from the private loop repo and the public upstream CI run;
- any deployment notes for Hugging Face;
- confirmation that no secrets, private trails, or generated run outputs are
  included.

## Upstream CI Gate

The public upstream PR should run the same no-key, no-network offline gate used
by the private loop repo:

```bash
make lint
make test
```

The GitHub Actions workflow also performs an app boot smoke test. Do not deploy
to Hugging Face from a sync branch whose upstream CI is red or pending unless
the failure is explicitly understood and documented in the PR.

## Release Tagging

After the upstream PR merges, tag the upstream merge commit. Use annotated tags
for releases:

```bash
git fetch upstream
git checkout main
git pull --ff-only upstream main
git tag -a v0.1.0 -m "Release v0.1.0"
git push upstream v0.1.0
```

The tag is the stable deployment input for Hugging Face and for benchmark or
release-note workflows. If the public PR is only a release candidate, use an
`rc` suffix and avoid updating the production Space until it passes the live
smoke test.

## Hugging Face Deployment

There are two supported deployment modes.

### Manual Deployment

Use manual deployment while autonomy is still at Level 0 or Level 1 in
`docs/loop/GOALS.md`.

1. Merge and tag the upstream release.
2. Confirm the Hugging Face Space has `OPENROUTER_API_KEY` set as a secret.
3. Confirm the Space is configured for the Gradio app entrypoint `app.py`.
4. Push or mirror the tagged upstream tree to the Space repo.
5. Watch the Space build logs until the app starts successfully.
6. Run a live smoke test with a free or budget-capped OpenRouter model.

### CI/CD Deployment

Enable CI/CD deployment only after the loop has earned the deployment gate
described in `docs/loop-engineering-design.md`: public upstream CI is green,
sync PRs have been clean, and live smoke tests are reliable.

The recommended workflow is:

1. Trigger only on upstream release tags such as `v*`, not on every private
   loop merge.
2. Check out the exact upstream tag.
3. Run `make lint` and `make test` without API keys.
4. Run the app boot smoke test.
5. Push the release tree to the Hugging Face Space repo using a
   least-privilege Hugging Face token.
6. Poll or inspect the Space build status.
7. Run a post-deploy smoke test against the public Space with a free model.
8. Fail loudly and open an issue if the Space build or smoke test fails.

The `Hugging Face Deploy` workflow implements steps 1 through 5. Post-deploy
live smoke testing remains a required follow-up until a budget-capped smoke
test workflow is added.

Keep Hugging Face deployment secrets separate from OpenRouter spending secrets:

| Secret | Stored in | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Hugging Face Space secret | Runtime model access for the public demo. |
| `HF_TOKEN` | Public upstream GitHub Actions secret, if CI/CD is enabled | Push release files to the Space repo. |
| `OPENROUTER_API_KEY` for CI | Private loop repo GitHub Actions secret | Nightly or pre-deploy live smoke tests only. |

Do not expose the production OpenRouter key to PR workflows, fork workflows, or
loop jobs that do not need live model access.

## Rollback

If the upstream release is bad but the Hugging Face app is still on the
previous working revision, stop and leave it there. Revert in Git first.

If the bad release is already deployed:

1. Pause any automatic deploy workflow.
2. Revert the public upstream merge or push the previous good tag to the Space.
3. Confirm the Space rebuilds successfully.
4. Run the live smoke test.
5. Open a private loop issue describing the regression and link the upstream
   PR, release tag, Space build, and rollback commit.

Do not patch the Hugging Face Space directly except as a temporary emergency
measure. Any emergency Space-only fix must be backported to the private loop
repo and upstream release path before normal deployment resumes.

## Current Policy

Until the loop reaches the documented graduation level for deployment, Hugging
Face deployment remains manually approved. The loop may prepare sync branches,
release notes, and deployment PRs, but a human reviews the upstream diff and
authorizes the production Space update.
