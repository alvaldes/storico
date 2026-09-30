# Slice (a) verification report — `extraction-versioning-schema`

Date 2026-09-29 · branch `feat/extraction-versioning-schema-wu1` · head `a6e41b0` (14 commits over
`main` @ `1737708`) · **not pushed, no PR opened**.

This is the record task 5.6 asks for: what was proven, what was only declared, and what never ran.
It is written from commands executed on this machine, each with its exit code read directly — never
through a pipe to `tail`, which masks status.

## The environment, because it bounds every claim below

Conda env `storico`, Python 3.12. **There is no Docker daemon here**: no `docker` CLI, no
Desktop/Orbstack/Rancher, no colima, no podman. Everything Postgres-only therefore skips rather than
fails, and "skipped" is not evidence.

A second constraint found while writing the Postgres cases, verified rather than assumed:
`PRAGMA foreign_keys` is **OFF by default in SQLite and nothing in this repository turns it on** —
zero occurrences across `backend/tests/` and `backend/src/`, and a fresh `aiosqlite` connection
reports `0`. So **no FK action of any kind fires in the unit layer**: the unit suite proves
`NOT NULL`, `CHECK`, `UNIQUE` and partial-unique behaviour, and proves nothing about
`ON DELETE CASCADE` or `SET NULL`. Read every "cascade" line below with that in mind.

## 1. Proven by execution, on this machine

| Gate | Command | Result |
| --- | --- | --- |
| 5.1 whole suite | `python -m pytest` | `1049 passed, 33 skipped, 0 failed` |
| unit layer | `python -m pytest -m "not integration"` | `1049 passed, 27 deselected` |
| repositories | `python -m pytest tests/test_repositories -m "not integration"` | `120 passed` |
| 5.5 lint | `python -m ruff check src tests` | exit `0` |
| 5.5 format | `python -m ruff format --check src tests` | exit `0`, 253 files |

Behaviour proven here:

- **Allocation.** `create_next_version` mints inside the row's own INSERT with `RETURNING`; conflict
  discrimination recognises both driver shapes and rejects `NOT NULL` violations; the bound is
  `MAX_ALLOCATION_ATTEMPTS = 3`; exhaustion raises `VersionAllocationConflictError`.
- **Birth.** `POST /workspaces/{id}/extract/` creates a pending row with `version_number` 1 then 2 on
  one story, `provider` from workspace config, `temperature` resolved against `DEFAULT_TEMPERATURE`
  (one literal, `0.1`), and `temperature` absent from `prompt_config`.
- **Render snapshot.** `prompt_rendered` holds the frozen text at the instant `generate()` is entered
  — witnessed by an observing fake adapter that reads the row through `find_by_id` and asserts
  `raw_response == ""` and no `confidence_score` at that moment. A run dying before render keeps it NULL.
- **Terminal writes are marks.** `mark_completed`/`mark_failed` name no snapshot column, so the
  snapshot survives structurally; four spy cases pin which write each path reaches.
- **No whole-row writer remains.** The port's abstract-method set is pinned exactly, with explicit
  no-`save` and no-`delete` assertions; `extract_and_persist()` is gone with its orphaned
  service-level `_store_rag`.
- **Invalidation invariants on SQLite, with a mutation matrix.** Nine cases, and each guarding
  declaration removed in turn to confirm the case fails without it:
  `ck_task_invalidations_reason_not_blank` (both arms), `ck_task_invalidations_revoke_pair` (both
  arms), `sqlite_where` on the partial unique index (degrades it to full — exactly one case catches
  it), and the whole index. The model file is byte-identical to HEAD afterwards, confirmed by SHA-256,
  and the parent re-ran the subtlest mutation independently because the writer disclosed its failure
  lines were paraphrased.
- **Re-run isolation.** v1's task rows are column-for-column identical after v2 runs (all eleven
  `TaskModel` columns including timestamps); `find_current_version` is v2; the story-level read
  returns both sets.

## 1b. What CI subsequently proved (2026-09-30, run 36649904378 on `962359a`)

The PR's CI ran the previously-unexecutable cases and is green: `1064 passed, 18 skipped` over the
same 1082 tests this machine collects, so **15 integration cases executed and passed**. That settles,
with observation rather than DDL-reading:

- `0028` upgrades and `downgrade 0027` round-trips on a real Postgres, and re-applying head restores
  the four columns — proven on a **private database**, after the shared-database version of the case
  poisoned its own session (three CI runs to find that; see §8).
- The index-name drift I could not measure locally is **absent**: `pg_indexes` reports exactly
  `pk_task_invalidations`, `ix_task_invalidations_task_id`, `uq_task_invalidations_active_task`,
  matching what `Base.metadata` expands, and the migration chain's `_KNOWN_DRIFT` is empty.
- `uq_task_invalidations_active_task` really is a **partial** index, and no full unique index on
  `task_id` exists.
- The duplicate `(user_story_id, version_number)` pair is refused by that named constraint; `tasks`
  refuses a null `extraction_id`; the story cascade removes exactly one story's versions and tasks.
- **D-a-2 is confirmed, not inferred**: deleting a user who revoked a mark is **refused** by
  `ck_task_invalidations_revoke_pair`, and the mark survives with `revoked_at` set. `0028` as written
  therefore makes such an account undeletable. Task 4.4's condition is met and needs the owner's call.

Still unexecuted by anyone: the 18 Qdrant-backed cases (they need a live vector store), and therefore
nothing in this change claims evidence about Qdrant behaviour.

## 2. Declared and lint-clean, but never executed — CI's verdict, not mine

Thirty-three cases skip. Two files are entirely in this category:

- `tests/test_integration/test_extraction_versioning_schema.py` — 12 cases. The original six (1.18/1.19:
  duplicate pair refused by name, `tasks.extraction_id` refuses null, no current flag/trigger/matview in
  `information_schema`/`pg_trigger`/`pg_matviews`, story cascade, `downgrade 0027` round-trip, the
  provoked allocation race) plus six for 4.3 (partial-index shape, catalog index names,
  index-level revoked/active coexistence, task cascade, marking-user `SET NULL`, revoking-user deletion).
- `tests/test_integration/test_migration_chain.py` — 5.3's chain acceptance and the `_KNOWN_DRIFT`
  frozenset that decides whether the migration-created index names match the models' naming convention.

These were collected (`12 tests collected`, zero errors) and linted, and were confirmed **skipping, not
erroring**. That is the most that can honestly be said about them here. The index-name expansion from
`op.f(...)` — the one thing most likely to bite — is not verified by anything I ran.

## 3. Gates that cannot be closed on this machine

| Task | Status | Why |
| --- | --- | --- |
| 5.2 integration layer | **open** | `33 skipped, 1049 deselected` — skipping satisfies the "record, don't report green" clause but proves nothing |
| 5.3 migration chain + drift | **open** | `2 skipped, 2 deselected`; needs a daemon |

Everything else in Phase 5 is closed. Nothing in this report should be read as Postgres-verified.

## 4. Two defects found by reading, not by running — both open, both need a decision

**D-a-1 — re-dispatch duplicates task rows.** `extraction_task.py:441` is an INSERT-only persist loop
with no guard on `extraction_id`; re-dispatching `run_background_extraction` for the same id appends a
second set of rows (probed: 2-task run → 3 rows for the story, while extraction rows stay at 1).
**Latent**: every live path either mints a new version or marks failed without re-running
(`recover_stuck_extractions` → `mark_failed`, `:193`). Not fixed in slice (a): both candidate fixes
change behaviour slice (b)'s endpoints depend on. The 3.2 case therefore pins the spec's "one row, one
number" and not "one set of task rows", which the code does not guarantee.

**D-a-2 — `0028` contradicts itself.** `fk_task_invalidations_revoked_by_users ... ON DELETE SET NULL`
(:104-109) coexists with `CHECK ((revoked_by IS NULL) = (revoked_at IS NULL))` (:114-117). Postgres
evaluates CHECKs during the referential action, so deleting a revoking user nulls `revoked_by` under a
standing `revoked_at` and the deletion **refuses**. `marked_by` has the same FK action but no paired
CHECK, so only the revoke side collides. Task 4.3-6 asserts the DDL reading with both outcomes
documented, so CI adjudicates rather than me encoding a guess. Task 4.4 stays open because its fix is a
product decision — `RESTRICT` and keep the audit whole, or relax the CHECK and allow an anonymous
surviving revocation — and `0028` is unreleased, so either way is an edit to `0028`, not a new migration.
The app serves no user-deletion route today (checked: no `router.delete` for users), so the conflict is
latent, not live.

## 5. Delivery facts

| PR | Commits | Content |
| --- | --- | --- |
| PR 1 (merged WU1+WU2) | `1a90aff`, `1f2d573`, `b52079c`, `486f7d6` | schema, allocation, birth, seeds, Postgres invariants, ledger |
| PR 2 (3a) | `c47a1b2` | render-time snapshot |
| PR 3 (3b) | `3364c43`, `366c341`, `3a23655`, `94db112` | marks, dead path gone, `save()` gone, triangulates |
| PR 4 (WU4) | `20a7e02`, `7a98c19`, `a6e41b0` | invalidation invariants + mutation matrix, Postgres half |

Branch total `37 files, 3902 insertions(+), 989 deletions(-)`. PR 1's 2,657 code lines were accepted
as an explicit `size:exception` by the owner on 2026-09-29; the later tranches came in under 400 each.

## 6. Chained-PR boundaries — each head verified green on its own

A chain only earns review time if every link compiles and passes independently. Each boundary was
checked out detached, the unit layer run, and the branch restored:

| Boundary | PR | Unit result at that commit |
| --- | --- | --- |
| `b52079c` | 1 — merged WU1+WU2 (schema, allocation, birth, seeds, Postgres cases) | `1031 passed, 27 deselected` |
| `c47a1b2` | 2 — 3a render-time snapshot | `1035 passed` |
| `94db112` | 3 — 3b marks, dead path gone, `save()` gone, triangulates | `1040 passed` |
| `20a7e02` | 4 — WU4 invalidation invariants + Postgres half | `1049 passed` |
| `8c5e514` | (this report) | ledger and verification only |

## 7. Delivery convention actually practised in this repo, checked rather than assumed

The `branch-pr` skill demands an approved linked issue and exactly one `type:*` label per PR. **This
repository enforces neither and has never used either**: no `PULL_REQUEST_TEMPLATE.md`, no validation
workflow (only `ci.yml` and `deploy-backend.yml`), the label set is GitHub's default (`bug`,
`documentation`, …) with no `type:*` or `status:approved`, and the eight most recent merged PRs carry
**zero** labels and close **zero** issues. Precedent also covers multi-unit PRs directly: PR 26 landed
`WU1+WU2+WU5` as one PR, and PR 27 was opened against a feature branch and then re-targeted to `main`
as PR 28 — so chaining works here but has already cost a re-target once.

Applying the skill's issue-first rule to slice (a) would therefore mean inventing a taxonomy the repo
does not have. Recorded as the user's call, not taken here.

**Deployment is not at risk from this branch**: `deploy-backend.yml` triggers only on push to `main`
with `backend/**` paths, and `ci.yml` triggers on `pull_request`. Opening a PR from this branch runs CI
and nothing else. Merging it to `main` would deploy — and CI's Postgres run is the first execution of
§2, so it must be green before that merge.

## 8. The three CI rounds, because the failures were the discovery

- **Round 1 — 8 failed.** All in the new integration file: `null value in column "owner_id" of
  relation "workspaces"`. `UserModel.id` is `default=uuid7`, applied at INSERT, and `_seed_story`
  read `owner.id` at construction time. The mechanism was then reproduced locally on SQLite (id is
  `None` before flush, a uuid after), but the failure itself was only visible under Docker, because
  the file is Docker-gated.
- **Round 2 — still 8 failed, different seven.** The round-trip case moved the *shared* module
  database down to `0027` and could not bring it back — `0028`'s own D11 guard refuses to re-apply
  while `extractions` holds rows, and earlier cases had already seeded rows. Every later case then
  failed on `column "version_number" does not exist` or empty `pg_indexes`. One fixture-ordering bug
  presented as seven schema bugs; the case's own premise ("on an empty database") was the defect. It
  now runs against a private database it creates and drops.
- **Round 3 — 2 failed, then green.** `CREATE DATABASE cannot run inside a transaction block` (the
  helper documented AUTOCOMMIT and never set it), and a `DetachedInstanceError`: the factory uses
  `expire_on_commit=False`, but that setting does not govern **rollbacks**, and the expected-failure
  case rolls back by design. The neighbouring case that passes is the one whose delete *succeeds*.

Worth stating plainly: every one of these was invisible to the machine that wrote the tests, and each
one was reported by CI as a schema failure while being a test-harness failure. A green local unit
layer was never evidence about this file, and the PR said so before any of it ran.
