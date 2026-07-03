# GOALS — human-owned steering file for the loop

<!-- Edit this file to steer the loop; triage scores issue value against it.
     See docs/loop-engineering-design.md §7. -->

graduation-level: 0        <!-- all PRs human-merged; see §7 graduation ladder -->
metric-version: pre-0      <!-- benchmark harness not yet built (§7.2) -->

## North star

A **stable public demo** on Hugging Face Spaces that reliably produces ranked
hypotheses even when free models churn; **persistent storage** (upstream #18)
is the next major feature.

## Current themes (ranked)

1. **Demo reliability** — graceful handling of model failures and delistings
   (upstream #26, #30, #36); errors must be actionable, never silent.
2. **Persistent storage + shareable results** — upstream #18 and #32; the
   §8.2 run-report work doubles as #32.
3. **Hypothesis quality measurement** — upstream #29; becomes the §7.1
   benchmark harness.

## Non-goals (for now)

- Docker deployment (upstream #34)
- pip packaging (upstream #14)
- Wrapping the system as an MCP server (upstream #15)
