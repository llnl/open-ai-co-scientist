# AGENTS.md — standing instructions for AI coding agents

This is the **private loop repo** for Open AI Co-Scientist (a Gradio app that
generates, reviews, ranks, and evolves research hypotheses via OpenRouter
LLMs). The autonomous-development process is specified in
`docs/loop-engineering-design.md`; current priorities live in
`docs/loop/GOALS.md`. Only human-vetted sync branches ever reach the public
`llnl/open-ai-co-scientist` repo.

## Project map

- `app.py` — Gradio UI entry point (`create_gradio_interface()`); note the
  `app/` package shadows it on `import app`, so load it via importlib when
  testing (see `tests/test_gradio.py`).
- `app/agents.py` — multi-agent pipeline (Generation, Reflection, Ranking,
  Evolution, Proximity, Meta-review) and LLM-call wrappers.
- `app/utils.py` — `call_llm` (OpenRouter via OpenAI SDK), similarity scoring,
  vis.js graph data, logging, `redact_secrets`.
- `app/models.py` — pydantic models. `app/config.py` + `config.yaml` — config.
- `app/tools/arxiv_search.py` — arXiv literature integration.
- `tests/` — offline by default; `integration` (paid LLM) and `network`
  (free network) markers are excluded unless you run `make test-all`.

## Canonical commands

- `make test` — offline suite; **must always pass with no API key and no
  network**. Run it before finishing any change.
- `make test-all` — includes `integration` + `network` tests (needs
  `OPENROUTER_API_KEY`, spends money — do not run unless asked).
- `make lint` / `make fmt` — ruff check / auto-format.

## Rules

- API keys come **only** from the environment (`.env`, gitignored; template in
  `.env.example`). Never write a key into code, tests, `config.yaml`, or logs;
  error text and log lines must pass through `redact_secrets` if they could
  contain one.
- Never commit: secrets, `.env`, `results/`, `venv`, `.worktree/`, `.audit/`.
- **Never add AI attribution to commits or PRs** — no `Co-Authored-By`, no
  session links, no "Generated with ..." footers.
- Match existing code style; keep diffs minimal and scoped to the task.
- New or changed behavior needs a test in the offline suite (mock the LLM
  boundary at `app.utils.OpenAI` or `app.agents.call_llm`).

## Worktree protocol (local sessions)

When working on issue N locally: work inside the worktree `.worktree/N` on
branch `loop/issue-N` (create with `make wt ISSUE=N`); never work directly on
`main`'s checkout; never modify files outside your own worktree; remove the
worktree after the PR merges (`make wt-clean ISSUE=N`).

## Pull request follow-up

When the user asks to create/open PRs, create **ready-for-review PRs by
default**. Do not create draft PRs unless the user explicitly asks for a draft
or the PR is intentionally blocked/incomplete; if you must use draft, say why
before handing off. The goal is to avoid unnecessary friction in human review
and merge flow.

After opening a pull request, wait briefly for automated review comments from
the `chatgpt-codex-connector` bot. Check the PR review threads/comments, address
actionable feedback with follow-up commits when needed, rerun the relevant
checks, and push the fixes before handing off. If no bot review arrives within a
reasonable wait or the comments are non-actionable, say that explicitly in the
handoff.
