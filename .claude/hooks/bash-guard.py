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
string concatenation, by base64, or by a helper script written a moment
earlier. What this hook buys is that the easy paths are closed and the
remaining ones require obvious intent. The boundaries that do not depend on
reading command text are the pre-commit hook and, above all, the manifest pin
checked in CI, which no local flag can switch off.

The command is examined three ways, because one reading cannot serve every
rule:

* raw — as written;
* `nq` — quote characters dropped, contents kept, so `.e""nv` reads as `.env`;
* `flags` — quoted prose dropped but quoted flags kept, so a commit message
  that happens to contain `-name` is not mistaken for `--no-verify`, while
  `git commit "--no-verify"` still is.

Rules that describe a *command* (rm, git rm, git checkout, writing to the
manifest) are applied per shell segment rather than to the whole line. A live
session showed why: almost every command an agent writes starts with
`cd "$PROJECT" &&`, and rules anchored to the start of the string turned
`cd … && sha256sum -c scripts/integrity.sha256` into a blocked "write to the
manifest". That fired on the first command of the session.

The working directory arrives in the payload and is used: `rm scratch.txt`
typed while the shell is inside tmpBin is the agent tidying up, and the same
command typed in the project root is not.

Writing this file's own text through a heredoc will trip the guard, because
the text names the things it blocks. Use the Write tool for that, not Bash.
"""
from __future__ import annotations

import json
import re
import sys

# --- reading the command ----------------------------------------------------

def segments(command: str) -> list[str]:
    """Split on shell separators without splitting inside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = ""
            i += 1
        elif c in "\"'":
            quote = c
            buf.append(c)
            i += 1
        elif command.startswith(("&&", "||"), i):
            parts.append("".join(buf)); buf = []; i += 2
        elif c in ";|&\n":
            parts.append("".join(buf)); buf = []; i += 1
        else:
            buf.append(c)
            i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def unquoted(command: str) -> str:
    """Quote characters removed, contents kept: `.e""nv` -> `.env`."""
    return re.sub(r"[\"']", "", command)


def flags_only(command: str) -> str:
    """Quoted prose removed, quoted flags kept.

    `git commit -am "fix: FR-001 handle -name in find"` must not read as -n,
    and `git commit "--no-verify"` must. Empty quotes are joined rather than
    replaced, so `--f""ix` still reads as one flag.
    """
    out: list[str] = []
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c in "\"'":
            j = command.find(c, i + 1)
            if j == -1:
                out.append(command[i + 1:])
                break
            inner = command[i + 1:j]
            out.append("" if not inner else inner if inner.startswith("-") else " ")
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


# --- secrets ----------------------------------------------------------------

# `.envrc` is deliberately caught: direnv files routinely hold exported
# secrets. Recorded so a later cleanup does not "fix" it back open.
ALLOWED_ENV_FILES = {".env.example", ".env.sample", ".env.template", ".env.dist"}
# The lookbehind keeps attribute access out of it. `os.environ`,
# `app.env_settings` and `config.environment` are Python, not filenames, and
# blocking them broke inline `python3 -c` in a live session.
ENV_TOKEN = re.compile(r"(?<![A-Za-z0-9_])\.env[A-Za-z0-9_.-]*")
# `cat .en?` never spells the name, but the shell expands it to one.
ENV_GLOB = re.compile(r"(?<![A-Za-z0-9_])\.e[A-Za-z0-9_.*?\[\]-]*[*?\[]")


def env_violation(command: str, nq: str) -> str | None:
    for text in {command, nq}:
        for token in ENV_TOKEN.findall(text):
            token = token.rstrip(".,;:")
            if token in ALLOWED_ENV_FILES:
                continue
            extra = ""
            if any(a in text for a in ALLOWED_ENV_FILES):
                extra = (
                    " Creating it from .env.example is the owner's step, not "
                    "yours — say that it needs doing."
                )
            return (
                f"this command touches {token}. Rules, section Environments: do not "
                f"read, print or log secret files. If you need a key documented, add "
                f"it to .env.example with an empty value.{extra}"
            )
        m = ENV_GLOB.search(text)
        if m:
            return (
                f"`{m.group(0)}` is a glob that can expand onto a dotfile such as "
                f".env without naming it. Say which file you need and why."
            )
    return None


# --- the manifest -----------------------------------------------------------

MANIFEST = "integrity.sha256"
MANIFEST_READ = re.compile(
    r"^(?:cat|head|tail|less|more|wc|grep|rg|diff|sha256sum|shasum|md5sum"
    r"|git\s+(?:diff|show|log|status|ls-files|blame))\b"
)
MANIFEST_REDIRECT = re.compile(r">>?\s*[\"']?[^\s;&|]*integrity\.sha256")


def manifest_violation(segs: list[str]) -> str | None:
    for seg in segs:
        plain = unquoted(seg)
        if MANIFEST not in plain:
            continue
        if MANIFEST_READ.match(plain) and not MANIFEST_REDIRECT.search(plain):
            continue
        return (
            f"this command writes to scripts/{MANIFEST}. The manifest is the "
            f"baseline every other check is measured against; rewriting it by hand "
            f"legitimises whatever was changed. That is --fix, and --fix is the "
            f"owner's. Reading it — cat, diff, sha256sum -c — is fine."
        )
    return None


# --- deleting ---------------------------------------------------------------

TMPBIN = "tmpBin/"
DELETE_HEAD = re.compile(r"^(?:sudo\s+)?(?:rm|unlink|truncate)\b")
FIND_DELETE = re.compile(r"^(?:sudo\s+)?find\b[\s\S]*?(?:\s-delete\b|-exec\s+rm\b)")
CD_HEAD = re.compile(r"^cd\s+(?P<path>[^\s;&|]+)")
WIN_DRIVE = re.compile(r"^[A-Za-z]:")


def _slash(text: str) -> str:
    return text.replace("\\", "/")


def _under_tmpbin(target: str, cwd_inside: bool) -> bool:
    target = _slash(target.strip("\"'"))
    if ".." in target:
        return False
    if TMPBIN in target:
        return True
    # A relative path while the shell already sits inside tmpBin is inside it
    # too. This is why the hook reads `cwd` from the payload: without it a bare
    # `rm scratch.txt` typed in tmpBin was refused as "the owner's file", which
    # was both wrong and the only real false positive left after the first live
    # session.
    return cwd_inside and not target.startswith("/") and not WIN_DRIVE.match(target)


def _rm_targets(tokens: list[str]) -> list[str]:
    return [t for t in tokens if not t.startswith("-")]


def _find_roots(tokens: list[str]) -> list[str]:
    roots: list[str] = []
    for t in tokens:
        if t.startswith("-"):
            break
        roots.append(t)
    return roots or ["."]


def delete_violation(segs: list[str], cwd: str) -> str | None:
    """Deleting is the owner's, except inside the agent's own scratch folder.

    Covers rm, unlink, truncate and `find -delete`, because they differ only in
    spelling. The exemption is decided per segment, and follows a `cd` into
    tmpBin as well as the shell's starting directory.
    """
    inside = TMPBIN in _slash(cwd)
    for seg in segs:
        plain = unquoted(seg)
        cd = CD_HEAD.match(plain)
        if cd:
            path = cd.group("path")
            inside = TMPBIN in _slash(path) or (inside and not path.startswith(("/", "~")))
            continue
        tokens = plain.split()[1:]
        if FIND_DELETE.match(plain):
            targets = _find_roots(tokens)
        elif DELETE_HEAD.match(plain):
            targets = _rm_targets(tokens[1:] if tokens[:1] == ["rm"] else tokens)
        else:
            continue
        if not targets or all(_under_tmpbin(t, inside) for t in targets):
            continue
        return (
            "deleting files the owner did not ask you to delete. Name what you "
            "want removed and why, and let the owner run it. Cleaning up your own "
            "scratch under tmpBin/ is allowed — rm, unlink and find -delete alike."
        )
    return None


# --- everything else --------------------------------------------------------

# Flags only. These ask "was this flag passed", and the answer must not be
# taken from prose: a commit message mentioning -name is not --no-verify.
FLAG_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\bgit\s+commit\b(?=[\s\S]*?\s(?:--no-verify\b|-[A-Za-z]*n[A-Za-z]*\b))"
        ),
        "git commit with --no-verify (or -n, including inside a flag cluster "
        "like -nm) skips the commit-msg and pre-commit hooks. If a hook is in "
        "the way, say which one and why — do not bypass it.",
    ),
    (
        # --force-with-lease is allowed: it refuses to overwrite work it has not
        # seen, and `git push` is already `ask` in settings.json.
        re.compile(
            r"\bgit\s+push\b(?=[\s\S]*?\s(?:--force(?!-with-lease)\b|-[A-Za-z]*f[A-Za-z]*\b))"
        ),
        "force push rewrites history. Rules, section Environments: irreversible "
        "actions are the owner's call. --force-with-lease is allowed.",
    ),
]

# Text of the command, read raw and with quotes dropped. These name a script, a
# config key or a path, which quoting can split but prose rarely produces.
TEXT_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bgit\s+push\b[\s\S]*?\s\+[^\s;&|]+"),
        "a refspec beginning with + forces the push without the --force flag. "
        "Same answer: irreversible, so it is the owner's call.",
    ),
    (
        re.compile(r"\bgit\b[\s\S]*?\s-c\s+[\"']?core\.hooksPath"),
        "overriding core.hooksPath for one command disables the hooks for that "
        "command. Same answer as --no-verify: say what is in the way.",
    ),
    (
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
        re.compile(r"--i-know-what-im-doing"),
        "that flag exists only to confirm --fix. Renaming or copying the script "
        "does not change whose decision it is: the owner's, in a terminal.",
    ),
]

# Applied per segment, on the `nq` reading: these describe one command, and
# scanning the whole line made them read the flags of the next one — `git rm
# --cached x && git status --short` was blocked for the r in --short.
PER_SEGMENT: list[tuple[re.Pattern[str], str]] = [
    (
        # `git rm file` deletes from the working tree; --cached only unstages.
        re.compile(r"^git\s+rm\b(?![\s\S]*--cached\b)"),
        "git rm removes the file from disk, not just from the index. Use "
        "git rm --cached to unstage, and leave deleting to the owner.",
    ),
    (
        # A live session showed `git checkout <file>` is the first form an agent
        # reaches for, and it discards work exactly like `checkout -- <file>`.
        # Telling branches from paths by their spelling is guesswork, so
        # checkout is for creating a branch and git switch is for changing one.
        re.compile(r"^git\s+checkout\b(?!\s+-[bB]\b)"),
        "git checkout can discard uncommitted work, and which argument is a "
        "branch and which is a path is not decidable from the text. Use "
        "git switch to change branch, git checkout -b to create one, and ask "
        "the owner before discarding anything.",
    ),
    (
        re.compile(
            r"^git\s+(?:reset\s+--hard\b"
            r"|clean\s+[\s\S]*?(?:-[A-Za-z]*[fd][A-Za-z]*|--force\b)"
            r"|stash\s+(?:drop|clear)\b"
            r"|restore\s+(?![\s\S]*?--staged\b))"
        ),
        "this discards uncommitted work irreversibly. Ask first.",
    ),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = str(payload.get("tool_input", {}).get("command", ""))
    if not command:
        return 0

    # PreToolUse hands the shell's working directory over; without it a bare
    # `rm scratch.txt` typed inside tmpBin cannot be told from one typed in the
    # project root.
    cwd = str(payload.get("cwd", "") or "")
    nq = unquoted(command)
    segs = segments(command)

    reason = (
        env_violation(command, nq)
        or manifest_violation(segs)
        or delete_violation(segs, cwd)
    )

    if reason is None:
        flags = flags_only(command)
        for pattern, message in FLAG_RULES:
            if pattern.search(flags):
                reason = message
                break

    if reason is None:
        for pattern, message in TEXT_RULES:
            if any(pattern.search(t) for t in {command, nq}):
                reason = message
                break

    if reason is None:
        for seg in segs:
            plain = unquoted(seg)
            for pattern, message in PER_SEGMENT:
                if pattern.search(plain):
                    reason = message
                    break
            if reason:
                break

    if reason is None:
        return 0

    print(f"Blocked by .claude/hooks/bash-guard.py: {reason}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
