# ODD Feature: schema-drift-reconciliation

> **Status**: not started. Branch `feat/schema-drift-reconciliation` off `main` @ `a1d549b`.
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

_(the per-work-unit records land here; every number cited comes from a measurement, and the two places
where this feature could not measure something say so.)_
