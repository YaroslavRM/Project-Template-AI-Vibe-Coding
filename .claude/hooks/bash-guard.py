#!/usr/bin/env python3
"""PreToolUse guard for Bash commands.

Registered in .claude/settings.json. Exit code 2 blocks the call and hands the
message back to the agent.

Why a hook and not more deny rules: a Bash permission rule matches the text of
the command, so it is dodged by reordering flags, adding `./`, changing the
working directory first, or using the short form of a flag. And Read/Edit deny
rules do not reach Bash subprocesses at all — `Read(./.env)` blocks the Read
tool, not `head .env`. This hook looks at the command that is actually about
to run.

It is still not a sandbox. It closes the paths that are easy to walk into by
accident. The primary boundary remains the text of RulesForAIVibeCoding.md.
"""
from __future__ import annotations

import json
import re
import sys

ALLOWED_ENV_FILES = {".env.example", ".env.sample", ".env.template", ".env.dist"}
ENV_TOKEN = re.compile(r"\.env[A-Za-z0-9_.-]*")

RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bgit\s+commit\b(?=(?:[^\n]*\s)(?:--no-verify|-n)\b)"),
        "git commit with --no-verify (or -n) skips the commit-msg and pre-commit "
        "hooks. If a hook is in the way, say which one and why — do not bypass it.",
    ),
    (
        re.compile(r"\bgit\s+push\b(?=(?:[^\n]*\s)(?:--force|-f)\b)"),
        "force push rewrites history. Rules, section Environments: irreversible "
        "actions are the owner's call.",
    ),
    (
        re.compile(r"\bgit\s+-c\s+core\.hooksPath"),
        "overriding core.hooksPath for one command disables the hooks for that "
        "command. Same answer as --no-verify: say what is in the way.",
    ),
    (
        re.compile(r"\bgit\s+config\b[^\n]*\bcore\.hooksPath\b(?![^\n]*\.githooks)"),
        "core.hooksPath must stay pointed at .githooks.",
    ),
    (
        re.compile(r"check-template\.py[^\n]*--fix|--fix[^\n]*check-template\.py"),
        "--fix rewrites the integrity baseline. That flag belongs to the owner, "
        "in a terminal, in the same commit as the change it legitimises.",
    ),
    (
        re.compile(r"\brm\s+(-[A-Za-z]*[rf][A-Za-z]*\s+)+"),
        "recursive or forced delete. Name what you want removed and why, and let "
        "the owner run it.",
    ),
    (
        re.compile(r"\bgit\s+(reset\s+--hard|clean\s+-[A-Za-z]*[fd])"),
        "this discards uncommitted work irreversibly. Ask first.",
    ),
]


def env_violation(command: str) -> str | None:
    for token in ENV_TOKEN.findall(command):
        token = token.rstrip(".,;:")
        if token not in ALLOWED_ENV_FILES:
            return (
                f"this command touches {token}. Rules, section Environments: do not "
                f"read, print or log secret files. If you need a key documented, add "
                f"it to .env.example with an empty value."
            )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = str(payload.get("tool_input", {}).get("command", ""))
    if not command:
        return 0

    reason = env_violation(command)
    if reason is None:
        for pattern, message in RULES:
            if pattern.search(command):
                reason = message
                break

    if reason is None:
        return 0

    print(f"Blocked by .claude/hooks/bash-guard.py: {reason}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
