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

# The console's code page, not this script's own choice, decided the output
# encoding before this: cp1251 on a default Windows terminal. That silently
# mangled every non-ASCII character in these messages into mojibake for every
# reader downstream (MinTTY, the agent's own tool output, the other check
# script that decodes this one's stdout as UTF-8) and, worse, crashed with
# UnicodeEncodeError the moment a printed line held a character outside
# cp1251 — which skipped whatever check was about to print it. See
# README.md, section Windows.
for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8", errors="replace")
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

    # Fall back to this file's own location, not to the current directory.
    # The hook lives in .claude/hooks/, so the project root is two levels up
    # and is knowable without the environment. Falling back to "." produced the
    # worst possible failure: with the variable unset and the process started
    # anywhere else, the check reported "check-template.py is missing", which
    # reads as "somebody deleted the checker" rather than "wrong directory".
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    root = Path(env_root).resolve() if env_root else Path(__file__).resolve().parents[2]
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
            # This decodes the child's stdout/stderr as UTF-8. That only
            # helps once the child itself writes UTF-8 (see the reconfigure
            # call near the top of this file and of the check scripts) —
            # decoding as UTF-8 a stream the child wrote in the console's own
            # code page (cp1251 on a default Windows terminal) is what
            # produced the replacement characters, not what fixed them.
            # errors="replace" is kept as a safety net for a genuine mismatch,
            # not as the fix.
            encoding="utf-8", errors="replace",
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
