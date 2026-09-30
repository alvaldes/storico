# SDD Archive Report — extraction-versioning-schema

> **Written by hand, not by `openspec archive`.** The CLI is neither installed on this machine nor a
> dependency of this project (`npx --no-install openspec` → "could not determine executable to run"), and
> the owner asked for the merge and everything remaining. Everything below that the tool would have
> computed automatically is marked as such, and the one check that could not run is named at the end.

## Archive Status

**PASS with one caveat.** The change was delivered to `main` and deployed to production before being
archived. Canonical specs were written for both domains by transforming the delta files, and the active
change folder was moved to the dated archive at
`openspec/changes/archive/2026-09-30-extraction-versioning-schema/`. **No source code was modified by the
archive step.**

**Caveat: `openspec validate` did not run.** Structure was instead verified against the repo's own
precedent — the archived `2026-09-14-few-shot-qdrant` delta vs its applied spec — and the applied files
were diffed against their deltas modulo the header. That is a formatting guarantee, not the tool's
semantic one.

## Final State

- **Tasks:** 46/46 closed, 0 open (`grep -c "^- \[ \]"` → 0).
- **Verification:** the report is `verification.md`, and its own structure is the verdict — §1 proven by
  execution on this machine, §1b what CI subsequently proved, §2 declared-and-never-executed (closed later
  by CI, not by this machine), §3 gates that cannot close here, §4 the two defects found by reading. It
  carries **no numeric requirement-coverage verdict**, and none is invented here; the counts below are
  measured from the delta files themselves.
- **Spec coverage, counted now:** 14 requirements and 36 scenarios across the two capabilities (8/23 and
  6/13), all `ADDED`, no `MODIFIED`/`REMOVED`, neither capability previously in the store.
- **Open defects at archive time:** two, both deliberately carried into slice (b) — **D-a-1** (re-dispatch
  duplicates task rows) and **D-a-4** (the account-delete route surfaces the revoker-FK refusal as an
  unmapped HTTP 500). **D-a-2 closed** as Option A, **D-a-3 closed** by the purge.
- **Implementation:** merged and deployed. PR **#30** → merge commit **`1dcc716`** (merge commit, not
  squash: `main`'s convention is merge commits, and squashing would collapse the twelve work-unit commits
  that are this branch's reviewable unit). Deploy `deploy-backend.yml` **run 36675276096** → `success`
  (2m1s). CI on `main` at the merge → `success`; CI on the closure docs commit `85e93bd` → `success`.
- **Production state verified read-only after the deploy** (`alembic_version = 0028`,
  `task_invalidations` with `fk_task_invalidations_revoked_by_users ... ON DELETE RESTRICT`,
  `uq_extractions_story_version`, partial `uq_task_invalidations_active_task`,
  `ck_task_invalidations_revoke_pair`, `tasks.extraction_id NOT NULL`, eleven business tables at 0,
  three Qdrant collections at 0 points, `/api/v1/health` → `ok`).

## Artifacts Read

`proposal.md`, `design.md`, `tasks.md`, `verification.md`, both `specs/*/spec.md` deltas, and the schema
migration itself as shipped (`backend/src/storico/infrastructure/database/alembic/versions/0028_extraction_versioning.py`).

## Domains Synced

| Capability | Mode | Requirements | Scenarios | File |
| --- | --- | --- | --- | --- |
| `extraction-versioning` | new capability (ADDED only) | 8 | 23 | `openspec/specs/extraction-versioning/spec.md` |
| `task-invalidation` | new capability (ADDED only) | 6 | 13 | `openspec/specs/task-invalidation/spec.md` |

Neither capability existed in `openspec/specs/` before, and both deltas contain only
`## ADDED Requirements` (0 `MODIFIED`, 0 `REMOVED`), so there was no existing requirement text to merge
against — the transformation is header-only and was checked by diffing each applied file against its
delta.

## Two things that changed while the change was open, and are now in the specs

- **`revoked_by` is `ON DELETE RESTRICT`, not `SET NULL`.** Task 4.4 / defect **D-a-2**, Option A chosen by
  the owner. The equivalence CHECK `(revoked_by IS NULL) = (revoked_at IS NULL)` is re-evaluated by
  Postgres *during* the referential action, so a nulling delete failed anyway; `RESTRICT` names the
  constraint that was already holding the invariant. `marked_by` keeps `SET NULL`. The normative wording
  is in `specs/task-invalidation/spec.md`, "Actor References Survive Account Deletion"; `design.md` and
  `proposal.md` keep their original `SET NULL` text with a `> [Superseded]` note under it, because those
  are planning artifacts and rewriting them would erase why the decision moved.
- **The `0028` guard was exercised for real, and it cost production data.** Defect **D-a-3**: the migration
  refuses any row in `extractions`/`tasks`, while every deploy runs `alembic upgrade head`. The owner chose
  the purge window (eleven business tables + all three Qdrant collections, no backup), executed behind an
  interlock that compared every count with a committed inventory before deleting. The
  "Migration Refuses Legacy Data and Never Backfills" requirement is therefore **verified in production**,
  not only in CI — and the runbook records the cost, including the two `api_key` values whose only copies
  were those rows.

## Active Same-Domain Change Warnings

Slices (b) `extraction-versioning-api` and (c) `extraction-versioning-prompt` are still active in
`openspec/changes/` and reference (a) by task ID (2.3, 3.4, 3.7). **Task IDs are not renumbered by this
archive**, and (a)'s artifacts stay readable at their archived path. Slice (b) inherits three named
requirements: **D-a-1**, **D-a-4**, and retiring `POST /api/v1/tasks/`, which slice (a) currently pins as
a 500 refusal.

## Unchecked Implementation Tasks

None. 46/46.

## Structured Status and actionContext Findings

**Not available.** These are produced by `openspec` itself; with the CLI absent they are not reproduced
here by hand, because a hand-written imitation of a machine-generated status is exactly the kind of
evidence that should not exist in an archive report.

## Delivery Strategy Resolution

One change, one PR, delivered as twelve work-unit commits reviewed as units. No `size:exception` label was
needed: the PR body carried measured sizes. Receipt-driven development is **off** in this clone
(`gentle-ai review mode status` → `clone-local: off`), so no native review ran; delivery followed ordinary
repository policy with the owner's explicit authorization for the merge.

## Archived Path

`openspec/changes/archive/2026-09-30-extraction-versioning-schema/`

## Memory Observation IDs

`storico-090-slice-a-delivered` · `storico-090-da3-production-measured` ·
`storico-090-d11-backfill-cost-measured` · `storico-090-da4-account-delete-500` ·
`storico-090-da2-ci-confirmed` · `storico-verify-before-accusing-data` ·
`storico-prod-purge-interlock` · `storico-llm-config-ollama-fallback`
