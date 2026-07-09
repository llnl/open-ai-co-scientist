# Makefile for AI Co-Scientist (canonical commands — see AGENTS.md)

# Tools resolve from ./venv when present (local dev), else from PATH (CI).
PYTEST := $(shell test -x venv/bin/pytest && echo venv/bin/pytest || echo pytest)
RUFF := $(shell test -x venv/bin/ruff && echo venv/bin/ruff || echo ruff)
PYTHON := $(shell test -x venv/bin/python && echo venv/bin/python || echo python)
VENV_PYTHON ?= python3.12

run:
	@echo "Starting AI Co-Scientist Gradio app on port 7860..."
	python app.py

test:
	$(PYTEST)

test-all:
	$(PYTEST) -m ""

lint:
	$(RUFF) check .
	$(RUFF) format --check .

fmt:
	$(RUFF) format .
	$(RUFF) check --fix .

# Per-issue worktree helpers (design doc §4 "Where stages execute").
# Usage: make wt ISSUE=36 / make wt-clean ISSUE=36
wt:
	@test -n "$(ISSUE)" || (echo "Usage: make wt ISSUE=<number>" && exit 1)
	git worktree add .worktree/$(ISSUE) -b loop/issue-$(ISSUE) origin/main
	cd .worktree/$(ISSUE) && $(VENV_PYTHON) -m venv venv \
		&& ./venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt
	@if [ -f .env ]; then ln -sf ../../.env .worktree/$(ISSUE)/.env; fi
	@echo "Worktree ready: .worktree/$(ISSUE) (branch loop/issue-$(ISSUE))"

wt-clean:
	@test -n "$(ISSUE)" || (echo "Usage: make wt-clean ISSUE=<number>" && exit 1)
	git worktree remove .worktree/$(ISSUE)
	git worktree prune

loop-once:
	$(PYTHON) scripts/local_loop.py

loop-dry-run:
	$(PYTHON) scripts/local_loop.py --dry-run

.PHONY: run test test-all lint fmt wt wt-clean loop-once loop-dry-run
