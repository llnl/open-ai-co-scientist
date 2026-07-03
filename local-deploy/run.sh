#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$APP_DIR/logs"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting local Open AI Co-Scientist deployment"

  git fetch origin "$DEPLOY_BRANCH"
  current_branch="$(git branch --show-current)"
  if [ "$current_branch" = "$DEPLOY_BRANCH" ]; then
    git pull --ff-only origin "$DEPLOY_BRANCH"
  else
    echo "Current branch is $current_branch; fetched origin/$DEPLOY_BRANCH but skipped pull."
  fi

  if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$APP_DIR/venv"
  fi

  "$APP_DIR/venv/bin/python" -m pip install --upgrade pip
  "$APP_DIR/venv/bin/pip" install -r requirements.txt

  if [ -f "$APP_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$APP_DIR/.env"
    set +a
  fi

  export GRADIO_ANALYTICS_ENABLED="${GRADIO_ANALYTICS_ENABLED:-False}"
  exec "$APP_DIR/venv/bin/python" app.py
} >> "$LOG_DIR/local-deploy.log" 2>&1
