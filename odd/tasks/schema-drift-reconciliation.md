# ODD Feature: schema-drift-reconciliation

> **Status**: **landed.** `git merge --ff-only` `a1d549b` → `ada0847` on `main`, pushed, branch deleted —
> recorded in "Landing, and the gate's first red" below, which is the evidence.
> **Created**: 2026-09-21
> **Workflow**: Organic Driven Development (ODD)

## Problem

The previous feature left a **ratchet**: an integration test runs the whole Alembic chain against a real
Postgres and asserts that the autogenerate diff between the migrated schema and the SQLAlchemy models
equals **exactly** a recorded set of differences. It fails on a new difference *and* on a recorded one
that has been resolved, so the recorded set is a debt list that cannot rot.

That list has **six** entries. This feature pays them off, so the ratchet's literal becomes empty and
"the models and the migrations agree" stops being an aspiration and starts being an assertion.

The set lives in `backend/tests/test_integration/test_migration_chain.py` as `_KNOWN_DRIFT`, and the
original reasoning is in `odd/tasks/schema-drift-gate.md` under "WU3 — the chain measured".

## The six, and what the evidence says about each

An exploration pass read the chain, the models, and every runtime read/write of the affected columns and
indexes. Its conclusions, condensed — the load-bearing part is that **three of the six were not really
dilemmas**:

| # | Difference | What the evidence says | Direction |
|---|---|---|---|
| 1 | `extractions.status`: DB `VARCHAR(20)` vs model `ENUM('pending','completed','failed', name='extraction_status_new')` | `f13a587` changed the model to the enum and said `0016` brought the enums — but `0016` **never touches `extractions.status`**. The same omission recurred for `user_story_status` and was fixed loudly in `0017`. Then `0018` created the *type* and never wrote the conversion. One-directional: **the revision is missing**. | **The model is right.** |
| 2 | `user_preferences.preferences`: DB `JSONB` vs model `JSON` | Nothing anywhere queries *inside* the document (no `->`, `->>`, `@>`, `.astext`, no index on it), so there is no functional owner. `0005` created it as JSONB deliberately. The models were flipped to `JSON` in `eb71c3bf…` with no explanation — and `postgresql.JSONB` cannot compile on SQLite, which the whole unit suite uses. | **The migrations are right.** |
| 3 | `workspace_prompts.few_shot_examples`: DB `JSONB` vs model `JSON` | Same as #2, and `0009` converted the column to JSONB *explicitly*, with a docstring naming richer Postgres indexing as the reason. | **The migrations are right.** |
| 4 | `remove_index idx_tasks_status` | `0016` created it "for query performance"; **no query in the repository filters `tasks.status` in SQL** (the Kanban grouping is client-side), and no name is referenced anywhere. | Declare it, or drop it. |
| 5 | `remove_index idx_user_stories_status` | Exact mirror of #4 on `user_stories.status`. | Same as #4. |
| 6 | `remove_index idx_tasks_user_story_id` | `0016` created `idx_tasks_user_story_id` while `0001` had already created `ix_tasks_user_story_id`: same table, same column, same btree, non-unique both. **Two physical copies of one index.** The model declares the `0001` one. | **Drop the undeclared copy.** |

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | `#1` — which side | **A new revision converts the column to the enum.** Operator-selected. The evidence says the model is right and the conversion was simply never written; taking the cheap direction (model → `String(20)`) would leave the orphan `extraction_status_new` type in every database forever, and **Alembic never enumerates enum types**, so nothing would ever report it. |
| D2 | `#2`/`#3` — which side | **The models declare JSONB, through a dialect variant:** `sa.JSON().with_variant(postgresql.JSONB(), "postgresql")`. Follows `0009`'s recorded intent with no migration. The variant is not optional: writing `postgresql.JSONB()` directly raises a `CompileError` at fixture setup, and the entire unit suite builds its schema with `create_all` on SQLite. |
| D3 | `#4`/`#5`/`#6` — indexes | **Declare the two `idx_*` in the models and drop the duplicate with a revision.** The database is already right for #4/#5, so those are model-only; #6 needs a `DROP INDEX` for the redundant copy, which the model does not declare. |
| D4 | The server-default blind spot | **Record it, do not touch it.** See below. |

### Why `#1` is the only one that carries risk

It is the only difference where the **database** must change over live rows. Three concrete hazards, all
recorded rather than discovered during an incident:

1. **The cast runs over rows nobody can see from the repository.** Production has extractions; if any row
   holds a value outside the three labels, the `USING` cast aborts and — because the migration runs in one
   transaction — takes the whole chain with it.
2. **The `server_default` is load-bearing.** `0002` created the column with
   `server_default='pending'`, and Postgres will not auto-cast that existing default expression to a new
   enum type. The revision has to drop the default, convert, and set it again as the enum.
3. **The deploy still runs no migrations at all.** A revision that aborts is a revision that gets applied
   by hand, late. That is the 2026-09-20 incident's mechanism, and it is still open.

**Mitigation the revision must carry, not the operator:** before casting, the revision queries the
distinct values in the column and **raises a clear error naming any value outside the enum's labels**,
instead of letting Postgres emit a cast error. Same spirit as the rest of this repository: fail loudly
with a nameable reason. If production does hold a stray value, the operator learns which one in one line
of output rather than reading a truncated cast failure in an SSH session.

### The structural blind spot, recorded and deliberately not touched (D4)

`compare_server_default` is **`False`** by default in Alembic and `env.py` never enables it, so **no
`modify_default` difference can ever appear in this ratchet**, however many exist. There are **ten
columns** whose `server_default` lives in the database and not in the models:

`projects.description`, `tasks.description`, `tasks.priority`, `extractions.status`,
`user_preferences.preferences`, `user_stories.status`, `tasks.status`, `users.is_first_login`,
`extractions.user_story_status`, `user_stories.updated_at`.

That is a coherent class, not an accident: this project's convention is Python-side defaults in the ORM
plus DB-side defaults for `NOT NULL` backfills, and the harness can see only the first half. Note the
irony worth keeping: `extractions.status`'s DB default is **precisely the expression that makes #1 hard**,
and the ratchet that guards #1 is blind to exactly that detail.

Not enabled here, because it is a **policy change and not a line**: turning it on reports all ten at once
and reads as a regression introduced by that change, and Alembic's own documentation says the comparison
"has varied accuracy depending on backend", so it can produce diffs that oscillate between runs. When it
is enabled, the model-side defaults must land **in the same change as the flag**.

## Work units

### WU-A — the model-only reconciliation (`#2`, `#3`, `#4`, `#5`)

| File | Change |
|------|--------|
| `models/user_preferences.py` | `preferences` → `sa.JSON().with_variant(postgresql.JSONB(), "postgresql")` |
| `models/workspace_prompt.py` | `few_shot_examples` → the same variant |
| `models/task.py` | declare `Index("idx_tasks_status", "status")` |
| `models/user_story.py` | declare `Index("idx_user_stories_status", "status")` |
| `tests/test_integration/test_migration_chain.py` | remove those **four** lines from `_KNOWN_DRIFT` |

Zero database change, zero Alembic revision. The SQLite unit suite is the proof that the variant is
correct, and it is the only local proof available: if the variant is wrong the suite dies at fixture
setup with a `CompileError`, which is a loud failure rather than a silent one.

### WU-B — the two revisions (`#1`, `#6`)

| File | Change |
|------|--------|
| a new revision | convert `extractions.status` to `extraction_status_new`: pre-flight value check with a nameable error, `DROP DEFAULT`, `ALTER COLUMN … TYPE … USING`, `SET DEFAULT` as the enum, working `downgrade` |
| a new revision | `drop_index("idx_tasks_user_story_id", table_name="tasks")`, with a `downgrade` that recreates it |
| `tests/test_integration/test_migration_chain.py` | remove the last **two** lines from `_KNOWN_DRIFT` |

Both revision files must be readable by a person who is about to run them against production, because
that is how they will be applied.

## The guardrail that makes this order-sensitive

The ratchet fails on a recorded entry the run **no longer reports**. So each fix must remove its own line
in the **same commit** that fixes it; a fix landed alone turns CI red with a "stale entry" message rather
than a false green. That is the mechanism working, and it is why WU-A and WU-B are separate commits even
though they are one candidate.

## Non-goals

- **Enabling `compare_server_default`** (D4). Recorded above; its own decision, with its own ten columns.
- **Retiring `workspace_prompts.few_shot_examples`.** `0020`'s docstring says the column is retained
  read-only so the one-time seed job can migrate legacy examples, and that it *"is dropped in a
  follow-up"*. That follow-up is real, but it is not a type alignment: it needs the model, the
  repository, the domain entity and `cli/seed_few_shot.py` retired together, and it needs to know whether
  the seed has already run against production — which is not determinable from the repository.
- **Renaming the three `idx_*` indexes to the documented `ix_*` convention.** Cleaner, but it makes the
  ratchet's literal change by **two** lines per index (a `remove_index` plus an `add_index`) and requires
  the revision and the literal to land atomically or CI is red in between. Its own change.
- **Dropping the two unused status indexes.** Nothing queries them today, so dropping is defensible; D3
  chose to declare them instead, because an index someone created deliberately is a cheaper thing to
  document than to remove and want back.
- **The orphan enum type.** If `#1` had gone the other way, `extraction_status_new` would have stayed in
  every database, invisible to autogenerate forever. D1 avoids that; this is recorded as the reason.
- **The deploy's missing migration step.** Still the largest open item, and the reason #1's hazard list
  has a third entry.

## Tasks

- [ ] WU-A — the four model edits, the SQLite suite green, and the four `_KNOWN_DRIFT` lines removed in
      the same commit.
- [ ] WU-B — the two revisions with working `downgrade`s, the pre-flight value check on #1, and the last
      two `_KNOWN_DRIFT` lines removed.
- [ ] Confirm the literal is **empty** afterwards, and say in the record why the ratchet machinery is kept
      rather than reverted to a bare equality assertion.
- [ ] Gates: `ruff check src tests`, `ruff format --check src tests`, `pytest -q` locally; the chain and
      the ratchet can only be proven in CI, because there is no Docker daemon on this machine.
- [ ] Commit, native review, land.

## Evidence

### WU-A — the model-only half (commit `ae7ae5d`)

Four files: `user_preferences.py` and `workspace_prompt.py` now declare the column through
`JSON().with_variant(JSONB(), "postgresql")`, `task.py` and `user_story.py` declare their `idx_*` index,
and four lines left `_KNOWN_DRIFT` in the same commit.

The variant is proven in **both** directions, which is the only local proof available: the unit suite
builds its schema with `create_all` on SQLite, so a bare `postgresql.JSONB()` dies at fixture setup with
a `CompileError` rather than failing quietly. Measured resolution is `JSONB` on `postgresql` and `JSON` on
`sqlite` for both columns. The suite ends at **743 passed, 3 skipped, 1 warning** — the warning is the
pre-existing `RuntimeWarning` — and the pre-change baseline was 730 + 3, so the only delta is WU-C's 13.

### WU-B — the two revisions (commit `1fca54b`)

`0025` converts `extractions.status` to `extraction_status_new`; `0026` drops `idx_tasks_user_story_id`,
the physical copy of the index `0001` already created. The last two lines left `_KNOWN_DRIFT` with them.

`0025` documents four things a person about to run it needs: the pre-flight check and why the mitigation
lives in the revision rather than in an operator's memory; the default moving in three steps and why
(`0002`'s `server_default='pending'` cannot survive the type change), including that the window with no
default is unobservable because the revision commits or aborts as one; that the **deploy order is
order-agnostic**, with the reason; and that it does not create the enum type (`0018` owns it) nor drop it
in `downgrade` (a revision that dropped another's object would break that other revision's own
`downgrade`).

The order-agnostic claim is argued rather than asserted, and the argument found something the plan had
not: the only behavioural difference between the two sides is **ordering** — an enum sorts in declaration
order, a `VARCHAR` in collation order — and nothing in the repository orders or range-compares the column
(the only predicate is an equality against `ExtractionStatus.PENDING`), so no observable behaviour depends
on which side is live.

### WU-C — proving the mitigation (commit `cf0b624`), added because nothing exercised it

The plan put the mitigation in the revision: check the stored values first and name a stray one instead of
letting Postgres emit a cast error. Then the writing agent found that **the failure branch was executed by
nothing** — CI's container database is empty, so in CI *and* locally only the happy path runs, and the
raise was proven by reading alone. That is precisely the class of defect this workstream exists to
eliminate, so it was fixed inside this feature rather than recorded as debt.

The decision moved into a pure function, `_values_outside_labels(labels, stored)`, handed the values
instead of reading them; the connection read stays in `_stray_statuses()`. **Thirteen tests now cover it
with no database**, including the revision's own use of it against a real SQLite engine, that the argument
decides rather than a hardcoded list, that a label valid for a *different* enum is still stray, and that
the revision follows `0024`.

**Load-bearing verified by mutation, not by reading.** Returning `[]` (never report a stray) fails **six**
of the thirteen, including the one that reads a real engine. Treating no value as an allowed label fails
the all-valid case with `assert ['failed', 'pending'] == []`. So the branch the plan cares most about is
now proven by tests that run on this machine, which is more than the plan asked for.

### What an empty literal does **not** mean

It makes **autogenerate-visible** drift zero. It does not make the models and the migrations agree. Ten
`server_default`s are invisible to this ratchet, and **this change adds one to that class**:
`extractions.status` now carries `server_default='pending'` in the database while the model declares only
a Python-side `default`. The ratchet guarding the hardest of the six differences is blind to precisely the
detail that made that difference hard.

So the machinery stays, and the literal being empty is recorded as the **target state** rather than a
placeholder. The honest counterpoint is recorded with it: with the set empty, `stale_entries` is
unreachable — untested code — and a reviewer arguing YAGNI would not be wrong. It stays because the
two-directional comparison is what forced each fix to land atomically with its own line, and because
deleting it would leave no proven place to record a difference that is next understood and deliberately
accepted.

### A correction to this plan's own brief, and an input for Fase 1

The brief told the writer that a revision must be readable "by a person who is about to run them against
production". Measured, that is not achievable through offline rendering, and the reason is not this
feature's: `alembic upgrade --sql` is already dead, because a revision that reads rows cannot be rendered
without a connection.

**The parent got the localisation wrong and the record keeps the correction.** It first stated that the
chain fails at `0022`. Measured independently afterwards:

| Range | Result | Named in the traceback |
|---|---|---|
| `base:0020` | exit 0, 362 lines | — |
| `base:0021` | exit 1, 375 lines | `versions/0021_add_custom_providers.py` |
| `0020:0021` | exit 1, 18 lines | `0021` |
| `0021:0022` | exit 1, 5 lines | `0022` |

**Those counts took three attempts, and the correction belongs in the record.** The first measurement
captured the output through `$(...)`, which strips a trailing newline; a second, made by the other session
in this worktree through a different capture path, landed one below a third that agreed with neither pair.
The figures above come from writing the output **to a file** and counting it with **three independent
instruments** (`wc -l`, `grep -c ''`, Python's `readlines`), plus the last byte, which is `0a` — so three
counters agree and the file really does end in a newline. The counts are decorative and **the localisation
is the claim that matters**; but a number nobody can reproduce is a claim nobody can check, which is the
subject of this whole record.

**The same discipline the counts needed is the one the bug needed.** `base:0022` printed the **same number
of lines** as `base:0021`, so the render had never advanced past it — and the difference between "the
range fails" and "the range fails *at* its last revision" was invisible until a narrower range was run.

The first blocker is **`0021`**, and `0022` fails on its own as well. `0021:59` calls
`_backfill_existing_custom_providers()`, and at `:81` that function opens `Session(op.get_bind())` — an ORM
Session whose bind, in offline mode, is a `MockConnection` with no `close()`. The failure mode that
produced the wrong localisation is worth keeping: the claim came from `base:head`, and **a range that
contains the culprit is indistinguishable from the culprit**. The tell was available and missed, and the
paragraph above records it.

Two consequences for **Fase 1**: a hand-applied revision means an online `alembic upgrade`, never a SQL
file; and `0024`'s guard is the model to copy, because it fails loudly, names the missing variable and says
re-running is safe, where `0021` and `0022` fail with an opaque `AttributeError`.

### Native review

Native review `review-d891068373279e1e`, target
`sha256:6a1f7d173b863c0cb5312bf31c66247cd3e1a8c6f9e5d8bdbe42c8ff786edf75`: **approved**, `risk_tier: medium`,
one lens (`review-reliability`), 9 files, `original_changed_lines: 885`, `correction_budget: 200`,
`risk_reasons: [{"code": "executable_change", "path":
"backend/src/storico/infrastructure/database/alembic/versions/0025_convert_extractions_status_to_enum.py"}]`.

**It took three attempts, and the failure was flaky rather than deterministic.** The first two died at the
transport stage — `pi-host-relay-transport-failure`, stage `pi`, ~250 s each, reason *"Reviewer completion
failed for review-reliability: Expected property name or '}' in JSON at position 1"* — with
`mutation_performed: false`, so nothing was admitted and no authority was created. The prescribed
continuation is a **fresh STATUS and its reoffered binding**, never a replay of the previous one, and the
third attempt closed approved. Recorded because two identical failures invited the conclusion
"deterministic", and the third refuted it — an inference from n=2, which is the mistake this record is
about.

**Four advisories, none opening a correction:**

| Finding | Lens | Location | Severity |
|---|---|---|---|
| `R3-docstring-offline-render-localisation` | reliability | `0025:31-36` | WARNING |
| `R3-guard-raise-path-integration-unexercised` | reliability | `test_migration_chain.py:415-440` | SUGGESTION |
| `R3-order-agnostic-claim-unmeasured` | reliability | `0025:18-24` | SUGGESTION |
| `R3-tripwire-vacuous-today` | reliability | `test_migration_chain.py:415-440` | SUGGESTION |

**The `WARNING` is a false claim that this record had already corrected, and the correction never reached
the code.** `0025`'s docstring says offline rendering *"stops at 0022"* — the localisation this record's own
brief stated and that the record later corrected to `0021`. The reviewer flagged precisely that location. So
the same wrong claim is now **right in the record and wrong in the revision an operator would read before
running it against production**.

That is the *"fix by class, not by instance"* failure the previous batch recorded: the correction was
applied to the artifact in front of the parent and not to every place the claim had already reached. Worth
keeping for exactly that reason — the record was the instance, the revision docstring was the class, and the
class was missed.

It is a **follow-up and not fixed here**, because the review's own closure says advisories are separate
later work and editing the reviewed tree would mean delivering something other than what was reviewed. The
fix is small and specific: name `0021` as the first blocker, and name the mechanism — an ORM
`Session(op.get_bind())`, not `op.get_bind()` directly.

The other three are the limitations this record already states rather than new defects: the guard's raise
path is exercised by unit tests but not through the integration path; the order-agnostic claim is argued
from code-reading and cannot be measured without two production-shaped databases; and the tripwire is
vacuous today, which the writing agent said itself when it added it.

### Landing, and the gate's first red

Landed with `git merge --ff-only` `a1d549b` → `ada0847`, pushed, branch deleted with `-d` (which fails
unless merged, so the deletion is the proof). `HEAD == refs/remotes/origin/main == ada0847`, ahead/behind
`0/0`, tree clean, and the tag `v0.4.0` unmoved at `af91291`.

**The deploy went red on purpose, and that is this feature working in production.** The code head became
`0026` while production's schema was `0024`, and the gate said so in one line:

```
=== READINESS GATE FAILED: 225s ===
storico-api container running: true
HTTP status: 503
Schema status is drift: the code expects revision 0026, the database holds 0024
```

That is the 2026-09-20 condition — code and schema out of step — **detected in a deploy log before any
extraction failed, instead of after 56 of them did**. Liveness was preserved throughout: `/health` answered
200 with `schema: drift` and `version: 0.4.0`, so the new container was up and serving while readiness
refused. The failure is the designed handoff, not a false alarm, and the workflow reported it instead of
reporting success over a broken release.

**The migration was then applied by hand, online**, as the runbook in `schema-drift-gate.md` prescribes —
`alembic upgrade head` in an ephemeral container mounting the VM's checkout read-only for its config:

```
Running upgrade 0024 -> 0025, convert extractions.status to the extraction_status_new enum
Running upgrade 0025 -> 0026, drop the duplicate index on tasks.user_story_id
0026 (head)
```

**`0025`'s pre-flight did not raise, and that is a measurement rather than a passed test:** production held
no value outside the enum's three labels, so the `USING` cast was safe. That is the mitigation's happy path
exercised against real rows — and it is precisely the branch no test can exercise, because CI's container
database is empty. Read the other way: the check's **refusal** path is still unexercised against production,
and the only thing that exercises it is production one day holding a bad value.

> **Addendum, 2026-09-21 — the paragraph above is no longer true.** The refusal path is now exercised by a
> test. `2252640` (`test(db): exercise 0025's refusal path against a real database`) seeds
> `pending, processing, processing, failed` at the `0024` schema and asserts that `upgrade()` raises **before**
> any DDL, that the message names the offending value exactly once, and that the rows are still there
> afterwards. It holds on SQLite precisely because the guard runs before the Postgres-only cast — which is
> why an empty CI container could never reach it and a seeded one can. The test passed 14/14 on its file, and
> the candidate went through native review before landing: lineage `review-8635d52fa755e325`, tier `medium`,
> one lens (`review-reliability`), **approved and burned**, with no advisories. Getting there cost two
> harness defects, both recorded in `odd/tasks/advisory-closures.md`.

Readiness then answered 200 with `schema: ok`, and the deploy was re-run on the same commit to confirm the
pipeline end to end: **green**. So the whole designed sequence — land, fail loudly, migrate, confirm — ran
once, for real, on the change that most needed it.

One honest note about that re-run: it replaced the failure with a success **on the same run id**, so the red
lives in that run's first attempt and in this record rather than in the headline list. Recording it here
means nobody later has to wonder whether it ever failed.
