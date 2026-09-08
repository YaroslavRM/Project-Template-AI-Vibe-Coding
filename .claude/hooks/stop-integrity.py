#!/usr/bin/env python3
"""Stop hook: run the integrity check and hand the result back to the agent.

Registered in .claude/settings.json.

Two things the previous one-liner got wrong:

* Only exit code 2 blocks the stop and shows stderr to the agent. Exiting 1
  produced an error the agent never saw, so a broken template stayed broken.
* `cmd || fallback` branches on the exit status, not on whether the
  interpreter exists — so a failing check ran twice instead of falling back.

The `stop_hook_active` guard is not optional. Without it a hook that keeps
exiting 2 will spin the agent until the session times out.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TIMEOUT = 120


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    # Already blocked once this turn: let the agent stop, or it never can.
    if payload.get("stop_hook_active"):
        return 0

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    script = root / "scripts" / "check-template.py"
    if not script.is_file():
        print(
            "scripts/check-template.py is missing. Do not recreate it from memory — "
            "restore it from git and tell the owner.",
            file=sys.stderr,
        )
        return 2

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root), capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"could not run the integrity check: {exc}", file=sys.stderr)
        return 2

    if result.returncode == 0:
        return 0

    print(
        "The template integrity check is failing. Do not finish the session on this.\n"
        "Report the output below to the owner verbatim and stop.\n\n"
        + (result.stdout or "") + (result.stderr or ""),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
