# SDD Archive Report — extraction-versioning-api

> **Written by hand, not by `openspec archive`.** The CLI is neither installed on this machine nor a
> dependency of this project. The owner asked for the merge and everything remaining, executed as a
> manual transformation. Everything below that the tool would have computed automatically is marked as
> such, and the one check that could not run is named at the end.

## Archive Status

**PASS with one caveat.** The change was delivered to `main` and deployed to production before being
archived. Canonical specs were written for all seven domains by transforming the delta files — nine
requirements replaced in place (`MODIFIED`), sixteen appended (`ADDED`), zero `REMOVED` — and the
active change folder was moved to the dated archive at
`openspec/changes/archive/2026-10-07-extraction-versioning-api/`. **No source code was modified by the
archive step.**

**Caveat: `openspec validate` did not run.** The merge was instead guarded by mechanical checks run
before and after: per-capability requirement and scenario counts, a duplicate-requirement-title check
over every canonical file (empty result), an assertion that every delta requirement title is present
in its canonical file exactly once, and an exact-match assertion on every `MODIFIED` title before its
canonical block was replaced. Those are formatting guarantees, not the tool's semantic one.

## Final State

- **Tasks:** every checkbox task in `tasks.md` is closed — measured 79 checkbox lines, all `[x]`,
  0 unchecked (`grep -cE '^\s*- \[ \]'` → 0). A naive string count reads 80 `[x]` and 1 `[ ]`, but the
  single `[ ]` is a prose quote inside the task 6.3 amendment note, not an open box: it quotes the
  interim revert of 6.3, and the deferral it describes — the checkbox-checked + reason-field-focus
  half of the "Marcar como inválida" seam, deferred out of W6-A's forbidden surfaces — was **closed
  the same day by W6-B1**, which delivered the seam through `TaskEditorProps`
  (`markDefaultChecked` / `reasonAutofocus` / `activeMark`) and re-checked 6.3.
- **Verification:** the report is `verification.md`, and its own structure is the verdict — §1 what ran
  where and the exact reconciliation of the two backend numbers (1242 collected = 1206 passed + 36
  skipped locally; 1224 passed + 18 skipped in CI, the difference being exactly the Docker-gated
  eighteen), §2 what each layer actually proved, §3 the one cross-slice dependency nothing here can
  prove (D10's exclusion, owned by slice (c)), §4 the residuals named instead of absorbed, §5 what is
  not in this slice's evidence at all (the deploy, production's LLM configuration, the release bump).
  It carries no numeric requirement-coverage verdict, and none is invented here; the counts below are
  measured from the delta files themselves.
- **The 36 skips are two classes, not one:** 18 Docker-gated cases that ran in CI, and 18
  environment-flag opt-ins (16 Qdrant, 2 Ollama live) that skip everywhere — nothing in this slice has
  ever run against a real Qdrant or a real Ollama.
- **Spec coverage, counted now:** 25 requirements and 90 scenarios across seven capabilities
  (16 `ADDED` / 9 `MODIFIED` / 0 `REMOVED`); one capability (`workspace-permissions`) is new to the
  store. `extraction-versioning` and `task-invalidation` already existed from slice (a) and grew.
- **Open defects at archive time:** both defects carried in from slice (a) are closed in this slice's
  artifacts — **D-a-4** closed by task 5.14 (the owner chose the designed 409 `ACCOUNT_DELETE_BLOCKED`,
  produced by a pre-check over `list_standing_revocations_by_user`, with the route's first DELETE-verb
  tests in `backend/tests/test_api/test_account_deletion.py`; the residual account-delete race is named
  in `verification.md` §4 rather than absorbed), and **D-a-1** closed by task 5.15 as an **explicit
  non-goal** with a measurement (the only production caller of `run_background_extraction` runs once
  per freshly minted extraction, and (b) adds no re-dispatch surface). **D-a-6** — production has no
  LLM configuration and `resolve_llm_config` falls back to an Ollama that does not exist there — is
  named in `verification.md` §5 as the owner's pending action, outside this slice's evidence.
- **Implementation:** merged to `main` on 2026-10-02 as the nine-PR chain **#31 → #39** (head verified
  `75e679e`), and released in **`v0.10.0`**. The deploy window's `alembic upgrade head` applied `0029`,
  which is additive and reads no data, so it needed no data plan and the D-a-3 rule did not bite.
- **Production state verified read-only on 2026-10-07**, by which time later releases had also landed:
  `/api/v1/health` reports `version: 0.12.0` with `database` and `schema` `ok`, `/api/v1/health/ready`
  responds 200, and the retired creation endpoint answers `POST /api/v1/tasks/` → **410**
  `TASK_CREATION_ENDPOINT_REMOVED` — the contract task 1.x built and the WU1 tests pin.

## Artifacts Read

`proposal.md`, `design.md`, `tasks.md`, `apply-progress.md`, `state.yaml`, `verification.md`, and all
seven `specs/*/spec.md` deltas. The transformation was applied from the delta files, not from memory.

## Domains Synced

| Capability | Mode | Delta reqs (scenarios) | Resulting file |
| --- | --- | --- | --- |
| `export-download` | `MODIFIED` ×1 | 1 (4) | `openspec/specs/export-download/spec.md` — 5 reqs / 8 scenarios |
| `extraction-versioning` | `ADDED` ×7 | 7 (30) | `openspec/specs/extraction-versioning/spec.md` — 15 reqs / 53 scenarios |
| `extraction-workflow` | `MODIFIED` ×2 | 2 (8) | `openspec/specs/extraction-workflow/spec.md` — 3 reqs / 9 scenarios |
| `kanban-board` | `MODIFIED` ×2 | 2 (6) | `openspec/specs/kanban-board/spec.md` — 5 reqs / 8 scenarios |
| `task-editor` | `MODIFIED` ×4, `ADDED` ×2 | 6 (20) | `openspec/specs/task-editor/spec.md` — 6 reqs / 20 scenarios |
| `task-invalidation` | `ADDED` ×4 | 4 (16) | `openspec/specs/task-invalidation/spec.md` — 10 reqs / 29 scenarios |
| `workspace-permissions` | new capability (`ADDED` ×3) | 3 (6) | `openspec/specs/workspace-permissions/spec.md` — 3 reqs / 6 scenarios |

`workspace-permissions` did not exist in `openspec/specs/` before and was created from its delta.
`extraction-versioning` grew from 8/23 and `task-invalidation` from 6/13 (slice (a)'s closed counts).
Every `MODIFIED` replacement was matched on its exact `### Requirement:` title before the canonical
block was touched; no title required guessing, and no canonical text outside the replaced blocks was
altered. Delta files moved to the archive unchanged.

## Active Same-Domain Change Warnings

Slice (c) `extraction-versioning-prompt` is still active in `openspec/changes/` and is being archived
separately. **Task IDs are not renumbered by this archive**, and (b)'s artifacts stay readable at
their archived path. Slice (b) hands (c) one named cross-slice dependency: **D10's exclusion** — (b)
makes marks creatable and revocable, but nothing in it calls `set_has_invalid_tasks`; (c)'s WU3 tasks
3.6–3.8 must, and until they land every mark excludes nothing from few-shot retrieval while nothing
goes red.

## Unchecked Implementation Tasks

None open. Every checkbox task is `[x]`; the one deferral the change carried (the mark-seam half of
task 6.3) was closed by W6-B1 on 2026-10-02, as recorded in the amendment note on the task itself.

## Structured Status and actionContext Findings

**Not available.** These are produced by `openspec` itself; with the CLI absent they are not reproduced
here by hand, because a hand-written imitation of a machine-generated status is exactly the kind of
evidence that should not exist in an archive report.

## Delivery Strategy Resolution

`tasks.md`'s workload forecast called for chained PRs (400-line budget risk high), and that is what
was delivered: the nine-PR chain **#31 → #39**, split along WU1–WU6 plus verification, merged
2026-10-02 and released in `v0.10.0`. The forecast's own restatement (≈4,500–5,800 lines, to include
task 5.14) is recorded in `tasks.md`. Whether receipt-driven development mode was on at merge time is
session state, not an artifact of this change; no artifact here records it, and this report does not
invent it.

## Archived Path

`openspec/changes/archive/2026-10-07-extraction-versioning-api/` — the folder date is the archive date
(2026-10-07); the merge date (2026-10-02) is carried by this report above.
