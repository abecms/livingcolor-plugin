"""Block expensive evaluation pipelines during FAST DEV implementation phases."""

from __future__ import annotations

import sys

from delivery_runtime.fast_dev.mode import is_fast_dev_mode, is_truthy_env

FAST_DEV_BLOCK_MESSAGE = """\
LivingColor FAST DEV mode is enabled (LIVINGCOLOR_FAST_DEV=true).

Expensive validation runs are disabled during active implementation phases.
Use targeted smoke tests instead:

  export LIVINGCOLOR_FAST_DEV=true
  scripts/run_fast_dev_smoke.sh

To run this evaluation anyway, disable FAST DEV or pass --force-full-eval.
"""


def assert_full_evaluation_allowed(*, script_name: str, force: bool = False) -> None:
    """Exit early when FAST DEV mode blocks full evaluation CLIs."""
    if force or not is_fast_dev_mode():
        return
    if is_truthy_env("LIVINGCOLOR_FORCE_FULL_EVAL"):
        return
    sys.stderr.write(f"{FAST_DEV_BLOCK_MESSAGE}\nBlocked script: {script_name}\n")
    raise SystemExit(3)
