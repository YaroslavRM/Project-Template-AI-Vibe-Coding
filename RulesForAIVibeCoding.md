# RulesForAIVibeCoding

**Status: PRIORITY. This file outranks every other instruction in this project.**

Do not modify, shorten, reformat, or delete this file without my direct instruction and explicit confirmation in the current session.

If you think a rule here is wrong or gets in the way — **say so and propose a change**. Do not edit the file yourself.

On conflict with any other file (`AGENTS.md`, `CLAUDE.md`, `docs/*`, code comments), this file wins.

---

## 0. Project structure

```
RulesForAIVibeCoding.md   development cycle rules (this file, PRIORITY)
README.md                 how to use the template: setup, the preparatory steps, Windows
AGENTS.md                 thin pointer to these rules (read by Codex)
CLAUDE.md                 imports AGENTS.md and this file (read by Claude Code)
prompts/                  prompts for the preparatory chat sessions (steps 1-3)
prompts/dev/              the two cycle commands (slice start / slice finish) — canonical text
docs/                     project documentation
scripts/check-template.py integrity of the rules and of the machinery that enforces them
scripts/check-ids.py      traceability by ID: nothing may reference a requirement that does not exist
scripts/check-slice.py    the mechanical part of the Definition of Done
scripts/integrity.sha256  pinned hashes for the rules and for every check listed above
source/                   project code
deploy/                   release tooling — its contents are decided in ARCHITECTURE.md; built by a TASK before the first release
tmpBin/                   development tooling (venv, local binaries, toolchains)
.githooks/                commit-msg (traceability) + pre-commit (integrity + IDs)
.github/workflows/        the same checks, server-side — --no-verify cannot reach them (optional: a project with no GitHub may delete it)
.claude/settings.json     Claude Code permissions — committed; enforces what patterns can: secrets, --no-verify, force-push, edits to agreements
.claude/commands/         /slice-start and /slice-finish — pointers to prompts/dev/, not copies
.claude/hooks/            bash-guard (blocks what permission patterns cannot) + stop-integrity
.agents/skills/           the same two commands for Codex — pointers, not copies
.gitattributes            forces LF; without it the integrity hashes break on Windows
.gitignore
.editorconfig
.env.example
```

If something from this list is missing, **stop and tell me** — do not recreate it from memory. A silently rebuilt skeleton without `.githooks/` or `.gitattributes` looks fine and enforces nothing. Keep empty directories with a `.gitkeep`. Items that may legitimately be absent: `.github/workflows/`, only when the project has no GitHub; `docs/DEPLOY.md`, only until step 2 (`prompts/02-solution-setup.md`) produces its skeleton; `deploy/`, only until the first release. `scripts/check-template.py` is the authority on the rest.

### The checks are not yours to edit

`scripts/integrity.sha256` pins this file *and* everything that enforces it: the three scripts, both git hooks, the agent hook scripts, the permission file, `.gitattributes`. The CI workflow in turn pins the manifest. Hashing only the rules would leave the checker rewritable, and a checker that always prints OK passes both the commit hook and CI.

So: you do not edit those files, you do not edit the manifest, and you never run `--fix`. If a check is wrong, say which one and why, and propose the change. `--fix` belongs to me, in a terminal, in the same commit as the change it legitimises.

The same holds for the files that carry these rules to an agent: `CLAUDE.md`, `AGENTS.md`, `prompts/` (including the canonical cycle commands in `prompts/dev/`), `.claude/commands/` and `.agents/skills/`. They are not pinned — a project may need to extend them — but a change to them needs my confirmation. `CLAUDE.md` without its import of this file loads no rules at all, and nothing else would notice.

### tmpBin/

* The contents of `tmpBin/` are **never committed**. Check that `.gitignore` contains `tmpBin/*` and not `tmpBin/` — git cannot re-include a file inside an excluded directory, so with `tmpBin/` the `!tmpBin/.gitkeep` line silently does nothing.
* This is an execution environment, not part of the project. Nothing here is imported into `source/`.
* System dependencies (compilers, package-manager runtimes) are not copied here — only what is installed locally into the project.

### docs/

| File | Contents |
|---|---|
| `docs/FRS.md` | Requirements. Source of truth. `BR-*` (business level — implemented through an `FR-*`, never committed against), `FR-*`, `DR-*`, `NFR-*`, `IR-*` + Acceptance Criteria |
| `docs/ARCHITECTURE.md` | Components, boundaries, stack, environments, deployment, migrations, rollback |
| `docs/ADR/*.md` | Technical decisions and their reasons |
| `docs/DEPLOY.md` | Runbook for the current release: version, the commit that was verified and the local verification that ran on it (the artifact is built from the runbook commit on top of it, which changes only `docs/`; a release to prod ships the test release's artifact instead of building one), what changes, the exact release commands, the checks to run after the release, what to do if it fails. Everything else in it depends on the platform, so its sections come from step 2 (`prompts/02-solution-setup.md`) as a skeleton. It holds the plan, not the outcome — the outcome goes to the Progress Log. Filled in at the first release, updated at every release |
| `docs/BACKLOG.md` | Vertical slices, tech tasks, statuses, dependencies, order |
| `docs/OPEN-QUESTIONS.md` | Unresolved questions |

Read `BACKLOG.md` in full at the start of every session — it is the index. `FRS.md` and `ARCHITECTURE.md` are **not** read in full: locate the IDs and the sections you need by search. See *Reading the docs*.

### Changing docs/

Documentation is an agreement, not a working file. You may not edit it on your own.

**Allowed without confirmation:**

* change the status of a slice or task in `docs/BACKLOG.md` (`TODO → IN PROGRESS → DONE / BLOCKED`; back to `TODO` when only the session ran out; `BLOCKED → IN PROGRESS` once it is unblocked) — its `**Статус:**` field, and the same status wherever `BACKLOG.md` repeats it: the Coverage Map, and the *Blocked* table, where a row is added when the slice is blocked and removed when it is unblocked;
* append a row to the Progress Log in `docs/BACKLOG.md`;
* append a new entry to the end of `docs/OPEN-QUESTIONS.md`.

**Requires my explicit confirmation:**

* any change to `docs/FRS.md`;
* any change to `docs/ARCHITECTURE.md`;
* creating or changing `docs/ADR/*.md`;
* creating or changing `docs/DEPLOY.md`;
* adding, removing, or rewording slices and tasks in `docs/BACKLOG.md`;
* deleting or editing existing entries in `OPEN-QUESTIONS.md`;
* creating new files in `docs/`.

Propose the change as a diff and wait for a yes.

When you change `FRS.md` or `ARCHITECTURE.md`, bump the `Версія` field and add a row to that document's *Change Log*. `DEPLOY.md` does the same with its `Реліз` field, one Change Log row per release. Without both, the change is not finished.

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
```

Steps 3 and 9 are never skipped.

Deployment is not a step of the cycle. It happens on my explicit command, by the
scheme in ARCHITECTURE.md — see *Environments*. A slice is finished when it is
committed, not when it is deployed.

The documentation update comes **before** the commit, not after it, and travels in the same commit as the code. The other order leaves the Progress Log either uncommitted or stranded in a second commit that nobody defined. For the same reason the Progress Log records the commit *subject*, not a hash that cannot exist yet.

### Reading the docs

When you need a requirement, search the FRS for its ID and read what is around it. Do not rely on a summary of the document you made earlier in the session, and do not carry requirement text between turns from memory — that is where invented `FR-0XX`s and near-miss Acceptance Criteria come from.

If you cannot find an ID, or the AC is not written down: **say that**. An AC that you reconstructed is worse than a missing one, because it looks like agreement.

### UI tests

If the project has a user interface, unit tests are not enough for it. Anything
the user sees is also covered by UI tests: end-to-end in a real browser (or the
platform's equivalent) against the Acceptance Criteria, plus visual checks where
the AC is about how something looks. They are part of the local verification
command in `ARCHITECTURE.md`, section *Project Structure* — not a separate check,
and never run against test or prod. The tools, browsers and viewports are
decided there; if they are not, it is a question, not a tool you pick.

* In step 4 the UI test is written against the AC before the UI code, like any
  other test. Its file or function name carries the FR-ID or AC-ID, and it lives
  under `source/` — `check-slice.py` reads test names only there and in
  `deploy/`, and a UI test belongs to the application, not to the release
  tooling.
* Visual baselines (reference screenshots) are not yours to accept.
  Regenerating them makes every visual test pass, exactly as `--fix` makes the
  integrity check pass. When a baseline must change, show me the old and the new
  image and wait for my yes; the new baseline travels in the same commit as the
  change that caused it. The command that regenerates baselines is the one
  `ARCHITECTURE.md` names; use no other. In Claude Code its common spellings
  stop at a permission prompt (`.claude/hooks/bash-guard.py`) — the well-known
  flags only, not a project script that wraps them. That prompt is where I
  confirm, not a substitute for showing me the images first.
* A missing baseline is a failure, not a new baseline. Many runners write one
  silently on the first run; the local verification command runs in the mode
  that refuses to (`ARCHITECTURE.md` says how). If it does not, say so — a
  baseline written by a run nobody looked at is one you accepted.
* A failing or flaky UI test is not skipped, retried until green, or deleted.
  Say which one and why.
* UI tests, their tooling (browsers, drivers) and their baselines never reach
  test or prod. `deploy/` ships only what the application needs at runtime.

### Settings that someone else will change

A configuration file, or a settings panel in the UI, that an administrator or a
user is expected to change carries its own explanation. Whoever changes it will
not have read the FRS.

For every setting, next to it — a comment in the file, a hint or help text in
the panel:

* what it does;
* allowed values, range, units;
* the default;
* what a change takes effect on — immediately, after a restart, after a redeploy;
* for a secret: where to obtain it. Never a real value — see *Secrets*.

The explanation says what the FRS and `ARCHITECTURE.md` say. If you do not know
what a setting means, what it accepts, or what its default is, that is a
question — not a plausible comment. A comment you made up looks like agreement.

A comment in a file is documentation. A hint in a UI panel is something the
user sees, so it is UI like any other: it comes from an `FR-*` or its AC, and a
UI test checks it. If the FRS has the panel but says nothing about its hints,
that is a question — do not add hints no requirement asked for, and do not
silently leave them out either.

Environment variables have no file of their own: their explanation lives in
`.env.example`, next to each key. If the chosen file format cannot hold
comments, do not invent workarounds such as `"_comment"` keys that the
application then has to ignore. Say so and ask.

This covers what administrators and users configure. Development tooling —
linter, test-runner, editor configs — is not in scope.

### Asking questions

An ID is an index, not a question. A bare `FR-014` in front of me means I open `FRS.md` before I can even tell what you are asking — and that lookup costs more than the question saved by leaving the words out.

So every ID you put in a message to me — a clarifying question, an options list, a diff summary — carries a short gloss in parentheses, taken from the document the ID lives in: the FRS for a requirement or an AC, `BACKLOG.md` for a slice or a task, the ADR itself for a decision:

```
FR-014 (фільтр замовлень за статусом): AC каже «статус зі списку», а
статусів у DR-003 (довідник статусів) шість. Фільтр по одному чи по кількох?
```

When the question does not actually depend on which ID it belongs to, better still: ask it in plain words and leave the ID at the end as a reference.

The gloss is three or four words for orientation, not a paraphrase standing in for the requirement — *Reading the docs* still governs the text you quote. And this applies to what you write **to me**, not to `BACKLOG.md` or the Progress Log, where a bare ID is the point.

### Branching

Finished work goes straight to `main`. There is no branch per slice and no
pull request — this is a solo project, and a branch that only ever merges into
itself is ceremony. `main` must be working after every commit; that is what
makes step 5 non-negotiable.

A branch exists for exactly one case: work that could not be finished in the
session. A slice's branch is named after the FR it belongs to —
`wip/fr-014-order-filter`; a task's after the task, even when the task
implements a requirement — `wip/task-007-backup` (one NFR can belong to two
tasks, and the branch must say whose work it holds). It is
either finished by the next session that takes the slice or deleted on my OK. For a `BLOCKED` slice that is the session after it is unblocked (see
*If the slice could not be finished*); until then the branch waits. Nothing
else lives on a branch.

Finishing it still ends in one commit on `main`: from `main`,
`git merge --squash wip/fr-014-order-filter` brings the unfinished work into
the working tree, the slice is finished there, and it is committed like any
other. The branch is deleted after that, on my OK.

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

**Machine-checked** — `python3 scripts/check-slice.py <SLICE-ID>` (on Windows in
Git Bash there is often no `python3` — use `python`; see the *Windows* section of
`README.md`), and you paste its real output:

* the slice exists in `BACKLOG.md`, its `**Статус:**` field is `DONE` or `BLOCKED`, the Progress Log has a dated row for it with that same status
* every requirement the slice claims — the IDs in its `**Вимоги:**` field, and nowhere else in its block — exists in the FRS
* `DONE`: every claimed requirement is traceable into `source/`, or into `deploy/` for what the release tooling implements — the test name carries the FR-ID or an AC-ID of it
* `DONE` task only: a requirement that no test can check (a hosting setting, a manual procedure) may instead stand in its `**Перевірка вручну:**` field with the entry that allowed it — `**Перевірка вручну:** NFR-004 — OQ-007`. That entry is `ANSWERED`, its `**Блокує:**` names the task, and it was already committed before this diff — it is the question the task was blocked on, not one written for the occasion. A slice's requirements are always tested
* `BLOCKED`: `OPEN-QUESTIONS.md` has an entry whose `**Блокує:**` field names the slice and that is still open (`**Статус:** OPEN` or `DEFERRED`) — the reason it stopped. Its tests are not checked: its code is on a `wip/` branch or nowhere
* no new `TODO`/`FIXME` comment in the diff without `OPEN-QUESTIONS.md` being touched in the same diff — the marker right after a comment opener (`#`, `//`, `/*`, `<!--`, `--`, `;`, or a `*` / `%` that starts the line); the bare word is a status in a task tracker, not a loose end

An `AC-*` counts as belonging to a requirement only where the two IDs sit on the
same **table row or heading** in the FRS, and the requirement is the one that
row or heading is about: the first cell of the row that holds a requirement ID,
or the IDs of a heading before the dash that starts its name —
`#### AC-001 (FR-002) — назва`. Another requirement mentioned further along — in
a description, in a *Related* column — ties nothing, and neither does a sentence
naming several requirements and a span of criteria: either would let one test
stand in for every requirement it mentions.

**Owner-checked** — you state plainly whether each holds, and I decide:

* the local verification command ran and was green (paste the output, not a verdict about it)
* I have seen the diff
* nothing was implemented that no requirement asked for

That second list is short deliberately. Every unfalsifiable line added to it makes the falsifiable ones cheaper to fake.

### If the slice could not be finished

Do not leave the session half-done, and never leave `main` half-working:

1. Say plainly what did not work and where you stopped.
2. Unfinished code does not reach `main`. Commit it to `wip/<fr-id>-<slice>`
   (a task: `wip/<task-id>-<name>`) — `git switch -c` takes
   the working tree along; stage only the code, commit as
   `feat: FR-014 order filter, unfinished` (a task: `chore: TASK-007 backup,
   unfinished`) — then `git switch main`: the rest happens there, and the next
   session starts there. Or leave the code uncommitted and say so.
3. If only the session ran out and nothing blocks the slice, set its status back
   to `TODO` and stop here: the `wip/` branch is the record, and the next
   `/slice-start` finds it. Except a slice unblocked in this session: `HEAD`
   still has it `BLOCKED`, so `TODO`, its row gone from *Blocked* and the
   answer in `OPEN-QUESTIONS.md` are changes nobody would commit. Add a
   Progress Log row with `TODO` and, after my OK, commit those docs alone, on
   `main`: `docs: FR-014 SLICE-005 unblocked, OQ-007 answered`. Left
   uncommitted, they ride into the next commit made, whichever it is.
4. If something blocks it, then on `main`: the slice's `**Статус:**` set to
   `BLOCKED` with the reason, an entry in `OPEN-QUESTIONS.md` whose
   `**Блокує:**` names the slice, with `**Статус:** OPEN`, and a Progress Log
   row with `BLOCKED`. If the reason is a question already in the file, do not
   open a second entry for it — two entries on one question are answered once,
   and the other keeps the slice blocked. Show me the new `**Блокує:**` line for
   the existing entry (its IDs plus the slice) and wait for my yes: editing an
   existing entry is mine. My no means that question does not block the slice —
   then it is not `BLOCKED` (step 3, or finish it). A new entry is for a new
   question only. Run
   `scripts/check-slice.py <SLICE-ID>` and show its output.
5. After my OK, commit those docs alone, on `main`:
   `docs: FR-014 SLICE-005 blocked, OQ-007`.

A `BLOCKED` slice is unblocked by the answer, not by time. Writing the answer
into its `OPEN-QUESTIONS.md` entry edits an existing entry, so it is mine or
needs my yes. After that the slice is taken again — by `/slice-start` once
the entries whose `**Блокує:**` names it, at least one, are all `ANSWERED`, or
when I say the block is lifted — and goes straight to `IN PROGRESS`; its `wip/`
branch is resumed as in *Branching*. It finishes like any other slice: the
answer, the status and the code travel in its one commit — unless the session
runs out first (step 3).

A `BLOCKED` slice that no entry names has lost its reason; it has not been
unblocked. `/slice-start` does not take it — it says so, and I decide.

All of this holds for a `BLOCKED` task as well, except a release task: that one
is resumed only by my deploy command (*Releases and deployment*, step 8).

---

## 3. Traceability

The end-to-end key is the `FR-ID`. It survives all the way to the commit.

* Commit: `feat: FR-014 order filter by status` — the ID must be in the **first
  line**; the commit-msg hook does not look at the body
* The hook also accepts `DR-*`, `NFR-*`, `IR-*`, `TASK-*` and `SLICE-*`. Prefer
  the `FR-ID`: it is the key that survives to the commit, and `SLICE-001` alone
  says which batch of work a change belongs to but not which requirement it
  serves. Use `SLICE-*` only when a commit genuinely spans a slice rather than a
  requirement. `BR-*` is not accepted at all — a business requirement is
  implemented through an `FR-*`, never committed against directly
* The test name contains the FR-ID or AC-ID, in the test's **file name or
  function name** — not in a comment or a docstring. `FR-014`, `FR_014` and
  `FR014` all count, in any case: `test_fr_014_filter` is as valid as
  `test_FR_014_filter`, because pep8-naming rejects the capitalised form and a
  project should not have to choose between a red linter and a red DoD. Glued
  to a test prefix it counts too, when it starts a new camelCase word in upper
  case or capitalised: `TestFR014Filter` (Go, pytest classes), `testFR014`
  (XCTest)
* A `wip/` branch, if one is needed at all, carries the FR-ID — `wip/fr-014-order-filter` —
  or, for a task, the TASK-ID: `wip/task-007-backup`

If a change does not map to any FR — stop. Either the work is unnecessary, or there is a hole in the FRS.

### Work without an FR

Not all work is functionality: infrastructure, linters, CI, dependency updates, defect fixes, paying down debt. That work is not done "along the way" either.

* Each such item is a separate `TASK-*` in the *Tech Tasks* section of `docs/BACKLOG.md`, with the same lifecycle as a slice.
* Commit: `chore: TASK-007 update dependencies` / `fix: FR-014 empty filter returns 500`.
* A defect in an already-closed slice maps to the `FR-*` of the requirement it violates, and starts with a test that reproduces it.
* Creating a new `TASK-*` is a change to `BACKLOG.md`, so it needs my confirmation. Found a problem — name it and propose a task, do not fix it silently.
* `TASK-000` is the one ID that lives outside `BACKLOG.md`. It covers the work
  that exists before the backlog does: the initial template commit, and the
  commit of the documents produced by steps 1-3 — `docs: TASK-000 FRS,
  architecture and backlog`. Without it the first commit of every project has no
  legal ID, and the first thing anyone learns is how to get past the hook.

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
* **Prod** — only on an explicit command, with a plan for a failed release — a rollback, or what replaces it — stated before launch.

Irreversible actions (drop, truncate, force push, deleting files outside the working branch, changes inside `.git/`) — always ask.

### Secrets

* Do not read, print, or log the contents of `.env` or any file holding keys.
* Real secret values never end up in `docs/`, commits, or chat messages. If an example is needed, add the key to `.env.example` with an empty or fake value.
* If you find a secret in the code or in history, stop and tell me. Do not "fix" it with a commit.

`.claude/settings.json` denies reading `.env` at the tool level, but that is a second layer and it has had enforcement gaps. This rule is the primary one and it holds regardless of what the settings file allows.

### Releases and deployment

What a release is depends on the platform: a server rollout, a store
submission, an installer or a package published to a channel. The template
does not know which, so this section keeps only what holds for all of them.
Here and in the rest of the rules, *test* and *prod* mean whatever
`ARCHITECTURE.md` names for this project — a test server, TestFlight or an
internal track, a beta channel — and to *deploy* is to put a build there.

The scheme — environments or channels, how a build gets there, what happens
when a release fails — lives in `ARCHITECTURE.md`, section *Environments &
Delivery*. The runbook for a concrete release lives in `docs/DEPLOY.md`, whose
sections step 2 derived from that scheme. They do not repeat each other:
`DEPLOY.md` refers to the scheme and adds only what is specific to this
release. If a release needs the scheme itself to change, that is a change to
`ARCHITECTURE.md` first.

What holds on every platform:

* Building and delivering a release is tooling in `deploy/`, not commands
  typed by hand — scripts, a pipeline definition, a store-upload
  configuration, whatever `ARCHITECTURE.md` chose. It is work without an FR: a
  `TASK-*` in *Tech Tasks*, planned before the first release to test. Anything
  `ARCHITECTURE.md` does not decide about it is a question, not an
  implementation detail.
* Every part of that tooling runs locally, or against a sandbox the platform
  provides, before it is ever pointed at test or prod.
* The released artifact carries no tests, no test tooling and no baselines —
  proved by a check in the tooling, not by a promise. Test and prod receive
  the same artifact: what was checked in test is what ships.
* What to do when a release fails is decided before it reaches prod. Where the
  platform can roll back, that is a rollback in `deploy/`, and it has been run
  locally — a rollback that has never run is not a plan. Where it cannot — a
  store release stays on the devices that already installed it —
  `ARCHITECTURE.md` names what replaces it: halting a staged rollout, a fix
  release, a server-side switch.

A release is a `TASK-*` of its own, marked `**Тип:** release` in its block —
that field is how the cycle commands tell it from other tasks — and it is the
one task with exactly two commits: one before the deploy, one after it. The outcome of a deploy does not
exist until the deploy has run, so a single commit would have to either claim
it in advance or leave it out. The one-commit rule of the *Work cycle* does not
apply to a release task; nothing else is exempt from it. The cycle commands
(`/slice-start`, `/slice-finish`) do not run a release task — this list does.
On my deploy command:

1. The release task already exists in *Tech Tasks* of `BACKLOG.md`, with
   `**Тип:** release`. If it does not, propose it — that is a change to
   `BACKLOG.md` and needs my yes. Never choose its number yourself. An agreed
   new task is written into `BACKLOG.md` in step 4, next to `DEPLOY.md`, not
   now: step 3 needs a clean working tree, and the task has no commit of its
   own.
2. A change to `deploy/` is not part of the release. It is a `TASK-*` of its
   own, finished, run locally and committed before the release starts — never
   edited mid-deploy.
3. Run the local verification command — UI tests included — on the current
   commit, with a clean working tree, and show the real output. The artifact
   carries no tests, so it is the commit that gets verified, not the artifact.
   Red means no deploy and no runbook. A release to prod that ships the
   artifact already released to test (step 6) builds nothing, so it verifies
   nothing new: it names the test release's runbook commit and the
   verification recorded there — running the command on today's commit would
   check code that is not shipping.
4. Update `docs/DEPLOY.md` for this release: the hash of the commit verified in
   step 3 and the verification that ran on it, taken from the output you have
   just shown — never written ahead of it; for prod, also which test release
   the artifact comes from. Post-deploy checks go in as checks to run, not as
   results. Show it as a diff and wait for my yes.
5. First commit: `DEPLOY.md`, the task set to `IN PROGRESS`, a Progress Log
   row — `docs: TASK-0XX release 1.2 runbook`. It touches only `docs/`; if
   anything outside `docs/` changed since step 3, the verification no longer
   covers it — go back to step 3.
6. Only then deploy, by the rules above. A release to test builds the artifact
   from this runbook commit, not by checking out the verified one: the two
   differ only in `docs/`, and you show that — `git diff --stat <verified> HEAD
   -- . ':!docs'` prints nothing. A release to prod builds nothing: it ships
   the artifact that went to test, as `DEPLOY.md` names it. If that artifact
   cannot be identified, stop — a rebuild is a new artifact that test never
   saw. Where `ARCHITECTURE.md` has no test environment, the prod release
   builds its artifact the way a test release would. For prod, the section of
   `DEPLOY.md` on a failed release is the plan that must be stated before
   launch.
7. Run the post-deploy checks from `DEPLOY.md` and show the real output. If the
   deploy or the checks fail, stop and tell me. Whatever `DEPLOY.md` says to do
   on failure — a rollback, halting a rollout — is a deploy too: it runs on my
   command.
8. Second commit, after my OK: the task set to `DONE` — or to `BLOCKED`, with
   an entry in `OPEN-QUESTIONS.md` whose `**Блокує:**` names the task, if the
   release was rolled back, halted or abandoned — and a Progress Log row: `docs: TASK-0XX release 1.2 deployed`
   (or what happened instead: `rolled back`, `halted`) whose status column is
   the task's new status. Run `scripts/check-slice.py TASK-0XX` before this
   commit, not before the first one: until the deploy is over the task is not
   done.

A release that ended `BLOCKED` is not replaced by a new task, even when the fix
changes the version. Once its entries are `ANSWERED`, or I lift the block, my
next deploy command runs this list again for the same task: the step-5 commit
then also carries the answer, sets the task back to `IN PROGRESS` and removes
it from *Blocked*. `DEPLOY.md` gets a Change Log row for the new attempt; its
`**Реліз:**` changes only with the version. A new task would leave this one
`BLOCKED` for good — there is no status for a replaced release.

---

## 9. Session hygiene

* One slice, one session. Long sessions drift.
* Don't hold state in your head — record it in `BACKLOG.md` and `OPEN-QUESTIONS.md`.
* At the start: which slice you are taking and which FRs it closes.
* At the end: what is done, what is left, which questions opened up.

