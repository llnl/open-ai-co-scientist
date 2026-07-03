#!/usr/bin/env bash
# One-shot, idempotent creation of the loop's label state machine
# (docs/loop-engineering-design.md §3). Run against the private loop repo:
#   ./scripts/setup_labels.sh [owner/repo]
set -euo pipefail

REPO="${1:-chunhualiao/co-scientist-loop}"

label() { gh label create "$1" --repo "$REPO" --description "$2" --color "$3" --force; }

# Issue lifecycle
label "loop:triaged"          "Scored and groomed; has acceptance criteria"                        "c5def5"
label "loop:ready"            "Approved for autonomous implementation"                             "0e8a16"
label "loop:in-progress"      "An implementation run owns this issue"                              "fbca04"
label "loop:blocked"          "Loop failed >=2 attempts; needs human"                              "d93f0b"
label "needs-human"           "Requires a human decision (scope, direction, spending)"             "b60205"
label "loop:wontfix-proposed" "Triage proposes closing; auto-closes after 7 days unless objected"  "cfd3d7"
label "meta:loop"             "Work on the loop itself, not the product (meta-work ratio)"         "5319e7"
label "stale-decision"        "needs-human item ignored >30 days; loop routes around it"           "e4e669"
label "opsec:hold"            "Held from public release pending publish/scrub/keep-private call"   "000000"

# PR labels
label "loop:auto"             "Created by the loop"                                                "1d76db"
label "risk:low"              "Auto-merge eligible when CI green + AI review approves"             "0e8a16"
label "risk:medium"           "AI-approved; human merges (one click)"                              "fbca04"
label "risk:high"             "Human review required; AI review advisory"                          "d93f0b"
label "ci:live"               "Run live-API test tiers against this PR (same-repo branches only)"  "006b75"

echo "Labels ensured on $REPO"
