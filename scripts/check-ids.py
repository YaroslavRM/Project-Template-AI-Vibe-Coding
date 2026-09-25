#!/usr/bin/env python3
"""Traceability check by ID, without knowing the document format.

Usage:  python3 scripts/check-ids.py

This deliberately knows nothing about headings, tables or section names. It
collects every `FR-014`-shaped identifier from each place it can appear and
compares the sets. Renaming a section cannot break it.

Blocking (exit 1) — an identifier is used somewhere but appears nowhere in
the FRS. That is the expensive kind of mistake: a slice pointing at FR-023
that was never written, an AC-021 quoted in a test that does not exist. It
is created in the chat sessions, where nothing can catch it, and it survives
for months.

Non-blocking (WARN) — an identifier exists in the FRS but no slice covers it,
or an ADR is referenced without a file. Those are gaps, not inventions.

Skips itself entirely while docs/FRS.md is still the empty template: there is
nothing to compare against yet.
"""
from __future__ import annotations

import re
import subprocess
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRS = ROOT / "docs/FRS.md"
BACKLOG = ROOT / "docs/BACKLOG.md"
ARCH = ROOT / "docs/ARCHITECTURE.md"
DEPLOY = ROOT / "docs/DEPLOY.md"
ADR_DIR = ROOT / "docs/ADR"
SOURCE = ROOT / "source"

REQ_ID = re.compile(r"\b(?:FR|DR|NFR|IR|BR)-\d{3}\b")
AC_ID = re.compile(r"\bAC-\d{3}\b")
ADR_ID = re.compile(r"\bADR-\d{3}\b")

# Only the fallback for a working copy with no usable git — the real filter is
# .gitignore, read through `git ls-files` in source_files().
SKIP_DIRS = {
    ".git", "node_modules", "vendor", ".venv", "venv", "__pycache__", "dist",
    "build", "target", ".next", ".turbo", ".gradle", "Pods", "coverage",
    "htmlcov", ".pytest_cache", ".mypy_cache", ".ruff_cache", "tmpBin",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb", ".php", ".java",
    ".kt", ".cs", ".swift", ".sql", ".sh", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".json", ".html", ".css", ".vue", ".svelte", ".feature",
}
MAX_BYTES = 1_000_000

errors: list[str] = []
warnings: list[str] = []


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def git_out(*args: str) -> str | None:
    """Stdout of a git command, or None when git could not answer.

    None and "" are different answers on purpose: "" means git ran and found
    nothing, None means there was no usable git. source_files() falls back to a
    directory walk only in the second case.
    """
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def source_files() -> list[Path]:
    """Files under source/ that belong to the project.

    The list comes from git: tracked files, plus untracked ones that .gitignore
    does not exclude. This runs on every commit, so the cost matters — but the
    reason is correctness first. Third-party code is not the project's code: an
    `AC-123` that happens to appear in a vendored package or its changelog used
    to be reported as an invented ID and blocked the commit.
    """
    if not SOURCE.is_dir():
        return []
    listing = git_out(
        "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "source"
    )
    if listing is None:
        print("WARN:  git unavailable — falling back to the SKIP_DIRS name list")
        candidates = list(SOURCE.rglob("*"))
    else:
        # A merge conflict lists the same path once per stage; dedupe, keep order.
        candidates = [ROOT / rel for rel in dict.fromkeys(listing.split("\0")) if rel]
    out: list[Path] = []
    for path in candidates:
        try:
            parts = path.relative_to(ROOT).parts
        except ValueError:
            parts = path.parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        out.append(path)
    return out


def report(kind: str, missing: set[str], where: str) -> None:
    if not missing:
        return
    ids = ", ".join(sorted(missing))
    errors.append(
        f"{where} references {kind} that do not appear in docs/FRS.md: {ids}\n"
        f"  Either the requirement was never written, or the ID was invented. "
        f"Do not add it to the FRS on your own — raise it with the owner or "
        f"open an entry in docs/OPEN-QUESTIONS.md."
    )


if not FRS.is_file():
    print("WARN:  docs/FRS.md is missing — nothing to check")
    sys.exit(0)

frs_text = read(FRS)
frs_reqs = set(REQ_ID.findall(frs_text))
frs_acs = set(AC_ID.findall(frs_text))

if not frs_reqs:
    print("WARN:  docs/FRS.md has no requirement IDs yet — traceability check skipped")
    sys.exit(0)

# --- Referenced but undefined ----------------------------------------------

if BACKLOG.is_file():
    backlog_text = read(BACKLOG)
    report("requirement IDs", set(REQ_ID.findall(backlog_text)) - frs_reqs, "docs/BACKLOG.md")
    report("acceptance criteria", set(AC_ID.findall(backlog_text)) - frs_acs, "docs/BACKLOG.md")

if ARCH.is_file():
    arch_text = read(ARCH)
    report("requirement IDs", set(REQ_ID.findall(arch_text)) - frs_reqs, "docs/ARCHITECTURE.md")

# The release runbook names what a release changes, and it is written by the
# agent at release time — the same place an invented ID gets typed in.
if DEPLOY.is_file():
    deploy_text = read(DEPLOY)
    report("requirement IDs", set(REQ_ID.findall(deploy_text)) - frs_reqs, "docs/DEPLOY.md")
    report("acceptance criteria", set(AC_ID.findall(deploy_text)) - frs_acs, "docs/DEPLOY.md")

# In source, the same ID is usually spelled FR_014 or FR014: hyphens are not
# valid in identifiers, and the rules ask for the ID in the test name.
# Not \b on the left: in test_FR_014 the underscore is a word character, so a
# word boundary never fires there. Case-insensitive, because check-slice.py
# accepts `test_fr_014` as traceability (pep8-naming rejects the capitalised
# form) — so an invented `fr_999` in exactly that spelling must be caught
# here too, not only the capitalised one.
SRC_REQ_ID = re.compile(
    r"(?<![A-Za-z0-9])(FR|DR|NFR|IR|BR)[-_]?(\d{3})(?![0-9])", re.IGNORECASE
)
SRC_AC_ID = re.compile(r"(?<![A-Za-z0-9])AC[-_]?(\d{3})(?![0-9])", re.IGNORECASE)

for path in source_files():
    text = read(path)
    rel = path.relative_to(ROOT)
    found_reqs = {f"{p.upper()}-{n}" for p, n in SRC_REQ_ID.findall(text)}
    found_acs = {f"AC-{n}" for n in SRC_AC_ID.findall(text)}
    report("requirement IDs", found_reqs - frs_reqs, str(rel))
    report("acceptance criteria", found_acs - frs_acs, str(rel))

# --- ADR files referenced but absent ---------------------------------------

referenced_adrs: set[str] = set()
for path in (ARCH, BACKLOG):
    if path.is_file():
        referenced_adrs |= set(ADR_ID.findall(read(path)))
existing_adrs = {
    m.group(0)
    for f in (ADR_DIR.glob("ADR-*.md") if ADR_DIR.is_dir() else [])
    for m in [ADR_ID.match(f.name.upper())]
    if m
}
for adr in sorted(referenced_adrs - existing_adrs - {"ADR-000"}):
    warnings.append(f"{adr} is referenced but there is no docs/ADR/{adr}-*.md file")

# --- Coverage gaps (non-blocking) ------------------------------------------

if BACKLOG.is_file():
    backlog_text = read(BACKLOG)
    functional = {i for i in frs_reqs if i.startswith(("FR-", "IR-"))}
    uncovered = sorted(functional - set(REQ_ID.findall(backlog_text)))
    if uncovered:
        warnings.append(
            "no slice or task in docs/BACKLOG.md mentions: " + ", ".join(uncovered)
        )

for w in warnings:
    print(f"WARN:  {w}")
for e in errors:
    print(f"ERROR: {e}")

if errors:
    sys.exit(1)
print("OK: traceability IDs consistent.")
