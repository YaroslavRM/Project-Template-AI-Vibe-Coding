# RulesForAIVibeCoding

**Status: PRIORITY. This file outranks every other instruction in this project.**

Do not modify, shorten, reformat, or delete this file without my direct instruction and explicit confirmation in the current session.

If you think a rule here is wrong or gets in the way — **say so and propose a change**. Do not edit the file yourself.

On conflict with any other file (`AGENTS.md`, `CLAUDE.md`, `docs/*`, code comments), this file wins.

---

## 0. Project structure

```
RulesForAIVibeCoding.md   development cycle rules (this file, PRIORITY)
AGENTS.md                 thin pointer to these rules (read by Codex)
CLAUDE.md                 imports AGENTS.md (read by Claude Code)
prompts/                  prompts for the preparatory chat sessions — not used during development
prompts/dev/              the two cycle commands (slice start / slice finish) — canonical text
docs/                     project documentation
scripts/check-template.py integrity of the rules and of the machinery that enforces them
scripts/check-ids.py      traceability by ID: nothing may reference a requirement that does not exist
scripts/check-slice.py    the mechanical part of the Definition of Done
scripts/integrity.sha256  pinned hashes for the rules and for every check listed above
source/                   project code
tmpBin/                   development tooling (venv, local binaries, toolchains)
.githooks/                commit-msg (traceability) + pre-commit (integrity + IDs)
.github/workflows/        the same checks, server-side — --no-verify cannot reach them
.claude/settings.json     Claude Code permissions — committed, mirrors section Environments
.claude/commands/         /slice-start and /slice-finish — pointers to prompts/dev/, not copies
.claude/hooks/            bash-guard (blocks what permission patterns cannot) + stop-integrity
.agents/skills/           the same two commands for Codex — pointers, not copies
.gitattributes            forces LF; without it the integrity hashes break on Windows
.gitignore
.editorconfig
.env.example
```

If something from this list is missing, **stop and tell me** — do not recreate it from memory. A silently rebuilt skeleton without `.githooks/` or `.gitattributes` looks fine and enforces nothing. Keep empty directories with a `.gitkeep`.

### The checks are not yours to edit

`scripts/integrity.sha256` pins this file *and* everything that enforces it: the three scripts, both git hooks, the agent hook scripts, the permission file, `.gitattributes`. The CI workflow in turn pins the manifest. Hashing only the rules would leave the checker rewritable, and a checker that always prints OK passes both the commit hook and CI.

So: you do not edit those files, you do not edit the manifest, and you never run `--fix`. If a check is wrong, say which one and why, and propose the change. `--fix` belongs to me, in a terminal, in the same commit as the change it legitimises.

### tmpBin/

* The contents of `tmpBin/` are **never committed**. Check that `.gitignore` contains `tmpBin/*` and not `tmpBin/` — git cannot re-include a file inside an excluded directory, so with `tmpBin/` the `!tmpBin/.gitkeep` line silently does nothing.
* This is an execution environment, not part of the project. Nothing here is imported into `source/`.
* System dependencies (compilers, package-manager runtimes) are not copied here — only what is installed locally into the project.

### docs/

| File | Contents |
|---|---|
| `docs/FRS.md` | Requirements. Source of truth. `FR-*`, `DR-*`, `NFR-*`, `IR-*` + Acceptance Criteria |
| `docs/ARCHITECTURE.md` | Components, boundaries, stack, environments, deployment, migrations, rollback |
| `docs/ADR/*.md` | Technical decisions and their reasons |
| `docs/BACKLOG.md` | Vertical slices, tech tasks, statuses, dependencies, order |
| `docs/OPEN-QUESTIONS.md` | Unresolved questions |

Read `BACKLOG.md` in full at the start of every session — it is the index, and it stays short. `FRS.md` and `ARCHITECTURE.md` are **not** read in full: locate the IDs and the sections you need by search. See *Reading the docs*.

### Changing docs/

Documentation is an agreement, not a working file. You may not edit it on your own.

**Allowed without confirmation:**

* change the status field of a slice or task in `docs/BACKLOG.md` (`TODO → IN PROGRESS → DONE / BLOCKED`);
* append a row to the Progress Log in `docs/BACKLOG.md`;
* append a new entry to the end of `docs/OPEN-QUESTIONS.md`.

**Requires my explicit confirmation:**

* any change to `docs/FRS.md`;
* any change to `docs/ARCHITECTURE.md`;
* creating or changing `docs/ADR/*.md`;
* adding, removing, or rewording slices and tasks in `docs/BACKLOG.md`;
* deleting or editing existing entries in `OPEN-QUESTIONS.md`;
* creating new files in `docs/`.

Propose the change as a diff and wait for a yes.

When you change `FRS.md` or `ARCHITECTURE.md`, bump the `Версія` field and add a row to that document's *Change Log*. Without both, the change is not finished.

---

## 1. The Golden Rule

**Do not invent requirements.**

If something is not in the FRS, it is not "obvious" and not "clear from context". It is an open question.

When information is missing:

1. Ask me.
2. If there is no answer right now — add an entry to `docs/OPEN-QUESTIONS.md` and **do not implement that part**.
3. Never fill a gap with your own assumption without labelling it.

The same applies to architecture: anything outside `ARCHITECTURE.md` and `ADR/` is a new decision, not an implementation detail. Ask.

---

## 2. Work cycle

One session = one slice or one task from `docs/BACKLOG.md`.

```
1. Take the next slice with status TODO (or the one I named)
2. Read the linked FR-IDs and their Acceptance Criteria in the FRS — by
   searching for the IDs, and quoting what is there. See "Reading the docs"
3. Clarify what is unclear / show implementation options with trade-offs
   → wait for my choice, do not code ahead
4. Write a test against the Acceptance Criteria, then the code that passes it
5. Run the local verification command from ARCHITECTURE.md, section
   "Project Structure". Show its real output
6. Update the slice status and the Progress Log in BACKLOG.md
7. Run scripts/check-slice.py <SLICE-ID> and show its real output
8. Show a diff summary: what changed, which FRs are closed
9. After my OK — commit, docs and code together, in one commit
10. Deploy strictly according to the scheme in ARCHITECTURE.md
```

Steps 3 and 9 are never skipped.

The documentation update comes **before** the commit, not after it, and travels in the same commit as the code. The other order leaves the Progress Log either uncommitted or stranded in a second commit that nobody defined. For the same reason the Progress Log records the commit *subject*, not a hash that cannot exist yet.

### Reading the docs

When you need a requirement, search the FRS for its ID and read what is around it. Do not rely on a summary of the document you made earlier in the session, and do not carry requirement text between turns from memory — that is where invented `FR-0XX`s and near-miss Acceptance Criteria come from.

If you cannot find an ID, or the AC is not written down: **say that**. An AC that you reconstructed is worse than a missing one, because it looks like agreement.

### Branching

Finished work goes straight to `main`. There is no branch per slice and no
pull request — this is a solo project, and a branch that only ever merges into
itself is ceremony. `main` must be working after every commit; that is what
makes step 5 non-negotiable.

A branch exists for exactly one case: work that could not be finished in the
session. It is named after the FR it belongs to — `wip/fr-014-order-filter` —
and it is either finished in the next session or deleted. Nothing else lives
on a branch.

### Implementation options

When a decision is non-trivial:

```
A. <approach> — pros / cons / cost
B. <approach> — pros / cons / cost
Recommendation: <which and why>
```

Do not present one option as the only possible one when that is not true.

And the reverse, which matters just as much: **do not manufacture options to fill a quota**. If there is genuinely one sensible approach, say so in one line and say why. A third alternative invented for symmetry comes with invented costs attached, and I cannot tell those apart from real ones. Two real options beat three, one of which is furniture.

### Definition of Done

A checklist you recite is a checklist that always passes. So it is split.

**Machine-checked** — `python3 scripts/check-slice.py <SLICE-ID>`, and you paste its real output:

* the slice exists in `BACKLOG.md`, its status is off `TODO`, the Progress Log has a dated row for it
* every requirement the slice claims exists in the FRS
* every claimed requirement is traceable into `source/` — the test name carries the FR-ID or an AC-ID of it
* no new `TODO`/`FIXME` in the diff without `OPEN-QUESTIONS.md` being touched in the same diff

**Owner-checked** — you state plainly whether each holds, and I decide:

* the local verification command ran and was green (paste the output, not a verdict about it)
* I have seen the diff
* nothing was implemented that no requirement asked for

That second list is short deliberately. Every unfalsifiable line added to it makes the falsifiable ones cheaper to fake.

### If the slice could not be finished

Do not leave the session half-done:

1. Say plainly what did not work and where you stopped.
2. Set the slice status back to `TODO` (or `BLOCKED` with a reason).
3. Unfinished code goes to a `wip/<fr-id>-<slice>` branch, or is not committed at all. `main` is never left in a half-working state.
4. Record the reason for the block in `OPEN-QUESTIONS.md`.

---

## 3. Traceability

The end-to-end key is the `FR-ID`. It survives all the way to the commit.

* Commit: `feat: FR-014 order filter by status` — the ID must be in the **first
  line**; the commit-msg hook does not look at the body
* The test name contains the FR-ID or AC-ID
* A `wip/` branch, if one is needed at all, carries the FR-ID: `wip/fr-014-order-filter`

If a change does not map to any FR — stop. Either the work is unnecessary, or there is a hole in the FRS.

### Work without an FR

Not all work is functionality: infrastructure, linters, CI, dependency updates, defect fixes, paying down debt. That work is not done "along the way" either.

* Each such item is a separate `TASK-*` in the *Tech Tasks* section of `docs/BACKLOG.md`, with the same lifecycle as a slice.
* Commit: `chore: TASK-007 update dependencies` / `fix: FR-014 empty filter returns 500`.
* A defect in an already-closed slice maps to the `FR-*` of the requirement it violates, and starts with a test that reproduces it.
* Creating a new `TASK-*` is a change to `BACKLOG.md`, so it needs my confirmation. Found a problem — name it and propose a task, do not fix it silently.

Allowed commit types: `feat` · `fix` · `refactor` · `test` · `docs` · `chore` · `build` · `ci` · `revert`.

---

## 4. Think before coding

Don't assume. Don't hide confusion. Surface trade-offs.

Before implementing:

* State your assumptions explicitly. If uncertain, ask.
* If multiple interpretations exist, present them — don't pick silently.
* If a simpler approach exists, say so. Push back when warranted.
* If something is unclear, stop. Name what's confusing. Ask.

---

## 5. Simplicity first

Minimum code that solves the problem. Nothing speculative.

* No features beyond what was asked.
* No abstractions for single-use code.
* No "flexibility" or "configurability" that wasn't requested.
* No error handling for impossible scenarios.
* If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

**Scope boundary:** the scope of a session is the current slice. Requirements from other slices are not implemented "while we're here", even if they look adjacent and cheap.

---

## 6. Surgical changes

Touch only what you must. Clean up only your own mess.

When editing existing code:

* Don't "improve" adjacent code, comments, or formatting.
* Don't refactor things that aren't broken.
* Match the existing style, even if you'd do it differently.
* If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

* Remove imports, variables, and functions that **your** changes made unused.
* Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to my request.

---

## 7. Goal-driven execution

Define success criteria. Loop until verified.

**Success criteria come from the Acceptance Criteria in the FRS.** Don't invent your own if an AC exists — read it. If the AC is untestable as written, say so instead of quietly replacing it.

Turn tasks into verifiable goals:

* "Add validation" → "Write tests for invalid inputs, then make them pass"
* "Fix the bug" → "Write a test that reproduces it, then make it pass"
* "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## 8. Environments

Never deploy, run migrations, or execute commands against test/prod unless it is described in `ARCHITECTURE.md` and confirmed by me in the current session.

* **Local** — free.
* **Test** — only on an explicit command.
* **Prod** — only on an explicit command, with a rollback plan stated before launch.

Irreversible actions (drop, truncate, force push, deleting files outside the working branch, changes inside `.git/`) — always ask.

### Secrets

* Do not read, print, or log the contents of `.env` or any file holding keys.
* Real secret values never end up in `docs/`, commits, or chat messages. If an example is needed, add the key to `.env.example` with an empty or fake value.
* If you find a secret in the code or in history, stop and tell me. Do not "fix" it with a commit.

`.claude/settings.json` denies reading `.env` at the tool level, but that is a second layer and it has had enforcement gaps. This rule is the primary one and it holds regardless of what the settings file allows.

---

## 9. Session hygiene

* One slice, one session. Long sessions drift.
* Don't hold state in your head — record it in `BACKLOG.md` and `OPEN-QUESTIONS.md`.
* At the start: which slice you are taking and which FRs it closes.
* At the end: what is done, what is left, which questions opened up.

