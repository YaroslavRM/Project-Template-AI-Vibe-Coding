#!/usr/bin/env python3
"""Template integrity check.

Usage:  python3 scripts/check-template.py
        python3 scripts/check-template.py --fix --i-know-what-im-doing

Checks:
  1. every enforcement file is unchanged (sha256 vs scripts/integrity.sha256);
  2. the project skeleton is in place (same list as the rules, section
     "Project structure");
  3. .gitignore excludes tmpBin/* and keeps .gitkeep;
  4. git hooks are actually wired up (core.hooksPath) and executable.

Plus non-blocking warnings: documents still untouched, local verification
command not filled in.

The manifest covers the rules AND the machinery that enforces them: this
script, the two other scripts, both git hooks, the agent hook scripts, the
permission file and .gitattributes.
Hashing only the rules would leave the checker itself rewritable — and a
checker that always prints OK passes both the commit hook and CI.

--fix rewrites the whole baseline and, in the same run, the manifest pin in
.github/workflows/template-check.yml. It is deliberately awkward: it needs a
second flag and a terminal, so a permission rule that blocks it cannot be
dodged by re-spelling the command. Run it only after a change you agreed to,
and commit integrity.sha256 and the workflow in the same commit as the change.

Why --fix writes the pin instead of leaving it to be copied by hand: copying a
hash stops nobody. Whoever can run --fix can edit the workflow line too, so the
manual step bought no safety — it only produced commits where the pin was
forgotten. What the pin actually catches is a manifest changed WITHOUT --fix,
and that is now caught twice: by this script on every commit, and by CI.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
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

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "integrity.sha256"
WORKFLOW = ROOT / ".github" / "workflows" / "template-check.yml"
# The pin line in the workflow. Optional: a project with no GitHub may delete
# the workflow outright, and then there is simply nothing to keep in step.
PIN = re.compile(r'(?m)^(?P<pre>\s*expected=")(?P<hash>[0-9a-f]{64})(?P<post>")$')

# Files whose contents are pinned. Order is the order written to the manifest.
#
# The manifest itself is not in this list, and neither is the CI workflow:
# the workflow pins the manifest's hash, so pinning the workflow here would
# close a loop that could never be updated. The chain is
# workflow -> manifest -> everything else, and it has no cycle.
PROTECTED = [
    "RulesForAIVibeCoding.md",
    ".gitattributes",
    "scripts/check-template.py",
    "scripts/check-slice.py",
    "scripts/check-ids.py",
    ".githooks/pre-commit",
    ".githooks/commit-msg",
    ".claude/settings.json",
    ".claude/hooks/bash-guard.py",
    ".claude/hooks/stop-integrity.py",
]

# Mirrors the structure listed in RulesForAIVibeCoding.md, section
# "Project structure". If you add a file there, add it here — a skeleton
# that is silently incomplete enforces nothing.
#
# Except what the rules allow to be absent for a while: .github/workflows/
# (no GitHub), docs/DEPLOY.md (until step 2 writes its skeleton) and deploy/
# (until the first release). Whether that moment has come is not something
# the files can tell, so requiring them here would fail every new project and
# checking "only after the first release" would be a guess.
REQUIRED = [
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".env.example",
    ".githooks/commit-msg",
    ".githooks/pre-commit",
    ".claude/settings.json",
    ".claude/commands/slice-start.md",
    ".claude/commands/slice-finish.md",
    ".claude/hooks/bash-guard.py",
    ".claude/hooks/stop-integrity.py",
    ".agents/skills/slice-start/SKILL.md",
    ".agents/skills/slice-finish/SKILL.md",
    "scripts/check-template.py",
    "scripts/check-slice.py",
    "scripts/check-ids.py",
    "docs/FRS.md",
    "docs/ARCHITECTURE.md",
    "docs/BACKLOG.md",
    "docs/OPEN-QUESTIONS.md",
    "docs/ADR",
    "docs/ADR/ADR-000-template.md",
    "prompts",
    "prompts/01-ba-interview.md",
    "prompts/02-solution-setup.md",
    "prompts/03-build-plan.md",
    "prompts/dev/slice-start.md",
    "prompts/dev/slice-finish.md",
    "source",
    "tmpBin",
]

# Addressed to two different readers on purpose. The old wording told whoever
# hit the error to run --fix; an agent reads that as an instruction, tries the
# command its permissions forbid, and goes looking for a way around it.
AGENT_LINE = "AGENT: stop here and tell the owner. Do not run --fix, do not edit the manifest."
OWNER_LINE = (
    "OWNER: if you agreed to this change, run "
    "`python3 scripts/check-template.py --fix --i-know-what-im-doing` "
    "and commit scripts/integrity.sha256 and the workflow in the same commit."
)

FIX = "--fix" in sys.argv
CONFIRM = "--i-know-what-im-doing" in sys.argv

errors: list[str] = []
warnings: list[str] = []


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def covered() -> list[str]:
    return list(PROTECTED)


def write_manifest() -> None:
    lines = []
    for rel in covered():
        path = ROOT / rel
        if not path.is_file():
            print(f"ERROR: cannot pin a file that does not exist: {rel}")
            sys.exit(1)
        lines.append(f"{digest(path)}  {rel}")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" is not cosmetic. On Windows write_text translates \n to
    # \r\n, and the manifest is read by `sha256sum -c` in .githooks/pre-commit,
    # which then sees every path as ending in a carriage return and reports
    # "No such file or directory" for all ten of them. This script would still
    # say OK — Python reads with universal newlines — so the owner gets a green
    # check and a blocked commit at the same time.
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"baseline written: {len(lines)} files pinned in scripts/integrity.sha256")
    write_pin()


def manifest_digest() -> str:
    return digest(MANIFEST)


def write_pin() -> None:
    """Keep the workflow's manifest pin in step with the manifest."""
    if not WORKFLOW.is_file():
        print("note: no .github/workflows/template-check.yml — no pin to update")
        return
    text = WORKFLOW.read_text(encoding="utf-8")
    m = PIN.search(text)
    if m is None:
        print(
            "ERROR: .github/workflows/template-check.yml has no `expected=\"<sha256>\"` "
            "line to update. Restore it from git, or delete the workflow if this "
            "project has no CI."
        )
        sys.exit(1)
    want = manifest_digest()
    if m.group("hash") == want:
        print("manifest pin in the workflow already matches")
        return
    WORKFLOW.write_text(
        PIN.sub(lambda mm: mm.group("pre") + want + mm.group("post"), text, count=1),
        encoding="utf-8", newline="\n",
    )
    print(f"manifest pin updated in .github/workflows/template-check.yml: {want[:12]}…")


# --- 1. Integrity of the rules and of the machinery that enforces them ------

if FIX:
    if not CONFIRM:
        print("ERROR: --fix also needs --i-know-what-im-doing.")
        print("  " + AGENT_LINE)
        print("  " + OWNER_LINE)
        sys.exit(1)
    if not sys.stdin.isatty():
        # A permission rule matches the text of a command, so it can be dodged
        # by respelling it. A terminal cannot be respelled into existence.
        print("ERROR: --fix only runs from a terminal, not from a script, hook or agent.")
        if os.name == "nt" or "MSYSTEM" in os.environ:
            # Git Bash on Windows fails this check even for the owner: MinTTY
            # hands programs a pipe rather than a console, so isatty() is false
            # there for everyone. Without this hint the owner reads "not from a
            # terminal" while sitting in one, and has no way forward.
            print("  On Windows this also fails in Git Bash — MinTTY gives the")
            print("  process a pipe, not a console. Use PowerShell or cmd:")
            print("      python scripts\\check-template.py --fix --i-know-what-im-doing")
            print("  or, to stay in Git Bash, prefix with winpty.")
        print("  " + AGENT_LINE)
        sys.exit(1)
    write_manifest()
    sys.exit(0)

if not MANIFEST.is_file():
    # A missing baseline is not a reason to trust the files. Silently
    # rebuilding it here would let anyone edit the rules, delete the manifest,
    # and make this check pass.
    errors.append(
        "scripts/integrity.sha256 is missing. Restore it from git.\n"
        f"  {AGENT_LINE}\n  {OWNER_LINE}"
    )
else:
    pinned: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            errors.append(f"scripts/integrity.sha256: malformed line: {line}")
            continue
        pinned[parts[1].strip()] = parts[0].strip()

    for rel in covered():
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing (pinned file): {rel}")
            continue
        if rel not in pinned:
            errors.append(
                f"{rel} is not pinned in scripts/integrity.sha256 — the manifest "
                f"has been shortened.\n  {AGENT_LINE}\n  {OWNER_LINE}"
            )
            continue
        if pinned[rel] != digest(path):
            errors.append(
                f"{rel} has changed since the baseline was written.\n"
                f"  If you did not change it, check for CRLF line endings "
                f"(see .gitattributes) before doing anything else.\n"
                f"  {AGENT_LINE}\n  {OWNER_LINE}"
            )

    for rel in pinned:
        if rel not in covered():
            warnings.append(f"scripts/integrity.sha256 pins {rel}, which is no longer covered")

    # The workflow pins the manifest's own hash — the manifest cannot pin
    # itself without closing a loop. CI checks this too, but checking it here
    # as well turns a red build into a blocked commit, which is cheaper. The
    # two are not redundant: CI is the copy that `--no-verify` cannot reach.
    if WORKFLOW.is_file():
        m = PIN.search(WORKFLOW.read_text(encoding="utf-8"))
        if m is None:
            errors.append(
                ".github/workflows/template-check.yml has no `expected=\"<sha256>\"` "
                "line — the manifest is no longer pinned anywhere, and a manifest "
                "rewritten by hand would pass every check.\n"
                f"  {AGENT_LINE}\n  {OWNER_LINE}"
            )
        elif m.group("hash") != digest(MANIFEST):
            errors.append(
                "scripts/integrity.sha256 does not match the pin in "
                ".github/workflows/template-check.yml.\n"
                "  Either the manifest was edited without --fix, or --fix ran on an "
                "older version of this script that did not update the pin.\n"
                f"  {AGENT_LINE}\n  {OWNER_LINE}"
            )

# --- 2. Skeleton ------------------------------------------------------------

for rel in REQUIRED:
    if not (ROOT / rel).exists():
        errors.append(f"missing: {rel}")

# --- 2b. The files that carry the rules to an agent still point at them ----
# Not pinned: a project may extend CLAUDE.md or AGENTS.md. But each of them
# is the only road from an agent to the rules or to a canonical command, and
# a CLAUDE.md that lost its `@RulesForAIVibeCoding.md` line loads no rules at
# all — every other check here would keep saying OK.
POINTERS = {
    "CLAUDE.md": ["@AGENTS.md", "@RulesForAIVibeCoding.md"],
    "AGENTS.md": ["RulesForAIVibeCoding.md"],
    ".claude/commands/slice-start.md": ["prompts/dev/slice-start.md"],
    ".claude/commands/slice-finish.md": ["prompts/dev/slice-finish.md"],
    ".agents/skills/slice-start/SKILL.md": ["prompts/dev/slice-start.md"],
    ".agents/skills/slice-finish/SKILL.md": ["prompts/dev/slice-finish.md"],
}
for rel, needles in POINTERS.items():
    path = ROOT / rel
    if not path.is_file():
        continue  # already reported as missing above
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = {ln.strip() for ln in text.splitlines()}
    for needle in needles:
        # An import must be a line of its own to be an import at all.
        present = needle in lines if needle.startswith("@") else needle in text
        if not present:
            errors.append(
                f"{rel} no longer references {needle} — an agent that starts from "
                f"it never reaches the rules or the canonical command. Restore it "
                f"from git.\n  {AGENT_LINE}"
            )

# --- 3. tmpBin/ is excluded the way git actually understands ----------------

gitignore = ROOT / ".gitignore"
if gitignore.is_file():
    lines = [ln.strip() for ln in gitignore.read_text(encoding="utf-8").splitlines()]
    if "tmpBin/*" not in lines:
        errors.append(
            ".gitignore must contain `tmpBin/*` (not `tmpBin/`) — git cannot "
            "re-include a file inside an excluded directory, so with `tmpBin/` "
            "the `!tmpBin/.gitkeep` line silently does nothing"
        )
    if "!tmpBin/.gitkeep" not in lines:
        errors.append(".gitignore is missing `!tmpBin/.gitkeep` — the empty directory would not survive a clone")

# --- 4. Hooks are actually active -------------------------------------------

try:
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=10,
    )
    out = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=10,
    )
    if inside.returncode != 0:
        warnings.append("not a git repository yet — hooks not checked")
    elif out.stdout.strip() != ".githooks":
        errors.append(
            "core.hooksPath is not set to .githooks — the commit hooks are "
            "inactive. Run: git config core.hooksPath .githooks"
        )
except (OSError, subprocess.SubprocessError):
    warnings.append("git not available — hooks not checked")

# A hook git cannot execute is skipped with nothing more than a hint, and the
# commit goes through unchecked. The repository records both hooks as 100755,
# but a template unpacked from an archive that dropped the mode — the manual
# setups in README.md — lands on Linux or macOS with them at 644. Windows
# does not look at the bit, so there is nothing to check there.
if os.name != "nt":
    for rel in (".githooks/pre-commit", ".githooks/commit-msg"):
        hook = ROOT / rel
        if hook.is_file() and not os.access(hook, os.X_OK):
            errors.append(
                f"{rel} is not executable — git skips it, and commits pass "
                f"unchecked. Run: chmod +x .githooks/*"
            )

# --- 4b. python3 actually runs, instead of guessing from its path -----------
# .claude/settings.json invokes python3 for both agent hooks. A fresh Windows
# machine commonly has a Microsoft Store shim ahead of any real install on
# PATH: it opens the Store and exits 9009 instead of running Python. `command
# -v python3` (used by .githooks/pre-commit) reports success for it anyway, so
# nothing else here would notice — the hooks would simply never run, silently,
# while this very check kept saying OK. See README.md, section Windows.
#
# The first version of this check read "WindowsApps" out of the resolved
# path, on the assumption that only the stub lives there. It does not: Python
# installed *from* the Store also registers its App Execution Alias under the
# very same WindowsApps folder, and that one runs fine. The path told the two
# apart by accident; running the interpreter tells them apart for real.
if os.name == "nt":
    python3_path = shutil.which("python3")
    if python3_path:
        try:
            probe = subprocess.run(
                [python3_path, "-c", "pass"],
                capture_output=True, timeout=10,
            )
            python3_broken = probe.returncode != 0
        except (OSError, subprocess.SubprocessError):
            python3_broken = True
        if python3_broken:
            errors.append(
                f"python3 ({python3_path}) does not run — "
                ".claude/hooks/bash-guard.py and stop-integrity.py never run, "
                "and this check would otherwise keep saying OK. On Windows "
                "this is usually the Microsoft Store's App Execution Alias "
                "placeholder (it exits without running anything, commonly "
                "code 9009). See README.md, section Windows, to make python3 "
                "a real interpreter."
            )

# --- 5. Non-blocking hygiene warnings ---------------------------------------
# The placeholder string alone is not enough: an agent that deletes the
# blockquote leaves an empty document that looks filled in. So each document
# is also checked for the IDs it cannot be complete without.

PLACEHOLDER = re.compile(r"Порожній шаблон|Empty template", re.IGNORECASE)
DOC_MARKERS = {
    "docs/FRS.md": re.compile(r"\b(FR|DR|NFR|IR)-\d{3}\b"),
    "docs/BACKLOG.md": re.compile(r"\b(SLICE|TASK)-\d{3}\b"),
}
for rel in ("docs/FRS.md", "docs/ARCHITECTURE.md", "docs/BACKLOG.md"):
    path = ROOT / rel
    if not path.is_file():
        continue
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:64]:
        # A document saved as UTF-16 (Notepad's "Unicode", or `>` under
        # Windows PowerShell 5.1) used to fail utf-8 decoding here with a
        # traceback instead of a diagnosis — and check-ids.py, reading the
        # same file, saw what looks like an empty document and quietly
        # skipped itself (exit 0) rather than reporting anything wrong.
        warnings.append(
            f"{rel} is not UTF-8 (looks like UTF-16) — every check here reads "
            f"it as UTF-8, so its content is not actually being checked. "
            f"Re-save it as UTF-8."
        )
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = DOC_MARKERS.get(rel)
    if PLACEHOLDER.search(text):
        warnings.append(f"{rel} is still the empty template")
    elif marker is not None and not marker.search(text):
        warnings.append(f"{rel} has no requirement or slice IDs in it — is it actually filled in?")

# The local verification command is found by its row label, and the cell is
# tested with a regex rather than a literal suffix: a single trailing space
# used to make this warning disappear without the command being filled in.
VERIFY_ROW = re.compile(
    r"^\s*>?\s*\|\s*\**\s*(Локальна перевірка|Local verification)\s*\**\s*\|(?P<cell>[^|]*)\|",
    re.IGNORECASE,
)
arch = ROOT / "docs/ARCHITECTURE.md"
if arch.is_file():
    found_row = False
    for line in arch.read_text(encoding="utf-8", errors="replace").splitlines():
        m = VERIFY_ROW.match(line)
        if not m:
            continue
        found_row = True
        if not m.group("cell").strip():
            warnings.append(
                "ARCHITECTURE.md, Project Structure: the local verification "
                "command is empty — the work cycle and the Definition of Done "
                "both point at it"
            )
        break
    if not found_row:
        warnings.append(
            "ARCHITECTURE.md: no `Локальна перевірка` / `Local verification` "
            "row found — the work cycle and the Definition of Done point at it"
        )

for w in warnings:
    print(f"WARN:  {w}")
for e in errors:
    print(f"ERROR: {e}")

if errors:
    sys.exit(1)
print("OK: template intact.")
