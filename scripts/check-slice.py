#!/usr/bin/env python3
"""Mechanical part of the Definition of Done.

Usage:  python3 scripts/check-slice.py SLICE-014
        python3 scripts/check-slice.py TASK-007

Run it before the commit that closes a slice, on the working tree.

Why this exists: a Definition of Done that an agent recites is a Definition of
Done that always passes. Everything here returns an exit code instead. What is
left over is printed at the end as the part a human still has to judge — kept
short on purpose, because a checklist full of unfalsifiable lines makes the
falsifiable ones cheap to fake too.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "docs/BACKLOG.md"
FRS = ROOT / "docs/FRS.md"
OQ = ROOT / "docs/OPEN-QUESTIONS.md"
SOURCE = ROOT / "source"

ID_ARG = re.compile(r"^(SLICE|TASK)-\d{3}$")
REQ_ID = re.compile(r"\b(?:FR|DR|NFR|IR)-\d{3}\b")
AC_ID = re.compile(r"\bAC-\d{3}\b")
STATUS = re.compile(r"\b(TODO|IN PROGRESS|DONE|BLOCKED)\b")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".turbo", "coverage", "htmlcov", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "tmpBin",
}

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((ok, label))


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30
        )
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def slice_block(text: str, slice_id: str) -> list[str]:
    """Lines from the heading that names the ID up to the next heading."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") and slice_id in line:
            start = i
            break
    if start is None:
        return []
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.lstrip().startswith("#"):
            break
        block.append(line)
    return block


def main() -> int:
    if len(sys.argv) < 2 or not ID_ARG.match(sys.argv[1]):
        print("usage: python3 scripts/check-slice.py SLICE-014 | TASK-007")
        return 2
    slice_id = sys.argv[1]

    backlog = read(BACKLOG)
    if not backlog:
        print("ERROR: docs/BACKLOG.md is missing or empty")
        return 1

    block = slice_block(backlog, slice_id)
    check(bool(block), f"{slice_id} exists as a section in docs/BACKLOG.md")

    block_text = "\n".join(block)

    # Status moved off TODO.
    statuses = STATUS.findall(block_text)
    check(
        bool(statuses) and statuses[0] in {"DONE", "BLOCKED"},
        f"{slice_id} status is DONE or BLOCKED (found: {statuses[0] if statuses else 'none'})",
    )

    # Progress Log row: any table row carrying both a date and the ID.
    logged = any(
        slice_id in line and DATE.search(line) and line.strip().startswith("|")
        for line in backlog.splitlines()
    )
    check(logged, f"Progress Log has a dated row for {slice_id}")

    # Every requirement the slice claims is traceable into source/.
    claimed = sorted(set(REQ_ID.findall(block_text)))
    if slice_id.startswith("SLICE-"):
        check(bool(claimed), f"{slice_id} names at least one requirement ID")
    if claimed:
        frs_text = read(FRS)
        unknown = [r for r in claimed if r not in frs_text]
        check(not unknown, f"all requirement IDs exist in FRS ({', '.join(unknown) or 'ok'})")

        source_text = ""
        if SOURCE.is_dir():
            for path in SOURCE.rglob("*"):
                if path.is_file() and not any(p in SKIP_DIRS for p in path.parts):
                    source_text += read(path)
        # The rules require the test name to carry the FR-ID or an AC-ID of it.
        frs_acs_for = {
            req: [ac for ac in set(AC_ID.findall(frs_text)) if _ac_near(frs_text, ac, req)]
            for req in claimed
        }
        untested = [
            req for req in claimed
            if not _mentions(source_text, req)
            and not any(_mentions(source_text, ac) for ac in frs_acs_for.get(req, []))
        ]
        check(
            not untested,
            "every claimed requirement appears in source/ (test names carry the ID): "
            + (", ".join(untested) or "ok"),
        )

    # New TODO/FIXME must come with an open question.
    diff = git("diff", "HEAD", "--unified=0")
    added_markers = [
        ln for ln in diff.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
        and re.search(r"\b(TODO|FIXME)\b", ln)
    ]
    if added_markers:
        touched_oq = "docs/OPEN-QUESTIONS.md" in git("diff", "HEAD", "--name-only")
        check(touched_oq, f"{len(added_markers)} new TODO/FIXME — docs/OPEN-QUESTIONS.md updated")
        for ln in added_markers[:5]:
            print(f"       {ln.strip()[:100]}")
    else:
        check(True, "no new TODO/FIXME in the diff")

    print()
    for ok, label in results:
        print(f"  [{'x' if ok else ' '}] {label}")

    print()
    print("Not mechanical — say plainly whether each holds, do not assume:")
    print("  - the local verification command from ARCHITECTURE.md ran and was green")
    print("  - the owner has seen the diff")
    print("  - nothing was implemented that no requirement asked for")

    failed = [label for ok, label in results if not ok]
    if failed:
        print(f"\nERROR: {len(failed)} Definition of Done item(s) not met.")
        return 1
    print("\nOK: mechanical Definition of Done met.")
    return 0


def _mentions(text: str, ident: str) -> bool:
    """FR-014 in a test name is usually spelled FR_014 or FR014.

    Identifiers with hyphens are not valid in most languages, so a test called
    test_FR_014_filter is the normal way to satisfy the traceability rule. Only
    matching the hyphenated form would fail every project that uses it.
    """
    prefix, number = ident.split("-")
    # Not \b: in test_FR_014_filter the underscore is itself a word character,
    # so \b never fires next to it.
    return re.search(rf"(?<![A-Za-z0-9]){prefix}[-_]?{number}(?![0-9])", text) is not None


def _ac_near(text: str, ac: str, req: str, window: int = 400) -> bool:
    """True when the AC-ID appears within a window of the requirement ID.

    Crude on purpose: it needs no knowledge of how the FRS lays out its
    acceptance criteria, and it is only used to widen a check, never to fail
    one that would otherwise pass.
    """
    for m in re.finditer(re.escape(ac), text):
        chunk = text[max(0, m.start() - window): m.start() + window]
        if req in chunk:
            return True
    return False


if __name__ == "__main__":
    sys.exit(main())
