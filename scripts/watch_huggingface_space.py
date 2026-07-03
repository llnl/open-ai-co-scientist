#!/usr/bin/env python3
"""Poll a Hugging Face Space until deployment succeeds or fails."""

from __future__ import annotations

import argparse
import os
import time
from typing import Protocol

from huggingface_hub import HfApi

SUCCESS_STAGES = {"RUNNING"}
FAILURE_STAGES = {
    "BUILD_ERROR",
    "CONFIG_ERROR",
    "NO_APP_FILE",
    "RUNTIME_ERROR",
    "DELETING",
    "PAUSED",
    "STOPPED",
}


class RuntimeClient(Protocol):
    def get_space_runtime(self, repo_id: str, *, token: str | None = None):
        """Return a Hugging Face Space runtime object."""


def stage_name(runtime) -> str:
    """Normalize Hugging Face runtime stages across client versions."""
    stage = runtime.stage
    return getattr(stage, "value", str(stage))


def watch_space(
    space_id: str,
    *,
    token: str | None = None,
    timeout_seconds: int = 900,
    poll_seconds: int = 15,
    client: RuntimeClient | None = None,
) -> str:
    """Return the successful stage or raise RuntimeError/TimeoutError."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")

    api = client or HfApi()
    deadline = time.monotonic() + timeout_seconds
    last_stage = "UNKNOWN"

    while time.monotonic() < deadline:
        runtime = api.get_space_runtime(space_id, token=token)
        last_stage = stage_name(runtime)
        print(f"Hugging Face Space {space_id} stage: {last_stage}", flush=True)

        if last_stage in SUCCESS_STAGES:
            return last_stage
        if last_stage in FAILURE_STAGES:
            raise RuntimeError(f"Hugging Face Space {space_id} failed with stage {last_stage}")

        time.sleep(poll_seconds)

    raise TimeoutError(
        f"Hugging Face Space {space_id} did not reach RUNNING within "
        f"{timeout_seconds} seconds; last stage was {last_stage}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space-id", default=os.environ.get("HF_SPACE_ID"), help="Space id, for example user/name")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=15)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.space_id:
        raise SystemExit("HF_SPACE_ID or --space-id is required")
    watch_space(
        args.space_id,
        token=os.environ.get("HF_TOKEN"),
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
