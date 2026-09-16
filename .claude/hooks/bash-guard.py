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

It is still not a sandbox, and the limit is worth stating plainly rather than
discovering later: Bash is an interpreter, so any pattern can be defeated by
string concatenation (`--f""ix`), by base64, or by a helper script written a
moment earlier. What this hook buys is that the easy paths are closed and the
remaining ones require obvious intent. The boundaries that do not depend on
reading command text are the pre-commit hook and, above all, the manifest pin
checked in CI, which no local flag can switch off.

Patterns use `[\\s\\S]` rather than `[^\\n]` on purpose: a command can span
lines through a backslash continuation or a heredoc, and a guard that stops at
the first newline is bypassed by pressing Enter.
"""
from __future__ import annotations

import json
import re
import sys

# `.envrc` is deliberately NOT here: direnv files routinely hold exported
# secrets, so the greedy ENV_TOKEN match that catches them is wanted, not an
# accident. Recorded so a later cleanup does not "fix" it back open.
ALLOWED_ENV_FILES = {".env.example", ".env.sample", ".env.template", ".env.dist"}
ENV_TOKEN = re.compile(r"\.env[A-Za-z0-9_.-]*")
# `cat .en?` and `cat .e*` never spell the name, but the shell expands them to
# it. Any token starting `.e` that carries a glob metacharacter is treated as
# an attempt to reach a dotfile without naming it.
ENV_GLOB = re.compile(r"\.e[A-Za-z0-9_.*?\[\]-]*[*?\[]")
# Quotes split a token without changing what the shell runs: `.e""nv` is .env
# and `--f""ix` is --fix. Every pattern is therefore tried twice — once on the
# command as written, once with quote characters removed. This closes the cheap
# form of concatenation; it does not close $(printf …) or base64, and nothing
# that reads command text can.
QUOTES = re.compile(r"[\"\']")

# Read-only inspection of the manifest is fine and sometimes necessary; writing
# to it is the thing --fix exists for. Anchored at the start so a redirect or a
# second command cannot hide behind a harmless-looking prefix.
MANIFEST = "integrity.sha256"
MANIFEST_READ = re.compile(
    r"^\s*(?:cat|head|tail|less|more|wc|grep|rg|sha256sum|shasum|md5sum"
    r"|git\s+(?:diff|show|log|status|ls-files))\b"
)

# Deleting inside tmpBin/ is the agent cleaning up after itself: the folder is
# its declared scratch space and it is in .gitignore. Anything outside it, or
# any `..` escape, falls through to the rm rule below.
RM_IN_TMPBIN = re.compile(
    r"^\s*rm\s+(?:-[A-Za-z]+\s+|--(?:recursive|force|dir)\s+)*"
    r"(?:tmpBin/[^\s;&|]*\s*)+$"
)

RULES: list[tuple[re.Pattern[str], str]] = [
    (
        # -n also hides inside a cluster of short flags: `git commit -nm "…"`
        # is --no-verify plus -m, and git's option parser accepts it.
        re.compile(
            r"\bgit\s+commit\b(?=[\s\S]*?\s(?:--no-verify\b|-[A-Za-z]*n[A-Za-z]*\b))"
        ),
        "git commit with --no-verify (or -n, including inside a flag cluster "
        "like -nm) skips the commit-msg and pre-commit hooks. If a hook is in "
        "the way, say which one and why — do not bypass it.",
    ),
    (
        # --force-with-lease is allowed: it is the form that refuses to
        # overwrite work it has not seen, and `git push` is already `ask` in
        # settings.json, so the owner sees it either way.
        re.compile(
            r"\bgit\s+push\b(?=[\s\S]*?\s(?:--force(?!-with-lease)\b|-[A-Za-z]*f[A-Za-z]*\b))"
        ),
        "force push rewrites history. Rules, section Environments: irreversible "
        "actions are the owner's call. If you need it, --force-with-lease is "
        "allowed and the owner still approves the push.",
    ),
    (
        # A refspec starting with + is a force push with no --force in sight.
        re.compile(r"\bgit\s+push\b[\s\S]*?\s\+[^\s;&|]+"),
        "a refspec beginning with + forces the push without the --force flag. "
        "Same answer: irreversible, so it is the owner's call.",
    ),
    (
        # -c need not sit right after `git`: `git --no-pager -c core.hooksPath=…`
        # is the same thing, and the key may be quoted.
        re.compile(r"\bgit\b[\s\S]*?\s-c\s+[\"']?core\.hooksPath"),
        "overriding core.hooksPath for one command disables the hooks for that "
        "command. Same answer as --no-verify: say what is in the way.",
    ),
    (
        # Only a write is blocked, and only when the value is not .githooks.
        # Reading the key must stay possible: check-template.py's own error
        # message tells you to go and look at it. The token loop cannot cross a
        # shell separator, so `… .githooks && git config --get …` is not read as
        # one command, and a trailing `# .githooks` comment no longer satisfies
        # the check the way a lookahead over the whole line did.
        re.compile(
            r"\bgit\s+config\s+"
            r"(?:(?!--get\b|--get-all\b|--get-regexp\b|--list\b|-l\b)[^\s;&|]+\s+)*?"
            r"core\.hooksPath\b(?!\s+[\"']?\.githooks\b)"
        ),
        "core.hooksPath must stay pointed at .githooks.",
    ),
    (
        re.compile(r"check-template\.py[\s\S]*?--fix|--fix[\s\S]*?check-template\.py"),
        "--fix rewrites the integrity baseline. That flag belongs to the owner, "
        "in a terminal, in the same commit as the change it legitimises.",
    ),
    (
        # Catches the same thing when the script has been copied under another
        # name. This flag exists for exactly one purpose and appears nowhere
        # else, so its presence is intent on its own.
        re.compile(r"--i-know-what-im-doing"),
        "that flag exists only to confirm --fix. Renaming or copying the script "
        "does not change whose decision it is: the owner's, in a terminal.",
    ),
    (
        # Two shapes. First: rm standing where a command starts, with or without
        # flags — `rm docs/FRS.md` needs no flag to lose a file the owner wrote.
        # The anchor keeps `npm rm lodash` out of it. Second: any rm carrying a
        # recursive or force flag anywhere, which catches `… | xargs rm -rf`.
        re.compile(
            r"(?:^|[;&|(]\s*)(?:sudo\s+)?rm\s+[^\s]"
            r"|\brm\b[\s\S]*?(?:-[A-Za-z]*[rf][A-Za-z]*|--recursive\b|--force\b)"
        ),
        "deleting files the owner did not ask you to delete. Name what you want "
        "removed and why, and let the owner run it. Cleaning up your own scratch "
        "under tmpBin/ is allowed.",
    ),
    (
        re.compile(r"\bfind\b[\s\S]*?(?:\s-delete\b|-exec\s+rm\b)"),
        "find -delete (or -exec rm) is a recursive delete wearing a different "
        "name. Same answer as rm.",
    ),
    (
        re.compile(
            r"\bgit\s+(?:reset\s+--hard\b"
            r"|clean\s+[\s\S]*?(?:-[A-Za-z]*[fd][A-Za-z]*|--force\b)"
            r"|checkout\s+--\s"
            r"|restore\s+(?![\s\S]*?--staged\b))"
        ),
        "this discards uncommitted work irreversibly. Ask first.",
    ),
]


def variants(command: str) -> tuple[str, ...]:
    """The command as written, plus the same text with quotes removed."""
    stripped = QUOTES.sub("", command)
    return (command,) if stripped == command else (command, stripped)


def env_violation(command: str) -> str | None:
    for text in variants(command):
        for token in ENV_TOKEN.findall(text):
            token = token.rstrip(".,;:")
            if token not in ALLOWED_ENV_FILES:
                return (
                    f"this command touches {token}. Rules, section Environments: do "
                    f"not read, print or log secret files. If you need a key "
                    f"documented, add it to .env.example with an empty value."
                )
        m = ENV_GLOB.search(text)
        if m:
            return (
                f"`{m.group(0)}` is a glob that can expand onto a dotfile such as "
                f".env without naming it. Say which file you need and why."
            )
    return None


def manifest_violation(command: str) -> str | None:
    if not any(MANIFEST in text for text in variants(command)):
        return None
    if MANIFEST_READ.match(command):
        return None
    return (
        f"this command writes to scripts/{MANIFEST}. The manifest is the baseline "
        f"every other check is measured against; rewriting it by hand legitimises "
        f"whatever was changed. That is --fix, and --fix is the owner's."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = str(payload.get("tool_input", {}).get("command", ""))
    if not command:
        return 0

    reason = env_violation(command) or manifest_violation(command)
    if reason is None:
        exempt_rm = RM_IN_TMPBIN.match(command) is not None and ".." not in command
        for pattern, message in RULES:
            if exempt_rm and message.startswith("deleting files"):
                continue
            if any(pattern.search(text) for text in variants(command)):
                reason = message
                break

    if reason is None:
        return 0

    print(f"Blocked by .claude/hooks/bash-guard.py: {reason}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
