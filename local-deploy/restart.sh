#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="${OACS_LAUNCHD_LABEL:-com.liao.open-ai-co-scientist.local}"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
URL="${OACS_LOCAL_URL:-http://127.0.0.1:7860}"

if ! launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
  if [ ! -f "$PLIST" ]; then
    "$SCRIPT_DIR/install-launchagent.sh"
  fi
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
fi

launchctl kickstart -k "gui/$(id -u)/${LABEL}"

printf 'Restarted Open AI Co-Scientist local test instance.\n'
printf 'Open or refresh: %s\n' "$URL"
