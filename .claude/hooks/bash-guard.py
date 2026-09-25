#!/usr/bin/env python3
"""PreToolUse guard for Bash commands.

Registered in .claude/settings.json. Exit code 2 blocks the call and hands the
message back to the agent.

Why a hook and not more deny rules: a Bash permission rule matches the text of
the command, so it is dodged by reordering flags, adding `./`, changing the
working directory first, or using the short form of a flag. And Read/Edit deny
rules reach Bash only part of the way: Claude Code parses simple commands
(`cat`, `ls`) and applies `Read(**/*.pem)` to their paths, but not to a path
inside an interpreter — `python -c "open('x.pem')"`, `node -e`, a heredoc —
which is exactly the form only the command text can catch. Probed on
2026-09-17 (audit 7). This hook looks at the command that is actually about
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

# The console's code page, not this script's own choice, decided the output
# encoding before this: cp1251 on a default Windows terminal. That silently
# mangled every non-ASCII character in these messages into mojibake for every
# reader downstream (MinTTY, the agent's own tool output, the other check
# script that decodes this one's stdout as UTF-8) and, worse, crashed with
# UnicodeEncodeError the moment a printed line held a character outside
# cp1251 — which skipped whatever check was about to print it. See
# RulesForAIVibeCoding.md / README.md, section Windows.
for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8", errors="replace")

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
# `cat .en?` never spells the name, but the shell expands it to one. Brace
# expansion is the same trick with a different bracket: `.en{v,}` and
# `.{env,gitignore}` both expand to `.env`. The second lookbehind also
# excludes `*`, `?` and `]`, so `ls *.{py,md}` is an ordinary glob and not a
# dotfile.
#
# Only a literal prefix of `.env` — `.e`, `.en`, `.env` — followed by a glob
# character can expand onto it. The earlier pattern let any letters sit
# between `.e` and the glob, so `git add .eslintrc.{js,json}` was refused as
# a secret, though it can only ever expand to the two eslint files.
ENV_GLOB = re.compile(
    r"(?<![A-Za-z0-9_])\.e(?:nv?)?[*?\[{]"
    r"|(?<![A-Za-z0-9_*?\]])\.\{"
)
# Mirror of the Read deny rules in settings.json that the Bash tool does not
# apply inside an interpreter: `*.pem`, `*.key`, anything under `secrets/`.
# `--key` (no dot), `monkey.keyboard` (not a suffix), `id.key.pub` and a
# `cfg.key(` method call stay out of it; `cfg.key)` does not, and that false
# positive is accepted over missing `open('db.key')`. A file needs a name in
# front of the suffix (`db.key`, `*.pem`): a bare `.key` is a jq filter —
# `jq -r '.key'` — and was refused as a key file.
SECRET_PATH = re.compile(
    r"[^\s\"'(),;:=]+\.(?:pem|key)(?![A-Za-z0-9_.(-])|(?<![A-Za-z0-9_.-])secrets/\S*",
    re.IGNORECASE,
)


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
        m = SECRET_PATH.search(text)
        if m:
            return (
                f"this command touches {m.group(0)}. Key files and secrets/ are "
                f"denied to the Read tool in settings.json, and the same boundary "
                f"holds for Bash. Rules, section Environments: do not read, print "
                f"or log secret files."
            )
    return None


# --- the manifest and the files it pins ---------------------------------------

MANIFEST = "integrity.sha256"
# The files scripts/integrity.sha256 pins — the PROTECTED list of
# scripts/check-template.py, by file name. Edit/Write on these paths is `ask`
# in settings.json; a `sed -i` or `cp` through Bash used to be neither asked
# nor blocked, and between that write and the Stop hook the guard it rewrote
# was already the new one. Kept as names rather than read from the manifest,
# so a deleted manifest does not also switch this rule off.
PROTECTED = (
    "RulesForAIVibeCoding.md",
    ".gitattributes",
    "check-template.py",
    "check-slice.py",
    "check-ids.py",
    ".githooks/pre-commit",
    ".githooks/commit-msg",
    ".claude/settings.json",
    "bash-guard.py",
    "stop-integrity.py",
    MANIFEST,
)
# Not pinned — it is the owner's machine file, in .gitignore — but it is read
# by Claude Code as settings, and its hooks and permissions are merged with
# the committed ones. `cat > .claude/settings.local.json` with
# `{"disableAllHooks": true}` switched this very guard off from the next
# session on, in the plainest spelling there is. Edit/Write on it are `ask`
# (`.claude/**`); through Bash it was neither.
LOCAL_SETTINGS = "settings.local.json"
WATCHED = PROTECTED + (LOCAL_SETTINGS,)
# Commands that only read, run, or merely name the file. `sed` and `perl` are
# here only without an in-place flag, and so are the other readers that can
# write: `sort -o`, `awk -i inplace`, `git diff --output`. `uniq` is not here
# at all — its second operand is an output file. An interpreter with an
# inline program (`python -c`, `node -e`) is not: that is the one form where
# the path in the text is an argument to open(), not a script to run. `for`,
# `echo`, `test` name a path without touching it; a redirect on the same
# segment is still caught by PROTECTED_REDIRECT.
#
# `find` only without an action that writes or runs something; `git grep`,
# `nl`, `xxd`, `od` only read. A pinned script or git hook given as the
# command word is being run, not written: `./scripts/check-slice.py
# SLICE-001` used to be refused as "writes to check-slice.py", and an agent
# told it is writing a file it is only running has to invent a reason.
PROTECTED_READ = re.compile(
    r"^(?:cat|head|tail|less|more|wc|grep|rg|diff|ls|stat|file|cut|nl|xxd|od"
    r"|for|echo|printf|test|\["
    r"|sha256sum|shasum|md5sum"
    r"|find\b(?![\s\S]*\s-(?:delete|exec|execdir|ok|okdir|fprint0?|fprintf|fls)\b)"
    r"|(?:\S*/)?(?:check-template|check-slice|check-ids|bash-guard|stop-integrity)\.py"
    r"|(?:\S*/)?\.githooks/(?:pre-commit|commit-msg)"
    r"|git\s+(?:diff|show|log)\b(?![\s\S]*--output)"
    r"|git\s+(?:status|ls-files|blame|add|commit|grep)"
    r"|sort\b(?![\s\S]*\s(?:-[A-Za-z]*o|--output))"
    r"|awk\b(?![\s\S]*\s(?:-i|--include)\b)"
    r"|(?:sed|perl)\b(?![\s\S]*\s-[A-Za-z]*i|[\s\S]*--in-place)"
    r"|(?:python3?|py|bash|sh)\b(?![\s\S]*\s-[ce]\b))\b"
)
PROTECTED_REDIRECT = re.compile(r">>?\s*[^\s;&|]*(?:" + "|".join(re.escape(p) for p in WATCHED) + ")")
CP_HEAD = re.compile(r"^cp\b")
# Directories that hold a pinned file. `cp x scripts` writes scripts/x exactly
# as `cp x scripts/` does, and nothing in the text says `scripts` is a
# directory — so these are known by name. A path to the project given in
# another spelling (absolute, via a variable) is not recognised; that is the
# limit stated at the top of this file, and the Stop hook still sees the
# result.
PINNED_DIRS = ("scripts", ".githooks", ".claude", ".claude/hooks")
# What stands in front of the command word without being one: shell keywords
# of a loop or a condition, and the opening of a `$(...)` or a subshell. The
# segment splitter cuts `for …; do h=$(grep x scripts/integrity.sha256 | …)`
# into `do h=$(grep x scripts/integrity.sha256`, and that segment used to be
# refused as a write to the manifest — the first command of an audit session.
# Also an environment assignment and the wrappers that only run the next word:
# `PYTHONUTF8=1 python3 scripts/check-slice.py`, `timeout 60 python3 …`. What
# follows them is judged as the command it is — `env sed -i …` is still sed -i.
LEAD = re.compile(
    r"^(?:(?:do|then|else|elif|if|while|until|!)\s+|\w+=\$\(|\$\(|\(|`"
    r"|[A-Za-z_]\w*=[^\s$`(]*\s+|(?:env|command|time|nice|nohup)\s+"
    r"|timeout\s+(?:-\S+\s+)*\S+\s+)+"
)
# An input redirection reads the file: `done < scripts/integrity.sha256` is a
# loop reading the manifest. Dropped before the name is looked for, so the
# write that may stand next to it (`tee <pinned> < x`) is still seen.
INPUT_REDIRECT = re.compile(r"(?<![<\d])<(?![<(])\s*[^\s;&|<>]+")


def _names_protected(token: str) -> bool:
    return any(p in token for p in PROTECTED)


def _cp_destinations(args: list[str]) -> list[str]:
    """The paths a `cp` writes, as far as the text tells.

    The last operand is the destination only when it is a file. Into a
    directory — `cp x .`, `cp x scripts/`, `cp -t .claude x`, or several
    sources — cp writes <directory>/<name of each source>, and checking only
    the last operand let `cp tmpBin/check-ids.py scripts/` overwrite a pinned
    script unasked.
    """
    target: str | None = None
    operands: list[str] = []
    it = iter(args)
    for a in it:
        if a in ("-t", "--target-directory"):
            target = next(it, "")
        elif a.startswith("--target-directory="):
            target = a.split("=", 1)[1]
        elif a.startswith("--"):
            continue
        elif a.startswith("-"):
            if "t" in a[1:]:  # -t inside a cluster: `cp -rt scripts x`
                target = next(it, "")
        else:
            operands.append(a)
    if target is not None:
        return [_into(target, s) for s in operands]
    if len(operands) < 2:
        return operands
    *sources, dest = operands
    if len(sources) > 1 or _looks_like_dir(dest):
        return [_into(dest, s) for s in sources]
    return [dest]


def _looks_like_dir(path: str) -> bool:
    p = _slash(path.strip("\"'"))
    if p.endswith("/") or p in (".", ".."):
        return True
    while p.startswith("./"):
        p = p[2:]
    return any(p == d or p.endswith("/" + d) for d in PINNED_DIRS)


def _into(directory: str, source: str) -> str:
    return _slash(directory).rstrip("/") + "/" + _slash(source).rsplit("/", 1)[-1]


def _cp_pinned_target(plain: str, named: str | None) -> str | None:
    """The pinned path a cp writes, or None when it writes none.

    Decided before the "does the text name a pinned file" test, not after it:
    `cp -t .claude x/settings.json` never spells `.claude/settings.json` — the
    pinned path exists only once the directory and the file name are joined.
    A destination the text cannot resolve (a variable, a backtick) fails
    closed, but only when a pinned name is in the command at all; tmpBin/ is
    the agent's own scratch and may hold copies.
    """
    for dest in _cp_destinations(plain.split()[1:]):
        if _under_tmpbin(dest, False):
            continue
        hit = next((p for p in WATCHED if p in dest), None)
        if hit:
            return hit
        if named and ("$" in dest or "`" in dest):
            return named
    return None


def manifest_violation(segs: list[str]) -> str | None:
    for seg in segs:
        plain = INPUT_REDIRECT.sub("", LEAD.sub("", unquoted(seg))).strip()
        hit = next((p for p in WATCHED if p in plain), None)
        if CP_HEAD.match(plain):
            # `cp <pinned> elsewhere` is a read of the pinned file; what must
            # not be pinned is where it writes.
            hit = _cp_pinned_target(plain, hit)
            if hit is None:
                continue
        elif hit is None:
            continue
        elif PROTECTED_READ.match(plain) and not PROTECTED_REDIRECT.search(plain):
            continue
        if hit == MANIFEST:
            return (
                f"this command writes to scripts/{MANIFEST}. The manifest is the "
                f"baseline every other check is measured against; rewriting it by hand "
                f"legitimises whatever was changed. That is --fix, and --fix is the "
                f"owner's. Reading it — cat, diff, sha256sum -c — is fine."
            )
        if hit == LOCAL_SETTINGS:
            return (
                f"this command writes to .claude/{LOCAL_SETTINGS}. Its hooks and "
                f"permissions are merged with the committed settings, so writing it "
                f"can switch the guards off. It is the owner's machine file "
                f"(README, section Windows): say what should change in it and why."
            )
        return (
            f"this command writes to {hit}, a file pinned by scripts/{MANIFEST}. "
            f"Rules, section 0: the checks are not yours to edit. Say which check "
            f"is wrong and why, and propose the change — the owner applies it and "
            f"runs --fix. Reading or running it — cat, diff, python — is fine."
        )
    return None


# --- deleting ---------------------------------------------------------------

TMPBIN = "tmpBin"
# The command word itself, after any wrapper: `\rm` (the classic alias
# bypass), `/bin/rm`, `command rm`, `env rm`, `xargs rm` after a find. All of
# these ran unblocked while `rm` did not, and none of them is concatenation or
# base64 — they are the plain spellings.
DELETE_CMD = re.compile(r"^\\?(?:/\S*/)?(?:rm|unlink|truncate)$")
WRAPPERS = {"sudo", "command", "env", "busybox", "xargs", "nice", "nohup", "time"}
FIND_HEAD = re.compile(r"^(?:sudo\s+)?find\b")
FIND_DELETE = re.compile(
    r"^(?:sudo\s+)?find\b[\s\S]*?(?:\s-delete\b|-(?:exec|ok)(?:dir)?\s+\\?(?:/\S*/)?rm\b)"
)
# The path group is optional: a bare `cd` (no argument) changes directory too
# — to $HOME on a POSIX shell — and used to fall through this regex entirely,
# leaving the tracked "inside tmpBin" state untouched instead of updated.
# pushd is cd with a stack; the stack is not tracked, so a bare pushd (swap)
# is unresolved like a bare cd.
CD_HEAD = re.compile(r"^(?:cd|pushd)\b(?:\s+(?P<path>[^\s;&|]+))?")
POPD_HEAD = re.compile(r"^popd\b")
WIN_DRIVE = re.compile(r"^[A-Za-z]:")
# A cd target this hook cannot resolve from text alone: the previous
# directory (`cd -`), or anything the shell expands at run time — a variable,
# a `$(...)` substitution, a backtick. Naming the two variables that matter
# (`$OLDPWD`, `$HOME`) left `cd "$CLAUDE_PROJECT_DIR"` and `cd $PWD/..` read
# as relative paths, i.e. as staying inside tmpBin.
UNKNOWN_CD = re.compile(r"^-$|[$`]")


def _slash(text: str) -> str:
    return text.replace("\\", "/")


def _segments(path: str) -> list[str]:
    return [p for p in _slash(path).split("/") if p not in ("", ".")]


def _under_tmpbin(target: str, cwd_inside: bool) -> bool:
    target = target.strip("\"'")
    # `rm -rf "$PROJECT/source"` typed inside tmpBin: the value is not in the
    # text, so it cannot be inside tmpBin. Fails closed, like `cd $VAR`.
    if "$" in target or "`" in target:
        return False
    if ".." in _segments(target):
        return False
    if TMPBIN in _segments(target):
        return True
    # A relative path while the shell already sits inside tmpBin is inside it
    # too. This is why the hook reads `cwd` from the payload: without it a bare
    # `rm scratch.txt` typed in tmpBin was refused as "the owner's file", which
    # was both wrong and the only real false positive left after the first live
    # session.
    t = _slash(target)
    return cwd_inside and not t.startswith("/") and not t.startswith("~") and not WIN_DRIVE.match(t)


def _rm_targets(tokens: list[str]) -> list[str]:
    return [t for t in tokens if not t.startswith("-")]


def _delete_targets(tokens: list[str], piped_from: list[str]) -> list[str] | None:
    """Targets of an rm/unlink/truncate, or None when the segment is not one.

    Skips wrappers (`sudo`, `env VAR=x`, `xargs -0`) up to the command word.
    `xargs rm` with no argument of its own deletes whatever the previous
    segment printed: the roots of a `find` if that is what it was, otherwise
    something this hook cannot see, spelled `$stdin` so that it fails closed
    like any other unresolved path.
    """
    via_xargs = False
    for i, tok in enumerate(tokens):
        if DELETE_CMD.match(tok):
            targets = _rm_targets(tokens[i + 1:])
            if via_xargs and not targets:
                targets = piped_from or ["$stdin"]
            return targets
        if tok in WRAPPERS or tok.startswith("-") or "=" in tok:
            via_xargs = via_xargs or tok == "xargs"
            continue
        return None
    return None


def _find_roots(tokens: list[str]) -> list[str]:
    roots: list[str] = []
    for t in tokens:
        if t.startswith("-"):
            break
        roots.append(t)
    return roots or ["."]


def _apply_cd(segs: list[str], path: str | None) -> list[str]:
    """Best-effort tracking of the shell's directory as a segment stack.

    Used only to decide whether the shell sits inside tmpBin/. An absolute
    path, a home path (~) or a Windows drive replaces the stack outright
    rather than being read as "still relative, so still inside" — that
    misreading let `cd D:\\elsewhere` or `cd C:/other` after a start inside
    tmpBin keep the exemption alive for a delete anywhere on disk. `..` pops a
    segment instead of being ignored, so `cd ..` from tmpBin/sandbox lands
    back in tmpBin (still exempt) while `cd ../..` from the same place leaves
    it (exempt lifted) — both were wrong with a plain substring check.

    A destination this hook cannot resolve from text alone — no path at all
    (bare `cd`, which goes to $HOME), `cd -` (the previous directory, whose
    value this hook never saw), or `cd $OLDPWD` / `cd $HOME` (a variable this
    hook cannot read) — fails *closed*: treated as leaving tmpBin, not as
    staying in it. The alternative reading a live session actually hit was
    the wrong one: `cd tmpBin && cd - && rm -rf source/x` kept the delete
    exemption alive because `cd -` matched nothing and left `inside` at its
    previous value.
    """
    if path is None:
        return []
    p = path.strip("\"'")
    if UNKNOWN_CD.match(p):
        return []
    sp = _slash(p)
    if not p:
        return segs
    if sp.startswith("~") or sp.startswith("/") or WIN_DRIVE.match(sp):
        return _segments(sp)
    new = list(segs)
    for part in sp.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if new:
                new.pop()
        else:
            new.append(part)
    return new


def delete_violation(segs: list[str], cwd: str) -> str | None:
    """Deleting is the owner's, except inside the agent's own scratch folder.

    Covers rm, unlink, truncate and `find -delete`, because they differ only in
    spelling. The exemption is decided per segment, and follows a `cd` into
    tmpBin as well as the shell's starting directory. The shell's directory is
    tracked as a path-segment stack (_apply_cd), not a boolean toggled by
    substring matching — see its docstring for the two cases that broke.
    """
    cwd_segs = _segments(cwd)
    inside = TMPBIN in cwd_segs
    piped_from: list[str] = []
    for seg in segs:
        plain = unquoted(seg)
        cd = CD_HEAD.match(plain)
        if cd:
            cwd_segs = _apply_cd(cwd_segs, cd.group("path"))
            inside = TMPBIN in cwd_segs
            continue
        if POPD_HEAD.match(plain):
            # Same reasoning as the unresolved cd forms above: popd's
            # destination is the directory stack this hook never tracked, so
            # it cannot be read as "still inside".
            cwd_segs = []
            inside = False
            continue
        tokens = plain.split()
        if FIND_DELETE.match(plain):
            targets = _find_roots(tokens[1:])
        else:
            targets = _delete_targets(tokens, piped_from)
        # What the next segment's `xargs rm` would receive: a find's roots,
        # or nothing knowable.
        piped_from = _find_roots(tokens[1:]) if FIND_HEAD.match(plain) else []
        if targets is None:
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
#
# `git` may carry global options before the subcommand — `git -C . commit`,
# `git -c user.name=x commit`, `git --no-pager push` — and `\bgit\s+commit`
# saw none of them, so `git -C . commit -n` walked past every rule below
# (and past the `Bash(git commit:*)` ask-prefix in settings.json, which is
# a prefix). GIT_GLOBALS eats any number of `-x`, `--x`, `-C value`, `-c k=v`.
# `--no-veri`: git accepts any unambiguous prefix of a long option, and
# `--no-veri` is one (`--no-v` is not — it collides with --no-verbose).
#
# Applied per segment. On the whole line the lookahead ran on into the next
# command, so `git commit -m "…" && git log -n 1` — the most ordinary thing
# an agent does after a commit — was refused as --no-verify, and
# `git push && tail -f log` as a force push. An agent accused of bypassing a
# hook it never touched has to explain something that did not happen.
GIT_GLOBALS = r"\bgit(?:\s+-\S*(?:\s+[^-\s;&|]\S*)?)*\s+"
FLAG_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            GIT_GLOBALS + r"commit\b(?=[\s\S]*?\s(?:--no-veri[a-z]*\b|-[A-Za-z]*n[A-Za-z]*\b))"
        ),
        "git commit with --no-verify (or -n, including inside a flag cluster "
        "like -nm) skips the commit-msg and pre-commit hooks. If a hook is in "
        "the way, say which one and why — do not bypass it.",
    ),
    (
        # --force-with-lease is allowed: it refuses to overwrite work it has not
        # seen, and `git push` is already `ask` in settings.json.
        re.compile(
            GIT_GLOBALS + r"push\b(?=[\s\S]*?\s(?:--force(?!-with-lease)\b|-[A-Za-z]*f[A-Za-z]*\b))"
        ),
        "force push rewrites history. Rules, section Environments: irreversible "
        "actions are the owner's call. --force-with-lease is allowed.",
    ),
]

# Text of the command, read raw and with quotes dropped. These name a script, a
# config key or a path, which quoting can split but prose rarely produces.
TEXT_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        # Kept inside one command: `[^;&|\n]`, not `[\s\S]`, so a `+1` in the
        # next command is not a refspec; GIT_GLOBALS, so `git -C . push
        # origin +main` is.
        re.compile(GIT_GLOBALS + r"push\b[^;&|\n]*?\s\+[^\s;&|]+"),
        "a refspec beginning with + forces the push without the --force flag. "
        "Same answer: irreversible, so it is the owner's call.",
    ),
    (
        # Config keys are case-insensitive to git, so `core.hookspath` is the
        # same key — hence IGNORECASE on every rule that names it. The
        # environment forms (GIT_CONFIG_KEY_n, GIT_CONFIG_PARAMETERS,
        # --config-env) set the same key without ever spelling `-c`.
        re.compile(
            r"\bgit\b[\s\S]*?\s-c\s+[\"']?core\.hookspath"
            r"|GIT_CONFIG_KEY_\d+=[\"']?core\.hookspath"
            r"|GIT_CONFIG_PARAMETERS=[\s\S]*?core\.hookspath"
            r"|--config-env=[\"']?core\.hookspath",
            re.IGNORECASE,
        ),
        "overriding core.hooksPath for one command disables the hooks for that "
        "command. Same answer as --no-verify: say what is in the way.",
    ),
    (
        # The lookahead ends `.githooks` at whitespace, a quote, a separator
        # or the end of the text: `\b` let `.githooks/../evil` through.
        #
        # The first lookahead lets the bare read through: `git config
        # core.hooksPath` with no value prints the setting, and it used to be
        # blocked as if it set one — while check-template.py's own advice is to
        # look at it. Only scope flags and the `get` subcommand (git 2.46+) may
        # precede the key for that, and only an output redirection may follow
        # it (`2>/dev/null` is not a value); `--unset core.hooksPath` has no
        # value either, and it is a write.
        re.compile(
            GIT_GLOBALS + r"config\s+"
            r"(?!(?:(?:--(?:local|global|system|worktree|show-origin|show-scope)|get)\s+)*"
            r"core\.hookspath(?:\s+\d?>>?&?\s*[^\s;&|]+)*\s*(?:[;&|)]|$))"
            r"(?:(?!--get\b|--get-all\b|--get-regexp\b|--list\b|-l\b)[^\s;&|]+\s+)*?"
            r"core\.hookspath\b(?!\s+[\"']?\.githooks/?(?:[\s\"';&|)]|$))",
            re.IGNORECASE,
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

# Not blocked but handed to the owner as a permission prompt. Regenerating
# visual baselines makes every visual test pass, the way --fix makes the
# integrity check pass — but unlike --fix it is legitimate after the owner has
# seen the old and new images (rules, section UI tests), and the prompt is
# exactly where that yes is given. Read on the `flags` reading, so a commit
# message that mentions the flag is not a regeneration.
#
# Two kinds of spelling. Long flags that mean nothing else anywhere, matched
# on the whole command. And the short or generic forms — `-u`, `--update` —
# which are also `git add -u` and `sort -u`, so they count only in a segment
# that runs one of the runners they belong to (Playwright, Jest, Vitest).
#
# The limit, stated rather than hidden: a project script that wraps these
# (`npm run test:update`) is invisible here. That is why the rules make
# ARCHITECTURE.md name the one regeneration command, and make the local
# verification refuse to write a missing baseline on its own.
ASK_MESSAGE = (
    "this regenerates visual baselines, which makes every visual test pass. "
    "Rules, section UI tests: the owner has seen the old and the new images "
    "and said yes before this runs."
)
ASK_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?<![\w-])--(?:update-?snapshots?|updateSnapshots?|snapshot-update"
            r"|update-baselines?|force-regen)(?![\w-])"
            r"|\bbackstop\s+approve\b",
            re.IGNORECASE,
        ),
        ASK_MESSAGE,
    ),
]
# The runner must be the command the segment runs — directly, by path, or
# through npx / pnpm / yarn / bunx / npm exec — not merely a word in it:
# `git log --grep=jest -u` is a patch listing, not a regeneration.
ASK_PER_SEGMENT: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"^(?:\w+=\S*\s+)*"
            r"(?:(?:npx|bunx|pnpm|yarn)\s+(?:-\S+\s+)*(?:exec\s+|dlx\s+)?|npm\s+exec\s+)?"
            r"(?:\S*/)?(?:playwright|jest|vitest)\b[\s\S]*?\s(?:-u|--update)(?![\w-])"
        ),
        ASK_MESSAGE,
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
        # `git switch` is where the checkout rule above sends the agent, and
        # its -f / --discard-changes throw away uncommitted work exactly like
        # `checkout --` does. Plain switch refuses to, so it stays allowed.
        re.compile(
            r"^git\s+(?:reset\s+--hard\b"
            r"|clean\s+[\s\S]*?(?:-[A-Za-z]*[fd][A-Za-z]*|--force\b)"
            r"|stash\s+(?:drop|clear)\b"
            r"|switch\b[\s\S]*?(?:\s--discard-changes\b|\s--force(?![\w-])"
            r"|\s-[A-Za-z]*f[A-Za-z]*\b)"
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
        reason = next(
            (m for seg in segments(flags) for p, m in FLAG_RULES if p.search(seg)),
            None,
        )

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
        flags = flags_only(command)
        ask = next((m for p, m in ASK_RULES if p.search(flags)), None)
        if ask is None:
            ask = next(
                (m for seg in segments(flags) for p, m in ASK_PER_SEGMENT if p.search(seg)),
                None,
            )
        if ask is not None:
            # Exit 0 with a decision on stdout: Claude Code shows the owner a
            # permission prompt instead of refusing the call outright.
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": f".claude/hooks/bash-guard.py: {ask}",
            }}))
        return 0

    print(f"Blocked by .claude/hooks/bash-guard.py: {reason}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
