# ODD Feature: extraction-versioning-090 (OpenSpec change authoring)

> **Status (2026-09-30, final)**: **slice (a) is SHIPPED.** 46/46 tasks, PR #30 merged to `main` as merge
> commit `1dcc716`, deploy run 36675276096 `success`, `0028` verified in production Neon (`alembic_version
> = 0028`, `task_invalidations` with `revoked_by ... ON DELETE RESTRICT`, `uq_extractions_story_version`,
> partial `uq_task_invalidations_active_task`, `tasks.extraction_id NOT NULL`) and the change archived by
> hand under `openspec/changes/archive/2026-09-30-extraction-versioning-schema/`. **D-a-2 closed** (Option
> A, `RESTRICT`), **D-a-3 closed** (purge window executed: eleven business tables and all three Qdrant
> collections emptied, no backup by the owner's choice). Not done, deliberately: `make bump` (release is
> the owner's call) and the two operations that need human hands — logging in again and re-creating the
> workspace LLM config, because `resolve_llm_config` defaults to `provider = "ollama"` and production runs
> no Ollama. **D-a-4** (the account-delete route 500s on the refusal) and **D-a-1** (re-dispatch duplicates
> task rows) are carried into slice (b), which is **not authorized**.
> → read **"Session handoff — 2026-09-30 (final)"** at the end of this file first.
> **Created**: 2026-09-28
> **Workflow**: SDD/OpenSpec (explicitly selected by the user) inside ODD
> **Session preflight**: `auto` + `openspec` + `ask-on-risk` + 400-line review budget, confirmed
> by the user in this session
> **Receipt-driven development**: off in this clone
> **Source spec**: vault note *"Storico — versionado de extracción y tareas inválidas"*
> (feature **0.9.0**, decisions **D1–D23**, no open questions)
> **Measured against**: `main` `ecea3e2` = `v0.8.0` + **42** commits

## What this document tracks

Steps 1 and 2 of the spec's "Siguiente paso":

1. Re-verify the measurements behind **D16–D23** against whatever is on `main`. The spec measured
   against `v0.8.0` + 41 commits (`475964c`) and warns those measurements "son las que sostienen
   decisiones, no decoración".
2. Write the OpenSpec change(s) in `openspec/changes/`, cut into the three dependent slices the
   spec suggests.

Step 3 — the destructive D11 data cleanup — is **not** tracked here and is **not** authorized by
this document. It is a separate data operation with its own confirmation and its own record.

## Slice plan (user decision, 2026-09-28)

Three **dependent changes**, not one: each is the unit that gets applied, verified, reviewed and
archived on its own. Permissions (D13, D15) and UI (C1, the mark-as-invalid button, the two
confirmations, the D16 notice) ride **inside slice (b)**, per the user's choice.

| Slice | Change name | Owns | Decisions |
| --- | --- | --- | --- |
| (a) | `extraction-versioning-schema` | migration `0028`, `version_number`, `tasks.extraction_id`, `task_invalidations`, current-version derivation | D1, D3, D4, D12-storage, D22, storage half of D6/D8 |
| (b) | `extraction-versioning-api` | field-policy matrix, marks endpoints, owner-or-`ADMIN` gate, 410, story-delete gate + audit, task editor + confirmations + version selector | D2, D5, D6, D12, D13, D14, D15, D16, D17, D21, C1, C2, C7, C8, C10 |
| (c) | `extraction-versioning-prompt` | snapshot content, project context, negative examples, Qdrant payload + filter signature, token usage, the 1000-story bench | D7, D8-content, D9, D10, D19, D20, D23, C4, C5, C6 |

**Deployment coupling (not a review coupling).** (a) alone is not deployable: once `tasks` gains
`extraction_id`, the board, the export and `GET /tasks` still read by `user_story_id`, so a second
run on a story shows both versions' tasks. (b) is what applies the current-version filter to
reads. Ship (a) and (b) in the same release train.

## Verification ledger — result

Full evidence, every claim with `file:line`, is in
`openspec/changes/archive/2026-09-30-extraction-versioning-schema/explore.md` (shared base for the three changes).

**No code moved** between the spec's `475964c` and `ecea3e2` — the one extra commit is docs-only
(`AGENTS.md`, `docs/architecture.md`, `docs/deployment.md`). So every verdict below is a verdict
on the spec's earlier verification pass, not on new commits.

- **Premise survives.** `Extraction` has no version or order; `Task` hangs off `user_story_id`;
  `task_invalidations` does not exist; the prompt takes only `user_story` and `examples`; the
  Qdrant payload is exactly 7 keys. The feature is still needed exactly as specified.
- **All six re-pinned line numbers still resolve.** D1–D23's numeric citations are safe.
- **Alembic head `0027` confirmed** → the change starts at `0028`. **15 ports confirmed**; the
  "13 entities" claim counts a file that is `exceptions.py` (12 entity modules).

### Four measurements that do not survive — each one is now a change requirement

| # | Spec premise | Reality at `ecea3e2` | What the change must do |
| --- | --- | --- | --- |
| Δ1 | `MAX_ROWS = 1000` means "1000 stories per project" | It is a **per-file** cap in the parser (`story_csv.py:23,143`); no per-project quota exists; a second import crosses it | D23's 1000-story bench is a **floor**, not a ceiling; say so where D9 claims a bound |
| Δ2 | "no input-size limit anywhere" | True in the extraction path, but `raw_text` is capped at **2000** chars upstream (`api/schemas/story.py:20`, `story_import.py:35`) | The unbounded dimension is item **count**; state the real bound |
| Δ3 | "≈8 fixed statements + 1 per task" | **≈16 fixed + ≈2 per task**: every repo `save()` is SELECT+COMMIT, plus `selectin` eager loads | D23's conclusion (2 more statements, `pool_pre_ping` untouched) holds; the arithmetic must not be quoted as measured |
| Δ4 | D8 "every version freezes everything needed to read it" + D22 "a failed run consumes a number" | `prompt_config` key sets differ by outcome: pending/failed `{validate, temperature}` vs completed `{…system_prompt}` (`extraction.py:236-239`, `extraction_task.py:438-442`, `:199/:506/:600`) | **New requirement, not in the spec**: the snapshot is written **after render, before the provider call**, so a failed version still carries its input. `usage` is the only key that may legitimately be absent |

Δ4 is the material one: it is a hole the measurements opened, and it is why slice (a) cannot ship
`version_number` by itself.

## Hazards named for whoever applies these changes

- **Two extraction persistence paths.** Production is `extraction_task._run_extraction` (reuses
  the row — which is what D22 needs). `extraction_service.extract_and_persist` is **dead,
  test-only** and creates a **fresh row** per call. `version_number` must be assigned at the
  row's birth in the route, or the dead path mints two numbers for one run.
- **`0027` dropped the column that `0009` converted to JSONB.** The migration precedent is real;
  the example column is gone. Quote the pattern, not the column.
- **D5's "status editable" already matches the UI**: `TaskEditor.tsx` edits five fields including
  `status` (the spec's table says four). Only title/description/priority are actual restrictions.
- **The D16 normalizer has a precedent, not a helper**: the only task-title `casefold()` is
  `api/routes/export.py:45`, used for dependency resolution.
- **The 410 mechanism has two precedents**, not one: `extraction.py:68-91` and
  `projects.py:35-59`, both `api_route(..., status_code=410)` + `ApiError(error_code=…)` →
  `{detail, error_code}`.

## Task list

- [x] 1. Re-verify D16–D23 measurements against `main` (3 bounded read-only scouts + parent
  re-reads) → ledger in `openspec/changes/archive/2026-09-30-extraction-versioning-schema/explore.md`
- [x] 2. Resolve the four drifts into change requirements (Δ1–Δ4 above)
- [x] 3. Write slice (a) `extraction-versioning-schema` — proposal, delta specs, design, tasks
  (`sdd-proposal` → `sdd-spec` → `sdd-design` → `sdd-tasks`, auto mode, each gate-validated)
- [x] 4. Write slice (b) `extraction-versioning-api` — proposal, 7 delta specs, design, tasks
- [x] 5. Write slice (c) `extraction-versioning-prompt` — proposal, 4 delta specs, design, tasks
- [x] 6. Validate all three with native `gentle-ai sdd-status --contract gentle-ai.sdd-status/v2`
  and report the per-slice Review Workload Forecast (ask-on-risk gate)
- [x] 7. Land the planning artifacts on `main` (`3ddbe28`, `66bbb3b`)
- [x] 9. **Owner decision on the `0028` deploy blocker** — asked and answered 2026-09-30: **purge
  window**. Nothing was executed; the runbook lives in `prod.todo.md`, and the wipe and the merge are
  two separate confirmations that still have to happen, in that order.
- [x] 10. **Task 4.4 of slice (a)** — closed 2026-09-30 with Option A: `revoked_by` becomes `RESTRICT`
  deliberately, the equivalence CHECK stays whole, and `0028` was edited rather than superseded because
  it is unreleased. Cost of finding out: the "it is latent because no user-deletion route exists"
  argument used to justify it was **false** — that is defect **D-a-4**, carried into slice (b).
- [ ] 13. **D-a-4** — `DELETE /api/v1/users/me` (`api/routes/settings.py:335`) has no `IntegrityError`
  mapping, so once a revocation row can exist the refusal is an HTTP 500. Belongs to slice (b), with the
  route's first DELETE-verb test.
- [x] 14. ~~Production `workspace_llm_configs.provider = 'Nan'`~~ — **withdrawn, it was never a defect.**
  Measured against the table that defines the value: `custom_providers` holds one row whose `name` md5
  equals md5('Nan'), and one `workspace_llm_configs` row references it with a real encrypted key.
  Custom providers have free-form names by design (`0021`); only reserved names are refused.
- [ ] 15. Smaller real item that survived the correction: deleting a `custom_providers` row would leave
  the `workspace_llm_configs` rows naming it without an FK to complain — `provider` is a plain string.
  Harmless at 1 row and 4 configs; look at it if a custom provider is ever deleted. **After the purge
  this one is moot in production** (both tables are empty); it still matters for any environment that
  keeps data.
- [x] 16. **Merge + deploy + production verification — DONE 2026-09-30** under the owner's "haz tú el
  merge y todo lo que queda". PR #30 merged as merge commit `1dcc716` (repo convention; squash would
  have collapsed the twelve work-unit commits), deploy run 36675276096 `success`, CI on `main` run
  36675276085 `success`, and `0028` verified by reading production Neon: `alembic_version = 0028`,
  `task_invalidations` with the revoker FK `ON DELETE RESTRICT`, both unique/partial indexes,
  `tasks.extraction_id NOT NULL`, eleven tables still at 0, health `ok`.
- [ ] 19. **D-a-5 — live consequence of shipping (a) alone, found while closing the merge.** Two
  production-visible facts, both confirmed in shipped code and measured against the running API, neither
  reachable by a human today: (1) `task_repository.list_by_story:120-123` and `list_by_workspace:125-133`
  (plus `routes/export.py:53,102`) have **no current-version predicate**, so two `completed` runs on one
  story show **both runs' task sets** in the board, story detail and export — precisely the effect slice
  (a)'s own proposal item 13 predicted when it said *"do not deploy (a) alone"*; (2) `POST /api/v1/tasks/`
  is published as `201 Successful Response` in production's live `openapi.json` with `/docs` returning
  `200`, while the route answers 500 `REPOSITORY_ERROR` (pinned by `tests/test_api/test_tasks.py:47,:67`).
  Exposure today is zero for two accidental reasons, not by design: `users` is empty after the purge, and
  `frontend/src/lib/tasks-api.ts` has no create-task call at all. **Fix is already planned:** (b) WU1
  retires the route with `410`, (b) WU3 adds the current-version predicate. So the rule that comes out is
  a sequencing rule: **(b) WU1 + WU3 before the thesis evaluation**, and anyone testing before that must
  know re-extracting a story duplicates its tasks. Tracked in `prod.todo.md`.
- [x] 17. **Archive — DONE by hand 2026-09-30.** `openspec` is neither installed nor a project dependency
  here, so `openspec archive` could not run. Both deltas are pure `## ADDED Requirements` for capabilities
  that did not exist in the store, which makes the sync mechanical and diff-checkable: `openspec/specs/extraction-versioning/spec.md`
  (8 reqs / 23 scenarios) and `openspec/specs/task-invalidation/spec.md` (6 reqs / 13 scenarios), each
  verified byte-identical to its delta modulo the header. The change moved to
  `openspec/changes/archive/2026-09-30-extraction-versioning-schema/` with an `archive-report.md` that says
  plainly it was hand-made and that **`openspec validate` never ran**. What was originally left undone
  —`make bump`— **was done later the same day on the owner's explicit instruction**: `v0.9.0` is released
  and deployed, evidence in `prod.todo.md` ("Release `v0.9.0`").
- [ ] 18. **Operational, needs the owner's hands:** log in again, then create the workspace LLM config in
  Configuración before any extraction — `resolve_llm_config` falls back to `provider = "ollama"` and
  production has no Ollama. The two api_key values must come from the AI Studio and nan.builders consoles.
- [ ] 11. Apply slice (b) `extraction-versioning-api` **after (a) merges** — it inherits **D-a-1** as a
  named requirement (re-dispatch duplicates task rows, `extraction_task.py:441`).
- [ ] 12. Apply slice (c) `extraction-versioning-prompt`.
- [x] 8. Apply slice (a) — Schema Identity **and** Birth Through Allocation, merged into one green
  work unit (`1a90aff`, `1f2d573`), then Phase 3 in four tranches and Phase 4 in two
  - **RED landed 2026-09-29, uncommitted on purpose.** 14 new cases across three files;
    `12 failed, 1010 passed, 21 deselected` against a 1008-pass baseline. WU1 must land as one green
    commit, so the RED is a review artifact, not a commit.
  - **The delegated writer died mid-run on a provider quota error**, not on the work: `sdd-apply`
    returned `API 429 … claude-opus-5 … limit 99.97%` after 7 turns / 22 tool calls, without ever
    returning its evidence report. All three files were already written; the parent verified them
    against the tasks, fixed one blemish (a `pytest_asyncio` fixture that imported the missing model
    at *setup* time, producing `ERROR` instead of a per-test `FAILED`), and re-ran the suite itself.
    Treat any future `sdd-apply` delegation in this session as quota-at-risk.

## Acceptance-criteria coverage audit (parent, 2026-09-28)

All 26 rows of the source spec's "Criterios de aceptación" map to at least one requirement across
the 37 requirements in the nine delta-spec files, **except one**:

- **"La limpieza de D11 se ejecutó y quedó registrada, con su confirmación"** — deliberately not a
  task in any change. It is a destructive data operation with its own confirmation and record, and it
  is a **precondition of the deploy** that carries `0028`, not a step of the feature. It is recorded
  in each change's `## Slice Boundary`; it belongs in the deploy runbook (`docs/deployment.md`),
  which is outside these three changes.

Three cross-slice seams needed a parent annotation so each change reads honestly on its own:

| Seam | Where it was invisible | Annotation added |
| --- | --- | --- |
| (b)'s mark/revoke endpoints never call `set_has_invalid_tasks` | read alone, (b) looks complete; skipping (c) 3.6–3.8 ships marks that exclude **nothing** from few-shot retrieval, with no red test | `(b) tasks.md`, bold warning in `## Slice Boundary` |
| (a) 3.4's `generate() -> tuple` is superseded by (c) WU2 2.8; (a) 2.3 threads only `temperature` and `version_number` arrives in (c) WU3 3.5 | an (a) reviewer would see later edits to lines (a) declared final | `(a) tasks.md`, "do not treat (a)'s shape as final" |
| (a)'s design claimed slice (c) needs no change to `render()`'s signature | wrong on the **input** side: D9's context comes from repositories and `ExtractionService` is repository-free | corrected in `(a) design.md`, with the rejected readings |

Native `sdd-status` resolves all three changes with `proposal/specs/design/tasks = all_done` and
`apply = ready`, and now reports the slice graph through the optional `state.yaml` hint (`dependsOn`
on (b) and (c)).

## Review Workload Gate — RESOLVED by the user on 2026-09-28

Every slice forecasts over the 400-line budget. The `ask-on-risk` pause was answered:

```text
Chain strategy: chained PRs, one PR per work unit, in the dependency order (a) → (b) → (c)
size:exception: accepted for exactly three units — (a) WU1, (b) WU2, (b) WU4
```

| Slice | Estimated changed lines | Units under the exception | Units chained |
| --- | --- | --- | --- |
| (a) `…-schema` | ≈2,250–3,000 | **WU1** (≈1,300–1,700 — the `NOT NULL` seed ripple across ~32 fixtures in ten files has no green intermediate) | WU2, WU3a, WU3b, WU4 |
| (b) `…-api` | ≈4,400–5,700 | **WU2** (≈420–520, atomic cross-stack) and **WU4** (≈1,300–1,700, the storage half has no greener boundary) | WU1; WU3/WU5/WU6 split on their named axes, each half green |
| (c) `…-prompt` | ≈2,500–3,400 | none — not needed | WU1 (3 parts), WU2 (2), WU3 (3, payload keys **before** the fail-closed filter), WU4 is the operator bench run, not a code PR |

The decision is recorded in each change's own `tasks.md` under
`### Delivery decision — accepted by the user on 2026-09-28, before apply`, so `apply` reads it from
the artifact rather than from conversation. The exception transfers to no other unit: a unit that turns
out larger in practice than forecasted goes back on the table.

### Apply authorization — granted by the user on 2026-09-29

```text
Apply: authorized, in tranches — the RED tests of (a) WU1 land first and stop for human review.
Verification split: the provable half runs locally on SQLite; the Postgres half runs in CI.
Planning artifacts: land on main as a docs commit, with .codegraph/ ignored first.
```

The tranche rule is the user's working pace, not a budget: each tranche is shown for review before
the next one starts. GREEN, TRIANGULATE and REFACTOR of WU1 are **not** yet authorized.

The D11 wipe remains a precondition of the *deploy* that carries `0028`, not of the code landing, and
is still not authorized.

## Verification environment — measured 2026-09-29, before the first line of code

| Check | Result |
| --- | --- |
| `main` == `origin/main` | `ecea3e2` |
| Baseline unit layer | `conda run -n storico python -m pytest -m "not integration"` → **1008 passed, 21 deselected** (32.7 s) |
| conda `storico` | present (`/opt/homebrew/Caskroom/miniconda/base/envs/storico`) |
| Docker | **absent** — no CLI, no Docker/OrbStack/Rancher app, no colima, no podman |

Consequence, stated rather than worked around: tasks **1.18** and **1.19** (and every
`@pytest.mark.integration` case) skip locally and stay unverified here. They are exercised by CI,
which runs `pytest -q` with no `-m` filter on a runner that has Docker
(`.github/workflows/ci.yml:44`). SQLite is not a stand-in for the Postgres-only claims: the DDL,
`downgrade`, the story cascade and the real allocation collision stay CI-side until CI says
otherwise. Nothing in this document calls an unverified invariant green.

## Commit evidence

### Slice (a), merged WU1 — landed on `feat/extraction-versioning-schema-wu1`

| Commit | Content |
| --- | --- |
| `c47a1b2` | `feat(extraction): snapshot the prompt at the moment it is rendered` — 3a. `1035 passed` |
| `3364c43` | `refactor(extraction): write terminal states through the mark methods` — 3b-i, task 3.5. `1039 passed` |
| `366c341` | `refactor(extraction): delete the dead extraction path and its wrapper` — 3b-ii-a, tasks 3.3/3.4/3.6 |
| `3a23655` | `refactor(extraction): remove save() so the repository has no whole-row writer` — 3b-ii-b, task 3.7 |
| `94db112` | `test(extraction): pin versioned task rows on the live path` — 3b-iii, tasks 3.2/3.8/3.9, defect D-a-1 |
| `20a7e02` | `test(extraction): prove the invalidation invariants are guarded` — WU4a, tasks 4.1/4.2/4.5, mutation matrix |
| `(this)` | `test(extraction): witness the invalidation invariants only Postgres can see` — WU4b, task 4.3, defect D-a-2 |
| `1a90aff` | `feat(extraction): give every run a version and its tasks a parent` — migration `0028`, the four new columns, `tasks.extraction_id`, `task_invalidations`, the port/repo allocation, the route's birth through `create_next_version`, `DEFAULT_TEMPERATURE`, the four runner rebuilds, the dead path allocating its own number, and the seed rewiring. 2,125 reviewable code lines |
| `1f2d573` | `test(extraction): pin the 0028 invariants only Postgres can prove` — the six integration cases (1.18/1.19). 532 lines, **collected and linted but never executed here** |

Branch total against `main`: **33 files, 2,439+/453−**. Task ledger for this slice: 1.1–1.20 and
2.1–2.6 are checked; 3.x and 4.x are not started.

Verified on this machine before each commit: `1031 passed, 27 skipped, 0 failed`; `ruff check src
tests` clean; `ruff format --check src tests` clean (253 files). The 27 skips are the
`@pytest.mark.integration` cases, including the six new ones — **no Docker daemon exists on this
machine**, so the Postgres half of WU1 has never run and is claimed only by CI.

Two audit findings worth repeating, because they are what made this unit land at all:

- The writer reports died on a provider 429 both times; the tree was verified by the parent against
  the tasks, not against the writer's narrative. Nothing was committed on the strength of a report.
- 25 `assert` lines left the suite and 37 arrived. Every removal is accounted for by the plan: three
  `status_code == 201` → `500` (task 1.17), three `save.called` → `create_next_version.called` (the
  dead-path decision), and the body of the `delete` case task 1.20 removes. No case was deleted and no
  assertion was weakened to reach green; test counts per file are unchanged (23→23, 12→12, 9→9,
  19→19, 24→24).

### Planning artifacts

Planning landed on `main` before any implementation branch was cut:

| Commit | Content |
| --- | --- |
| `3ddbe28` | `chore: ignore the local CodeGraph index` — `.codegraph/` is derived state and must not ride a docs commit |
| `66bbb3b` | `docs(openspec): commit the 0.9.0 extraction-versioning planning` — 27 artifacts |
| `1737708` | `docs(odd): record the 0.9.0 apply authorization and its commit evidence` |

The 27 artifacts are:

```
openspec/changes/archive/2026-09-30-extraction-versioning-schema/{explore,proposal,design,tasks}.md
  + specs/{extraction-versioning,task-invalidation}/spec.md
openspec/changes/extraction-versioning-api/{explore,proposal,design,tasks}.md + state.yaml
  + specs/{extraction-versioning,task-invalidation,workspace-permissions,task-editor,
           kanban-board,extraction-workflow,export-download}/spec.md
openspec/changes/extraction-versioning-prompt/{explore,proposal,design,tasks}.md + state.yaml
  + specs/{extraction-context,extraction-versioning,few-shot-retrieval,vector-store-isolation}/spec.md
odd/tasks/extraction-versioning-090.md
```

Work-unit commits get recorded here as they happen; native review runs only under the user-owned RDD
switch, which reads **off** in this clone.

---

## Session handoff — 2026-09-30 (slice (a) delivered, merge blocked on purpose)

Written for a session that starts with nothing in context. Read in this order: this section, then
`openspec/changes/archive/2026-09-30-extraction-versioning-schema/verification.md`, then `prod.todo.md`'s
"Bloqueo de despliegue" item.

### Where things stand

| | |
| --- | --- |
| PR | **#30** — <https://github.com/alvaldes/storico/pull/30> — base `main`, **MERGED 2026-09-30 as merge commit `1dcc716`**. Its body was updated before the merge to record D-a-2 closed, D-a-4 opened and D-a-3 chosen-but-unexecuted with measured numbers, which is why `mergeable=CLEAN` never read as "safe to merge" |
| Deploy | `deploy-backend.yml` run **36675276096** → `success` (2m1s) on `1dcc716`; CI on `main` run 36675276085 → `success`. `0028` verified in production Neon, read-only: see "Deployed" below |
| Branch | `feat/extraction-versioning-schema-wu1`. **Deliberately not pinned to its own HEAD sha or commit count** — a commit cannot truthfully cite the sha it is creating. Measure at review time: `git rev-list --count main..HEAD` and `git diff --shortstat $(git merge-base main HEAD)..HEAD`. Two counts were wrong here before this note (the PR body's "15 commits / 38 files" and this table's "21 commits"), which is why the commands replaced the numbers |
| Last measured | at `7e3aa6e`: **26** commits over `main` `1737708`, `41 files changed, 5027 insertions(+), 1001 deletions(-)` |
| CI on `382a9c5` | **`1064 passed, 18 skipped`** (run 36658068793) — the same 15 integration cases as the earlier run, now including the renamed revoker-FK case, so `RESTRICT` is observed and not inferred |
| Local suite | `1049 passed, 33 deselected`, 0 failed · `ruff check`/`format --check` exit 0 |
| Open tasks in the change | **none** — 4.4 closed 2026-09-30; 1.1–1.20, 2.1–2.6, 3.1–3.9, 4.1–4.5 and 5.1–5.6 are closed |
| Blocked on | **nothing** — D-a-3 closed end to end: interlock → wipe → merge → deploy → verification |
| Deployed | production now runs `0028`: `alembic_version = 0028`, `task_invalidations` exists with `fk_task_invalidations_revoked_by_users ... ON DELETE RESTRICT`, `uq_extractions_story_version`, partial `uq_task_invalidations_active_task`, `ck_task_invalidations_revoke_pair`, `tasks.extraction_id NOT NULL`; eleven business tables at 0; three Qdrant collections at 0 points; `/api/v1/health` → `ok` |
| Released | **`v0.9.0`** — `make bump` on the owner's order 2026-09-30: commit `fb25478`, tag `v0.9.0`, MINOR from the two `feat(extraction)` commits with no `!`/`BREAKING CHANGE`. Pushed with the tag; deploy `36747695497` → `success`; CI → `success`; `/api/v1/health` → `0.9.0`. `alembic_version` still `0028`: the bump moved no schema |
| Needs a human | re-create the workspace LLM config in Configuración before any extraction: `resolve_llm_config` (`api/routes/workspace_settings.py:121-129`) falls back to `provider = "ollama"` + `settings.ollama_host` when a workspace has no config row, and production has no Ollama. Also: log in again (no `users` rows), and the AI Studio / nan.builders keys must come from their consoles |
| Archived | **by hand, 2026-09-30** — store updated (`openspec/specs/extraction-versioning`, `openspec/specs/task-invalidation`) and the change moved to `openspec/changes/archive/2026-09-30-extraction-versioning-schema/` with `archive-report.md`. **`openspec validate` did not run** (no CLI); structure was diffed against the repo's own `2026-09-14-few-shot-qdrant` precedent instead |
| Not authorized | slice (b) `extraction-versioning-api`, slice (c) `extraction-versioning-prompt` |
| Receipt-driven development | still **off** in this clone; no native review ran on any tranche |

Landed tranches, in order: `1a90aff` + `1f2d573` (merged WU1+WU2: schema and birth), `c47a1b2` (3a
render snapshot), `3364c43` (3b-i marks), `366c341` (3b-ii-a dead path deleted), `3a23655` (3b-ii-b
`save()` removed), `94db112` (3b-iii triangulates), `20a7e02` (WU4a invariants + mutation matrix),
`7a98c19` (WU4b Postgres half), then the `fix(test)` chain `3333b7b` / `4da58fb` / `962359a` and the
doc commits.

### The blocker (D-a-3), the reason the PR was not merged — **CLOSED 2026-09-30: purge → merge → deploy → verification**

`.github/workflows/deploy-backend.yml:101` runs `alembic upgrade head` on **every** deploy.
`0028:41` reads `SELECT count(*)` on `extractions` and `tasks` and raises `RuntimeError` if either is
non-empty — decision D11, no backfill. So **merging to `main` takes the API down on purpose**: the
container is already stopped by the time the migration fails. That is the workflow behaving as designed,
not a deploy.

**Decided 2026-09-30: path 1, the purge window.** Not executed: the wipe and the merge are separate
explicit confirmations, and the runbook in `prod.todo.md` is the thing to read before either.

**The premise was cited against the wrong store until it was measured.** This section said production has
real rows because the **Qdrant** collection `storico_extractions_prod` was measured on 2026-09-28, but
the guard counts the **relational** tables. A read-only pass against the production database gives:
`alembic_version = 0027`; **17** `extractions` (11 `failed`, 6 `completed`, 2026-08-03 → 2026-09-24);
**42** `tasks`, all in `backlog`; 6 stories, 3 projects, 3 users, 4 workspaces; and
`task_invalidations` **does not exist** there yet. Same verdict, honest evidence.

Three paths, written out in `prod.todo.md`; **path 1 chosen, none executed**:

1. **Purge window** ← **chosen.** Empty `extractions`/`tasks` in Neon — and, extended 2026-09-30, the
   Qdrant points too — letting `0028` run on the empty pair, with **no backup**: the owner waived it
   ("nothing worth saving") and the runbook's backup step became a measured inventory instead. Costed, then corrected downward: the Qdrant point id **is** the `extraction_id`
   (`qdrant_adapter.py:255`) and the payload carries the story text and the task summary, so few-shot
   retrieval keeps working after the wipe. What is lost is **provenance**, not function — and what gets
   purged is 11 failed runs and 42 tasks that never left `backlog`.
2. **A `0029` backfill** — rejected on cost, after measuring what it would actually have to invent.
   D11's stated reason named the wrong column: `temperature` is genuinely unrecoverable (the key is on
   17/17 rows, the **value is JSON `null` on 17/17**), `provider` **is** derivable per row through
   story → project → workspace → `workspace_llm_configs.provider`, as a hypothesis about the past, and
   `version_number` is derivable from `created_at`. The irreducible field is **`tasks.extraction_id`:
   28 of 42 tasks sit on single-run stories and 14 of 42 do not**, with no record of which run produced
   them. Three assertions about thesis data, for data the measurement describes as test traffic.
3. **Hold the PR** — what the slice plan already assumed; still available, and what has been happening
   until this decision.

### Two open defects

**D-a-2 / task 4.4 — CLOSED 2026-09-30, Option A (`RESTRICT`).** `revoked_by ON DELETE SET NULL`
(:104-109) coexisted with `CHECK ((revoked_by IS NULL) = (revoked_at IS NULL))` (:114-117). Postgres
evaluates CHECKs during the referential action, so deleting such a user **fails**. CI observed it under
the old shape: `test_deleting_the_revoking_user_meets_the_revoke_pair_check` passed by asserting the
refusal. The owner chose FK → `RESTRICT`, keeping the equivalence CHECK whole, edited in `0028` and its
ORM mirror in the same change (the autogenerate drift gate catches a one-sided edit, and that gate is
itself `integration`-marked, so it runs in CI too). The case is now
`test_deleting_the_revoking_user_is_refused_by_the_revoker_fk` and expects the FK name in the driver
message. Locally: `1049 passed, 33 deselected` plus `540 passed`, lint and format clean. **The RESTRICT
behaviour could not be verified here — no Docker daemon — and CI observed it: run 36658068793 on
`382a9c5` reports `1064 passed, 18 skipped`, so the refusal came with a message naming
`fk_task_invalidations_revoked_by_users`.** D-a-2 is closed with evidence on both halves.

~~The app serves no user-deletion route, so it is latent either way.~~ **That justification was false.**
See **D-a-4** below, which replaces it.

**D-a-4 — the account-delete route exists, and the refusal surfaces as a 500.** Found while writing the
sentence above. `DELETE /api/v1/users/me` is live (`api/routes/settings.py:335`; router prefix at `:31`)
and its docstring promises every related row is cascade-deleted. `UserRepository.delete`
(`:74-79`) issues a bare `delete(UserModel)` with **no `IntegrityError` handling** — unlike `save()` and
`link_account()` in the same file — and `api/app.py:149-176` registers no handler for it, so it falls to
`generic_error_handler` (`api/errors.py:161-175`): **HTTP 500, `{"detail": "Internal server error"}`**.
No test issues that verb (`delete("…/users/me")` across `tests/`: empty). D-a-2 is still latent, but
because **slice (a) ships no port, repository or route that writes a `task_invalidations` row** (grep
`Invalidation` in `src/storico`: only the model and `__init__`), not because no deletion path exists.
Carried into slice (b) as a named requirement: when the mark endpoints make the row writable, that 500
becomes the designed answer to a real user action and has to become a 409-with-reason or a pre-check.

**D-a-1 — re-dispatching a run duplicates its task rows.** `extraction_task.py:441` is an INSERT-only
persist loop with no `extraction_id` guard; re-dispatching `run_background_extraction` for the same id
appends a second set of rows (probed: a 2-task run yields 3 rows). Latent: every live path either mints
a new version or only calls `mark_failed` (`recover_stuck_extractions` → `:193`). Deliberately not fixed
in slice (a) — both candidate fixes change behaviour slice (b)'s endpoints depend on. **Carry it into
(b) as a named requirement.** Note that `3b-iii`'s test pins the spec's "one row, one number" and *not*
"one set of task rows", precisely because the code does not guarantee the latter; do not "fix" that test
to assert more than the code does.

### What CI proved that this machine could not

- No index-name drift: `pg_indexes` reports exactly `pk_task_invalidations`,
  `ix_task_invalidations_task_id`, `uq_task_invalidations_active_task`, matching what `Base.metadata`
  expands, and `test_migration_chain.py`'s `_KNOWN_DRIFT` is empty.
- `uq_task_invalidations_active_task` really is a **partial** index, and no full unique index on
  `task_id` exists.
- `0028` upgrades, downgrades to `0027`, and re-applies head on a real Postgres.
- The duplicate `(user_story_id, version_number)` pair is refused by name; `tasks` refuses a null
  `extraction_id`; the story cascade is scoped to one story.
- **15 integration cases ran green in CI.** The 18 that still skip are Qdrant-backed and need a live
  vector store — nothing in this change claims evidence about Qdrant.

### Environment facts a new session must not re-derive

- **No Docker daemon on this machine** (no `docker`, OrbStack, colima, podman).
  `@pytest.mark.integration` cases skip locally. Never describe a Postgres-only invariant as verified
  unless CI ran it.
- `PRAGMA foreign_keys` is **OFF** and nothing in the repo enables it (verified: zero occurrences in
  `tests/` and `src/`; a fresh aiosqlite connection reports `0`). **No FK action of any kind fires in
  the unit layer** — the unit suite proves `NOT NULL`, `CHECK`, `UNIQUE` and partial-unique behaviour,
  and proves nothing about `CASCADE` or `SET NULL`.
- Runner: `cd backend && conda run -n storico python -m pytest -m "not integration" -q`. There is no
  `.venv`; the conda env `storico` is canonical.
- When reading `conda run` output, **do not pipe to `tail` before checking the exit status**: a pipe
  reports the tail's status, which is how a lint failure nearly entered a commit here.
- Provider quota killed two `sdd-apply` writers in the previous session (HTTP 429, cache-read ≈100%).
  What worked instead: **2–4 file surfaces per tranche** — five consecutive writers landed green.

### Notes on the harness, because they repeat

- **Commit messages: write them to a file and use `git commit -F /tmp/msg`.** Two heredoc attempts
  failed in this session and one pushed a commit titled literally `NOPE`, which is still in the branch
  history (`3333b7b`) because rewriting published history needs the owner's explicit say-so.
- A lease-holding force-push is blocked by this repo's Gentle AI safety policy, which then asks the
  human. The non-destructive repair for a duplicated local commit was rebasing the branch onto its own
  remote: git dropped the identical patch on its own.
- Destructive-looking command literals inside a heredoc also trip that policy, even when the intent is
  documentation. Write the prose to a file instead of inlining it in a shell command.
- The `branch-pr` skill (issue-first, one `type:*` label) is **not** this repo's practice: no PR
  template, no validation workflow, GitHub's default label set with no `type:*` or `status:approved`,
  and the eight most recent merged PRs carry 0 labels and close 0 issues. PR 26 landed `WU1+WU2+WU5`
  as a single PR.
- Three CI rounds were needed on my own integration file, and **every failure was a harness bug wearing
  a schema costume**: `default=uuid7` read before the flush; a schema-mutating case sharing the module
  database (which poisoned seven later cases); `AUTOCOMMIT` documented but never set; and ORM
  attributes read after a rollback — `expire_on_commit=False` does not govern rollbacks. A green local
  unit layer was never evidence about that file, and the PR body said so before anything ran.

### Resuming, in order

1. ~~Ask the owner for the blocker decision.~~ **Asked and answered 2026-09-30: path 1, the purge
   window.** Runbook written in `prod.todo.md`, **not executed**.
2. ~~Close task 4.4 in the same edit as that decision.~~ **Done** — Option A, `RESTRICT`, both files.
3. **The wipe is DONE (2026-09-30 ~04:28 UTC); only the merge is left.** Executed after the owner confirmed
   the scope three times, including once with the API-key consequence stated explicitly. An interlock
   refused to run unless all eleven table counts, `alembic_version` and the three Qdrant counts matched
   the inventory committed at `9a5086c`; then one transaction truncated the eleven tables
   (`RESTART IDENTITY CASCADE`) and three `points/delete` calls emptied the three collections.
   Verified from a separate process: 11 tables at 0, 3 collections at 0 points, `alembic_version` still
   `0027`, `GET /api/v1/health` → `ok` (`database ok`, `schema ok`). Both open runbook choices closed by
   the owner's scope decision: all three collections, and `user_stories` wiped — so the denormalized
   `status` question no longer applies.
   ⚠️ **Until the merge lands, nothing may run an extraction in production.** `0028`'s guard fires on
   *any* row, so a single extraction re-creates the exact blocker that was just paid for in data.
4. ~~**Mergear**~~ **DONE 2026-09-30, authorized by the owner ("haz tú el merge y todo lo que queda").**
   Merged as a **merge commit** (`1dcc716`), not squash: `main`'s history is merge commits (`#24`–`#29`),
   and squashing would have collapsed the twelve work-unit commits that are this branch's reviewable
   unit. Deploy `run 36675276096` → `success`; CI on `main` → `success`. Verified in production read-only:
   `alembic_version = 0028`, `task_invalidations` with the revoker FK `ON DELETE RESTRICT`,
   `uq_extractions_story_version`, `uq_task_invalidations_active_task`, `tasks.extraction_id NOT NULL`,
   eleven tables still at 0, health `ok`. **Deliberately not done: `make bump`** (release decision, and
   `0.9.0` is three slices with one shipped). **`openspec archive` was done by hand**, because the CLI is
   absent and both deltas are pure additions to capabilities the store did not have — see the archive
   report, which names the one check that could not run (`openspec validate`).
4. Slice (b) then needs its own apply authorization, carrying **three** named requirements: **D-a-1**
   (re-dispatch duplicates task rows), **D-a-4** (the account-delete 500), and retiring
   `POST /api/v1/tasks/`, which slice (a) currently pins as a 500 refusal (`tasks.extraction_id NOT
   NULL`) — that pin is honest about being temporary. Slice (c) after that.
   **The carry-over is materialized, not just promised:** `grep` for `D-a-1`/`D-a-4` in slice (b)'s
   artifacts returned **zero** before this, so the sentence above was a promise in (a) and absent from
   the destination. Both defects are now named in
   `openspec/changes/extraction-versioning-api/tasks.md` (§"Defects carried in from slice (a)",
   commit `5f04d10`), with line numbers re-measured on `main` — `extraction_task.py:441` for D-a-1 and
   `settings.py:335` → `user_repository.py:74-78` → `errors.py:161` for D-a-4 — attached to the work unit
   where each stops being latent (WU5 for D-a-4), and explicitly **excluded** from the 77 tasks and the
   line forecast so the estimate gets updated by choice, not by surprise mid-PR.
5. Do not renumber task IDs. Slices (b) and (c) reference (a) IDs such as 2.3, 3.4 and 3.7.
6. Side item, closed by measurement rather than by a fix: the production `provider = 'Nan'` that an
   earlier version of this document called a defect is a legitimate custom provider (`custom_providers`,
   added by revision `0021`, free-form names). The correction and the lesson are in `prod.todo.md`.

## Session handoff — 2026-09-30 (b): the blocker got decided, and the measurement corrected two documents

Everything above stays true. This is what changed in the session that closed 4.4.

**Two owner decisions, both taken inside the session's question round:**

- **D-a-3 → path 1, the purge window, scope chosen by the owner 2026-09-30:** **the whole business
  schema, configs and prompts included, plus all three Qdrant collections — and no backup.** Executed the
  same day, then merged and deployed; `prod.todo.md` carries the runbook and the verification.
  The chosen scope is wider than `0028` needs: `0028` only requires `tasks` and `extractions` to be empty,
  and the owner also asked for `users`, `workspaces`, `workspace_members`, `projects`, `user_stories`,
  `workspace_llm_configs`, `workspace_prompts` and `custom_providers`, i.e. 11 tables and 21 vector points.
  **One consequence I surfaced before firing it, not after:** two `workspace_llm_configs.api_key` values
  are Fernet ciphertexts whose plaintexts match nothing on this machine (compared in memory against all
  32 `STORICO_*` values in `.env.prod.local` and `.env`, no secret printed). Deleting them is the only
  truly irreversible part of this wipe, because the rows must be re-typed from the nan.builders and AI
  Studio consoles before any extraction can run again. Their non-secret settings are recorded in
  `prod.todo.md` so the config can be rebuilt exactly: `Nan` / `qwen3.8-flash` / `api.nan.builders` /
  0.1 / 2048, and `gemini` / `gemini-2.5-flash` / `base_url = localhost:11434` (an Ollama-shaped URL in a
  production row, noted without concluding — the Gemini adapter may ignore it).
  Wiping `user_stories` also dissolves the denormalized-status question the runbook used to leave open:
  `tasks` and `extractions` are `ON DELETE CASCADE` off `user_stories.id`, so one statement empties all
  three and no story is left claiming `extracted` over zero extractions.
- **D-a-2 → Option A, `revoked_by` `ON DELETE RESTRICT`,** which closes task 4.4 and makes slice (a)
  **46/46**. `0028` and `models/task_invalidation.py` moved as one edit because the autogenerate drift
  gate catches a one-sided change — and that gate is `integration`-marked, so it runs in CI, not here.

**The measurement that changed the docs.** A read-only pass against production (authorized in the same
round, `SELECT count(*)` and type probes only, DSN never printed) found that D-a-3's premise was
*correct but cited against the wrong store* — Qdrant instead of the relational tables the guard counts —
and that **D11 named the wrong unreconstructable column**. `provider` is derivable per row (as a
hypothesis about the past); `temperature` is genuinely gone (key on 17/17 rows, **value JSON `null` on
17/17**); `version_number` is derivable from `created_at`; the irreducible field is
`tasks.extraction_id`, ambiguous for **14 of 42** rows. Costing the purge in the other direction: the
Qdrant point id *is* the `extraction_id` and the payload is self-contained, so wiping relational data
removes provenance, not few-shot function.

**A justification that was false, and the defect it hid.** Slice (a) called D-a-2 latent because "the app
serves no user-deletion route". It does: `DELETE /api/v1/users/me` (`api/routes/settings.py:335`), with
`UserRepository.delete` (`:74-79`) issuing a bare delete that catches nothing, no `IntegrityError`
handler registered in `api/app.py:149-176`, and `generic_error_handler` (`api/errors.py:161-175`)
turning the refusal into **HTTP 500 `{"detail": "Internal server error"}`**. No test issues that verb.
Recorded as **D-a-4** and carried into slice (b) next to D-a-1: the refusal is only reachable once the
mark endpoints exist, which is exactly when it must stop being a 500.

**"A production defect" that was not a defect, and why it is recorded anyway.** An earlier commit in
this session filed `provider = 'Nan'` as someone saving a stringified `NaN`, because `md5()` and
`length()` matched and the column is a plain `String(50)`. Measured against the table that **defines**
the value, it is correct: `custom_providers` has one row named `'Nan'` — custom providers are a feature
since revision `0021`, with free-form names and only reserved names refused
(`routes/workspace_settings.py:264`) — and the one `workspace_llm_configs` row pointing at it carries a
real encrypted key, `temperature 0.1`, `max_tokens 2048`. Those two runs are the `qwen3.8-flash` ones.
The lesson is the second one of the session in the same shape: I called a value broken without reading
where it is created. Suspicious-looking data is not evidence; the schema that accepts it is.

**Method lessons, because they repeat.** (1) `prompt_config ? 'key'` measures the *key*;
`->> 'key' IS NOT NULL` measures the *value*. Reading only the first produced the opposite answer for
`temperature`, and my own first pass reported "17 recoverable" from it. (2) `fetchval` on a multi-row
query silently returns row one: the first probe's key list showed `system_prompt` as the only key when
there were three. (3) Both were caught only because every number was computed twice through
independent SQL and the disagreements were printed instead of picked. (4) A premise inherited from an
earlier session — "production has data" — was worth measuring even though the conclusion held.

**Verified locally:** `1049 passed, 33 deselected` over the same 1082 · `540 passed` for
`tests/test_repositories tests/test_unit` · `ruff check` and `ruff format --check` exit 0.
**Not verifiable here, and closed by CI afterwards:** the RESTRICT refusal and the autogenerate drift
gate are both `integration`-marked. Run 36658068793 on `382a9c5` — after the push this session
authorized — reports `1064 passed, 18 skipped`: the renamed case ran and asserted the FK name in the
driver message. So 4.4 has evidence on both halves, and the one thing this machine could never prove is
no longer open. Both needed Postgres, and Postgres only exists in CI here.

---

## Session handoff — 2026-09-30 (final): the merge, the deploy, and the archive nobody could run

Slice (a) is **shipped**. What happened after the purge, and what is now true.

**The merge, and why it was not a squash.** The owner said "haz tú el merge y todo lo que queda", so the
merge became an executed action instead of a recommendation. `main`'s first-parent history is merge
commits (`#24`–`#29`), and this branch's reviewable unit is twelve work-unit commits — squashing would
have collapsed exactly the thing the whole session was built around. So: `gh pr merge 30 --merge` →
merge commit **`1dcc716`**, mergedAt `2026-09-30T05:50:33Z`.

**The deploy was the risky half, and it was a real swap, not a rollout.** `deploy-backend.yml` stops the
container, runs `alembic upgrade head` between `stop` and `run`, and starts again: the maintenance window
that ADR-005 chose. Run **36675276096** → `success` in 2m1s. CI on `main` run 36675276085 → `success`.
Had the pair not been empty, this is the step that would have left the API down on purpose.

**`0028` verified by reading production, not by reading the job log.** Independent read-only pass:
`alembic_version = 0028`; `task_invalidations` exists with `fk_task_invalidations_revoked_by_users`
**`ON DELETE RESTRICT`** (the task 4.4 fix the owner chose as Option A — CI proved it on CI's Postgres,
this is the first time it was observed on Neon), `fk_task_invalidations_marked_by_users` still
`SET NULL`, `ck_task_invalidations_revoke_pair` and `ck_task_invalidations_reason_not_blank` intact;
`uq_extractions_story_version`, partial `uq_task_invalidations_active_task` (`WHERE revoked_at IS NULL`),
`tasks.extraction_id` **NOT NULL**; eleven business tables still at 0; three Qdrant collections at 0
points, `status=green`; `/api/v1/health` → `ok`, `database ok`, `schema ok`, version `0.8.0`.

**The finding that outlived the deploy: the app is healthy and cannot extract.** Nobody asked for this
and no migration reports it. With `workspace_llm_configs` empty, `resolve_llm_config`
(`api/routes/workspace_settings.py:121-129`) returns `provider = "ollama"` + `settings.ollama_host`, and
production runs no Ollama (`health/services` → `ollama: not reachable`, optional). So "deploy succeeded"
+ "health ok" ≠ "the product works". The unblock is: log in (the first login creates user + personal
workspace + admin membership + prompt row, `api/routes/auth.py:119-126`), then create the LLM config in
Configuración with a key from the AI Studio or nan.builders console — the VM's `STORICO_GOOGLE_API_KEY`
does **not** serve extraction (`infrastructure/tasks/extraction_task.py:241-247` refuses a workspace
without its own credential; that env key feeds embeddings only).

**Archive: done by hand, with the gap declared.** `openspec` is not installed here and is not a project
dependency (`npx --no-install openspec` → "could not determine executable to run"), so `openspec archive`
could not run. Both deltas were pure `## ADDED Requirements` for capabilities absent from the store, which
made the sync mechanical: created `openspec/specs/extraction-versioning/spec.md` (8 reqs / 23 scenarios)
and `openspec/specs/task-invalidation/spec.md` (6 reqs / 13 scenarios), each **diff-verified byte-identical
to its delta modulo the header**, then moved the change to
`openspec/changes/archive/2026-09-30-extraction-versioning-schema/` with an `archive-report.md` that states
the method and names the one check that never ran: **`openspec validate`**. The structure was checked
against the repo's own precedent (`2026-09-14-few-shot-qdrant`: same header shape, `ADDED` → `Requirements`,
`> **Change**` line dropped).

**A spec bug the archive almost froze in place.** While checking what I was about to promote to the store,
I found the delta still said `marked_by` **and** `revoked_by` are `ON DELETE SET NULL` with a scenario
asserting "`revoked_by` is null" — written before task 4.4, and never updated when the owner chose
`RESTRICT`. Archiving as-is would have made the contradicted text permanent and normative. Fixed in the
delta first ("Actor References Survive Account Deletion": `marked_by` `SET NULL`, `revoked_by` `RESTRICT`,
deleting the revoking user is **refused**), with `> [Superseded]` notes left under the original `SET NULL`
wording in `design.md` and `proposal.md` — planning artifacts keep their history, the spec keeps the truth.

**Also corrected while writing closure:** the earlier claim that production `provider = 'Nan'` was a
stringified `NaN` was wrong. It is a legitimate custom provider: `custom_providers` (a feature since
revision `0021`) has one row whose `name` md5 equals md5('Nan'), referenced by exactly one
`workspace_llm_configs` row with a real encrypted key, `api.nan.builders`, `qwen3.8-flash`. Second
self-correction of the same class in this session, after "temperature is recoverable". The rule that came
out of both: **do not call production data broken until you have read the place that creates it** — and do
not let a decision that destroys rows depend on my reading numbers off a terminal, which is why the purge
went behind an in-memory count interlock instead.

**And a third wrong claim of mine, committed and then corrected inside the same hour.** In the closure
commit I edited slice (b)'s spec-phase note to say that because (a) was now archived, (b)'s deltas for
`extraction-versioning` and `task-invalidation` had to become `MODIFIED Requirements`, full text, header
verbatim. It read convincingly and it was false: `MODIFIED` requires a stored header to modify, and
(b)'s 7 + 4 requirements **collide with none of** the 8 + 6 the store holds — they are new obligations on
capabilities that exist, which is exactly what `ADDED Requirements` means. (c) is the same shape. I wrote
that sentence from the tool's vocabulary instead of from the files, and the only reason it got caught is
that I went to check the collision count for a different reason. It is retracted in place in
`extraction-versioning-api/proposal.md`, with the numbers, and the check surfaced something the assumption
would have hidden: two of (b)'s API-layer requirements restate (a)'s storage invariants in other words
(`Revoking Updates the Row and Never Deletes It` vs `Revoking Is an Update, Never a Delete`), so the store
will hold the same rule twice at two layers once (b) archives — recorded as an authoring note for (b),
not silently accepted and not "fixed" by editing requirements that are correct where they stand.

**What was left undone at the time, and is now closed.** `make bump` sat in this list as a deliberate
non-action while the version question was the owner's; on the owner's instruction it ran the same day —
`fb25478` + tag `v0.9.0`, deploy `36747695497` `success`, health reports `0.9.0`, `alembic_version` still
`0028`. Slice (b)
`extraction-versioning-api` and slice (c) `extraction-versioning-prompt` are **not authorized** and each
needs its own apply authorization; (b) carries **D-a-1**, **D-a-4** and the retirement of
`POST /api/v1/tasks/`. The Qdrant dev/prod cluster-sharing design decision is still open. The published
commits `7e3aa6e` / `d4fea8b` still carry the withdrawn `'Nan'` claim in their messages — rewriting
published history is the owner's call.

## Where the production scaffolding lives — read this before re-deriving anything

The probes and the purge used to close D-a-3 were **one-off scripts, never repository code**: they speak
to Neon and Qdrant Cloud directly, with the DSN from `~/Developer/storico/.env.prod.local`, run as
`conda run -n storico python <script>.py`. They were copied out of `/tmp` to **`~/storico-ops/`** on
2026-09-30, with a `README.md` there classifying them by risk (🔴 mutates production / 🟢 read-only /
🟡 touches decrypted material in memory).

They are deliberately **not under version control**, and they embed no secrets — all read `os.environ`.

Two things worth knowing before touching them, from that README:

- **`d_a_3_purge.py` is not re-runnable as-is.** Its interlock pins `EXPECTED_ALEMBIC = "0027"` and
  production is at `0028`, so today it refuses itself. That is the interlock working, not a bug: any
  future purge needs a freshly measured `EXPECTED_*` block, never an inherited one.
- **The pattern to steal is the interlock, not the script.** A destructive run executes behind a
  re-measurement that aborts if reality moved — not behind my reading from an hour ago. This session was
  wrong twice about production data (`provider = 'Nan'`, and which store held the D-a-3 counts); the
  interlock is what kept both errors non-destructive.

If `~/storico-ops/` is gone (new machine, wiped home), the *procedure* is still reproducible from
`prod.todo.md` — inventory, runbook, executed steps, and the verification checklist — and the scripts are
regenerable from it in a few minutes. Nothing in the repo depends on their existence.

## Slice (b) apply — session 2026-09-30 (b1): WU1 authorized

**The owner authorized apply of `extraction-versioning-api`, starting with WU1**, and confirmed the SDD
session preflight on the slice (a) defaults: execution `auto`, artifact store `openspec`, delivery
`ask-on-risk`, review budget `400` lines. Strict TDD stays active (`openspec/config.yaml`).

### The repo was not where I left it, and it was not my doing

Between my first read-only pass and the owner's "continua", **another session worked in this checkout**
(measured from `git reflog` and file mtimes, not inferred):

| Local time | Event |
| --- | --- |
| 11:33 | this session starts; `main @ a809428`, clean tree |
| 12:33–12:45 | another session creates `chore/dev-reset-0028` from `a809428`, three docs commits, one amended |
| 13:00 | `.claude/skills/` appears (local copies of the neon skills) |
| 13:37 | checkout still mounted on that branch, never pushed |

The dev-reset branch was **docs-only** (+349: `odd/tasks/dev-reset-0028.md` 272, `docs/deployment.md` +69,
`AGENTS.md` +4, `odd/tasks/board-debt-closure.md` +5), zero `backend/**`, so it could not deploy or break
CI. On the owner's choice it was merged into `main` with `--ff-only` before the feature branch opened,
keeping one line of history; `main` is now `241cd55`, **ahead 3 of `origin/main` and unpushed** — push is
the owner's call. `feat/extraction-versioning-api-wu1` branches from `241cd55`.

Two untracked files are **not mine and stay uncommitted**: `backend/.gitignore` (31 B, ignores `.atl/` —
Pi runtime state) and `.claude/skills/` (not gitignored). Never `git add -A` in this worktree without
looking.

### Gates consumed before the first write

- Native `gentle-ai sdd-status extraction-versioning-api --contract gentle-ai.sdd-status/v2`:
  `nextRecommended: apply`, `applyState: ready`, `dependencies` proposal/specs/design/tasks `all_done`,
  `apply/verify/archive: ready`, `taskProgress` 0/77, `blockedReasons: []`, `notes: []`,
  `actionContext` mode `repo-local`, workspaceRoot = allowedEditRoots = `/Users/alvaldes/Developer/storico`.
- **Review Workload Guard**: the slice forecast says `400-line budget risk: High`,
  `Chained PRs recommended: Yes`, `Decision needed before apply: Yes`. That is the *whole slice* (77 tasks,
  ≈4,400–5,700 lines). This run is **WU1 only**, which `tasks.md` itself estimates at ≈260–340 lines and
  ships whole, and the delivery decision accepted on 2026-09-28 is recorded in the same file (`size:exception`
  is accepted for WU2 and WU4 **and for no other unit**). `ask-on-risk` therefore has nothing to ask here.
- **Model routing drift, reported not fixed**: `.pi/gentle-ai/models.json` (written 2026-09-14) pins every
  SDD phase to `nan/deepseek-v4-flash`, while the installed `~/.pi/agent/agents/sdd-apply.md`
  (written 2026-09-28) carries `model: nan/glm5.3-flash`, `thinking: high`. The launch resolves through the
  installed definition; no ad-hoc model was passed, per the phase model gate.

### WU1 execution plan (the two 410 retirements)

`tasks.md` Phase 1, tasks **1.1–1.8**, commit `refactor(api): retire manual task creation and single-task
deletion with 410 Gone`. Two sequential writers, because the lesson that held in slice (a) is that tranches
of 2–4 files survive the provider and bigger ones die on 429:

| Tranche | Tasks | Allowed edit surfaces |
| --- | --- | --- |
| A — backend | 1.1, 1.2 (RED), 1.3, 1.4 (GREEN), 1.6 (TRIANGULATE), 1.7 (REFACTOR) | `backend/tests/test_api/test_tasks.py`, `backend/src/storico/api/routes/tasks.py`, `backend/src/storico/api/schemas/task.py`, `backend/src/storico/api/error_codes.py` |
| B — frontend mirror | 1.5 (GREEN), 1.8 (REFACTOR) | `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`, `frontend/src/lib/__tests__/error-codes.test.ts` |

Writers do not commit. The parent runs both suites, counts the diff, and lands one work-unit commit for WU1.
Runners: `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`,
then `cd frontend && pnpm test src/lib/__tests__/error-codes.test.ts src/i18n/__tests__/neutral-spanish.test.ts src/i18n/__tests__/no-duplicate-keys.test.ts`.

- [x] b1-1. Gates closed (preflight, native status, workload guard, model drift reported).
- [x] b1-2. Docs branch merged to `main` (`--ff-only` → `241cd55`), `feat/extraction-versioning-api-wu1` opened.
- [x] b1-3. This section written before the first source write.
- [x] b1-4. Tranche A (backend, tasks 1.1–1.4, 1.6, 1.7) green.
- [x] b1-5. Tranche B (frontend mirror, tasks 1.5, 1.8) green.
- [x] b1-6. Full verification: `tests/test_api` unit suite + the three frontend test files, line count under 400.
- [x] b1-7. WU1 work-unit commit on the branch.
- [x] b1-8. `tasks.md` checkboxes and `apply-progress.md` reconciled, handoff updated.

### WU1 closure evidence (measured by the parent, not reported by the writers)

| Check | Result |
| --- | --- |
| Commits | **`e4be843`** `refactor(api): retire manual task creation and single-task deletion with 410 Gone` (code + SDD artifacts) and **`58720db`** `docs(odd): …` (this document). Branch `feat/extraction-versioning-api-wu1` from `241cd55`. |
| Changed lines of code | **357** (213+/144−): backend 346 (205+/141−) + frontend 11 (8+/3−). Inside the 400 budget, **no `size:exception` used**. The PR also carries 16 checkbox lines and a 182-line `apply-progress.md`, which are process records, not review material. |
| Backend suite | `conda run -n storico python -m pytest -m "not integration"` → **1051 passed, 33 deselected**. Focused `tests/test_api` + `tests/contract` → 394 passed. Baseline before WU1 was 1049 passed / 33 skipped over the same 1084 collected, so nothing regressed and two net cases were added. |
| Frontend suite | `pnpm test` → **606 passed in 54 files**, including `neutral-spanish` and `no-duplicate-keys`. |
| Hard greps | zero `repo.delete(` in `routes/tasks.py`; zero `CreateTaskRequest` anywhere in `src/`; zero `path:path` catch-all; both new codes sorted at `error_codes.py:45-46`. |
| Native status after | `gentle-ai.sdd-status@2` → **8/77 complete**, `next: apply`, `apply: ready`, `blockedReasons: []`. |
| RDD | `gentle-ai review mode status` → **off (clone_local)**: the switch was read, not skipped, and ordinary repository policy decided delivery. |
| Delivered | Pushed and opened as **PR #31** → https://github.com/alvaldes/storico/pull/31 (base `main` `241cd55`, head `21fb611`). CI **green**: backend `1066 passed, 18 skipped` in 1m32s, frontend `606 passed` + `tsc --noEmit` clean + Astro build in 1m18s, Vercel preview deployed. The 15 integration cases that cannot run on this machine (1051 local vs 1066 CI) passed in CI, the same delta slice (a) showed. |
| PR shape | 12 files, 499+/152− total, of which **357 lines are code** and **294 are process artifacts** (`apply-progress.md` 182, this document 96, `tasks.md` 16). The repo has no PR template, no issue-linkage gate and no `type:*` label gate — the `branch-pr` skill's checks belong to a different repo, and #23–#30 ship label-less with no `Closes #N`. |
| Not yet in production | Merging is the owner's call and it **deploys**: `deploy-backend.yml` matches `main` + `backend/**`, so the maintenance window (stop → `alembic upgrade head` → start) runs. WU1 adds no migration, so the upgrade is a no-op and the only cost is the window. |

### The push hung, and the cause is not mine to guess at

`git push` produced no output and no result three times under this harness's shell. `GIT_TRACE=1` named it: git ran
`git credential-osxkeychain get` and that process **blocked forever** waiting for a keychain authorization a
non-GUI shell cannot answer. Reads are unaffected because the repository is public, so `ls-remote` succeeds and
the failure looks like a network problem until you trace it.

Two things about the fix are worth keeping, because both were wrong the first time:

- `GIT_ASKPASS=…` alone does **not** bypass the helper. `credential.helper` is a multivar, so
  `-c credential.helper='!gh auth git-credential'` **appends** to the chain and `osxkeychain` still runs first
  and still hangs. The value that clears the chain is an empty one: `-c credential.helper=`.
- With the chain cleared, `GIT_ASKPASS` supplying `alvaldes` + `gh auth token` pushes fine, and the token never
  reaches `argv` or the remote URL. The askpass script is a `/tmp` throwaway that calls `gh` at runtime; nothing
  was written to `~/.gitconfig`, and the user's own interactive pushes keep working exactly as before.

**Two deviations recorded, both accepted:** the handlers are annotated `-> None` because FastAPI rejects `-> NoReturn` as a response field (same shape as the repo's own 410 precedents); and deleting `CreateTaskRequest` mechanically required two companion edits outside the declared four-file surface — `api/schemas/__init__.py` (its re-export) and `tests/contract/test_api_schemas.py` (the case importing it). The writer disclosed both before I measured them; widening a surface is not mine to overlook.

**D-a-5 is half closed, and not in production yet.** Item 1 (the `POST /api/v1/tasks/` contract that advertised `201` and answered 500) is fixed on the branch; it reaches users only at merge → deploy. Item 2 (reads without a current-version predicate) waits for **WU3**.

### Still open inside slice (b), named so nobody rediscovers them mid-PR

1. **D-a-4 and D-a-1 have no task IDs and no line estimate.** `tasks.md` says to assign them when apply is
   authorized; the owner chose WU1 first, so they land before **WU5** (marks backend), where D-a-4 stops
   being latent. Until they are numbered they are outside the 77 and outside the forecast.
2. **D-a-5 closes only at WU1 + WU3.** WU1 kills the `POST /api/v1/tasks/` lie; WU3 adds the
   current-version predicate. Between them, production still shows both runs' task sets to anyone who
   re-extracts.
3. **`openspec validate` has still never run** — the manual archive of slice (a) keeps its declared gap.
4. **Production cannot extract** until the owner re-creates the LLM config; his call, not a task of mine.
5. **Qdrant dev writes against the production cluster** — design debt, unassigned.

## Slice (b) WU3 — session 2026-09-30 (b3): the reads, one PR over budget by owner decision

**What the owner decided.** Asked with the three real options on the table — split into the two PRs the plan
names, run as one PR under a new `size:exception`, or merge #31/#32 first — the owner chose **one PR with a new
`size:exception` for WU3**. That acceptance is written into `tasks.md` itself: the `text` block line is amended
in place with its date and scope, and the "WU3, WU5 and WU6 do NOT carry the exception" bullet keeps its
original wording with a quoted `[Amended 2026-09-30, WU3 only]` note under it. WU5 and WU6 are **unchanged**; an
exception granted for one unit is not a policy for the slice.

**Gates.** Fresh native status: `nextRecommended: apply`, `apply: ready`, **19/77**, `blockedReasons: []`.
Branch `feat/extraction-versioning-api-wu3` stacked on WU2's head `ad93979`. Preflight unchanged (`auto` /
`openspec` / `ask-on-risk` / 400), STRICT TDD active.

**Why WU3 is the one that matters for the thesis evaluation.** It closes **D-a-5 item 2**: today
`task_repository.list_by_story` / `list_by_workspace` and `routes/export.py` have no current-version predicate,
so two `completed` runs on one story show **both runs' task sets** in the board, story detail and export. It also
closes the `frozen` seam WU2 left: the selector read arrives, so the page can compute `is_current` for real
instead of passing `false`.

**The correctness rule this unit turns on** (from design settlement 5, and the reason a Python post-filter is
not an option): the current-version predicate must be joined to the **same `scope` variable** the page and its
fallback `count_stmt` share. Filter in Python after pagination and `total` keeps counting superseded rows: the
board truncates silently while the counter lies, and the past-the-end page returns a total that does not match
its own items.

### Tranches (backend only — Phase 6 owns the frontend consumers)

| Tranche | Tasks | Surfaces |
| --- | --- | --- |
| W3-T1 task repository | 3.1 RED, 3.3+3.4 GREEN, 3.12 | `domain/ports/task_repository.py`, `infrastructure/database/repositories/task_repository.py`, `tests/test_repositories/test_task_repo.py` |
| W3-T2 version reads | 3.2 RED, 3.5 GREEN | `domain/ports/extraction_repository.py`, `infrastructure/database/repositories/extraction_repository.py`, `tests/test_repositories/test_extraction_repo.py` |
| W3-T3 routes + export | 3.6, 3.7, 3.11 | `api/routes/tasks.py`, `api/routes/export.py`, `tests/test_api/test_tasks.py`, `tests/test_api/test_export.py` |
| W3-T4 selector | 3.8 (`StoryVersionResponse`), 3.9, stories half of 3.10 | `api/schemas/story.py`, `api/routes/stories.py`, `tests/test_api/test_stories.py` |
| W3-T5 scalars | 3.8 (extraction scalars), rest of 3.10 | `api/schemas/extraction.py`, `tests/test_api/test_unfiltered_list_queries.py` + whatever pins `ExtractionResponse` |
| Parent | 3.12 REFACTOR rerun, full suites, one WU3 commit | — |

Runner: `cd backend && conda run -n storico python -m pytest <target> -m "not integration"`.

- [x] b3-1. W3-T1: current-version predicate in the task repository, filtered `total` proven.
- [x] b3-2. W3-T2: `list_versions` unbounded, `find_current_version` agrees with it.
- [x] b3-3. W3-T3: `extraction_id` read arm + refusals, export on the filtered statement.
- [x] b3-4. W3-T4: `GET /stories/{id}/versions` with the unchanged access walk, bare array.
- [x] b3-5. W3-T5: the 3.10 triangulation across the three read surfaces (the response scalars named
      here were actually delivered by W3-T4, which took both halves of task 3.8).
- [x] b3-6. 3.12 REFACTOR + full backend suite and ruff, measured by the parent.
- [x] b3-7. One WU3 commit + PR under the accepted exception, with the production/test split stated.
- [x] b3-8. `tasks.md` + `apply-progress.md` + this handoff reconciled.

## Slice (b) WU2 — session 2026-09-30 (b2): the field matrix, stacked on WU1

**Base decision.** WU1 is `OPEN` as PR #31 and the owner has not merged it. "sigamos" was read as
*continue implementing*, never as *merge*: merging deploys. So WU2 branches from WU1's head
(`feat/extraction-versioning-api-wu2` off `5290954`) and its PR targets the WU1 branch —
`feature-branch-chain`, the same move this repo already made when #27 became #28 and got re-targeted to
`main`. When #31 merges, the WU2 PR re-targets to `main`; nothing is rewritten and WU1 stays decidable on
its own.

**Gates.** Fresh native status before the run: `next: apply`, `apply: ready`, **8/77**, `blockedReasons: []`.
Preflight unchanged for the session (`auto` / `openspec` / `ask-on-risk` / 400). WU2 is one of the two units
the owner accepted over budget on 2026-09-28, so this run carries **`size:exception`** for WU2 and for no
other unit: forecast ≈420–520 lines, and it is atomic because the schema shrink and the client have to land
together or every editor save 422s.

**The seam the plan left implicit, resolved before any writer met it.** `design.md:625` defines `frozen` as
"a prop the page computes from the selector's `is_current`" — and the selector is **WU3**. In WU2 the page has
no such read, and `TaskResponse` carries no `extraction_id` (WU3 adds the response scalars). Two ways to carry
that: default the prop to `false` and let no caller set it, or require it and pass `false` explicitly at the
call site with WU3 named in the comment. Chosen: **required prop, explicit `false`**, because a defaulted prop
nobody sets is how a real product rule becomes dead code that nobody deletes. Consequence, stated rather than
buried: between WU2 and WU3 the client is permissive about dependency edits on non-current versions and the
**server is the authority** — such an edit answers 409 `TASK_VERSION_FROZEN`, which is exactly why task 2.8's
locale copy belongs in this unit and not in WU3. WU3 closes the loop by filtering reads to the current version
and computing `frozen` for real.

### Tranches (one commit at the end, because the unit is atomic)

| Tranche | Tasks | Surfaces |
| --- | --- | --- |
| T1 — backend matrix | 2.1 RED, 2.2–2.4 GREEN, 2.5 TRIANGULATE | `api/schemas/task.py`, `api/routes/tasks.py`, `api/error_codes.py`, `tests/test_api/test_tasks.py` |
| T2a — frontend RED | 2.6, the frozen edge of 2.9 | `lib/__tests__/tasks-api.test.ts`, `components/react/__tests__/TaskEditor.test.tsx` |
| T2b — editor + client | 2.7, 2.9 | `lib/tasks-api.ts`, `components/react/TaskEditor.tsx`, `components/react/StoryDetail.tsx` |
| T3 — locale mirror | 2.8 | `i18n/en.json`, `i18n/es.json`, `lib/__tests__/error-codes.test.ts` |
| Parent | 2.10, 2.11 REFACTOR reruns, full suites, the single WU2 commit | — |

Runners per unit: `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`
and `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/lib/__tests__/tasks-api.test.ts`.

- [x] b2-1. T1 backend matrix green (2.1–2.5).
- [x] b2-2. T2a frontend RED cases land (2.6).
- [x] b2-3. T2b editor + client GREEN (2.7, 2.9).
- [x] b2-4. T3 locale mirror and registry count 38 → 39 (2.8).
- [x] b2-5. REFACTOR reruns 2.10/2.11 + full backend and frontend suites, measured by the parent.
- [x] b2-6. One WU2 commit (atomic by design), PR stacked on the WU1 branch.
- [x] b2-7. `tasks.md` + `apply-progress.md` + this handoff reconciled; the `frozen` seam recorded where the
  next reader will find it (PR body and `apply-progress.md`, not only here).

### Delivered, and the exception was widened by the owner before the push

**PR #32** → https://github.com/alvaldes/storico/pull/32 — base `feat/extraction-versioning-api-wu1`, head
`62d780d`, `MERGEABLE` / `mergeStateStatus: CLEAN`. Commits: **`bf12197`** `feat(tasks): enforce the D5/D21 field
matrix and stop the editor sending removed fields` and **`62d780d`** `docs(odd): record the WU2 tranches and the
four plan premises they corrected`.

The 918-vs-≈420–520 overrun was put in front of the owner **before** pushing, with the production/test split, and
ratified: the `size:exception` for WU2 now stands at 918. Nothing was trimmed to meet a number, and the unit was
not split, because a backend-only half 422s every editor save.

| Check | Result |
| --- | --- |
| PR shape | 16 files, **1716** changed lines: **918 code+tests** (210 production / 708 tests) and **798 process artifacts** (`apply-progress.md` 651, this document, `tasks.md` checkboxes) |
| CI backend | **1081 passed, 18 skipped** in 1m43s — 1099 collected, against WU1's 1084, so the 15 new cases ran and the integration half passed where it can actually run |
| CI frontend | `pass` in 1m15s, Vercel preview deployed |
| Reading guide published | the PR names the five files that hold the contract and calls the two big test files evidence for them, so the reviewer is not asked to read 798 lines of process noise as if it were code |

### What the tranches actually found, because the plan got four premises wrong

1. **T1's guard cost what the design said it would cost — and the design contradicted itself.**
   `design.md:152` sketches the `find_current_version` lookup **unconditionally**, while its Tradeoff
   paragraph prices it as "one extra statement **before a dependency write**, against a pooler where a
   statement is ~2s" and its Why paragraph names the save that must stay fast: the board's
   `{"status": …}`. Unconditional makes the most common write in the product pay ~2s for a verdict it never
   reads. Implemented presence-guarded (T1b), behaviourally identical, with a **call-count** case that fails
   if anyone re-widens it. Not a re-decision of D5/D21 — the placement detail that the design's own cost
   sentence already chose.
2. **Task 2.7 asks to remove a `priority` control that does not exist.** The editor never had one; T2a found
   it and T2b declared it. The case `no priority control at all (D21)` is a **regression guard**, not new
   behaviour, and `priority` stays in `TaskResponse` and the JSON export as designed.
3. **T2b opened a type hole to keep tests compiling, and the parent closed it (T2c).**
   `TaskUpdateFields` grew `& Record<string, unknown>` so a stale test literal and the store's
   `Partial<Task>` forward would typecheck. Its effect: `updateTask(id, { title: 'x' })` compiles, the key is
   dropped at runtime, and nobody hears anything — the exact lie WU2 exists to kill, moved from the wire to
   the type system. Strict type restored; the narrowing lives as an explicit presence-preserving pick in
   `taskStore.ts`; the case that must pass a forbidden literal does it through a test-local cast, so breaking
   the contract is a deliberate, greppable act instead of an accident waiting to happen.
4. **Task 2.8's "both locale counts 43 → 44" is stale arithmetic.** The per-locale expectation is **derived**
   (`EXPECTED_REGISTRY_COUNT + ROUTE_ERROR_CODES.length`), so one constant moves. The plan's sentence would
   have invited a second fake constant.

Two smaller things worth keeping: T2a caught its own frozen case **passing for the wrong reason** (the
fixture task already had its only sibling as a dependency, so the select was disabled anyway) and reworked it
before accepting the RED — a test that passes vacuously pins nothing. And `title_required` was deleted from
both locales after grepping it to zero references: copy for a validation that can no longer fire is a UI lie.

### The number the accepted exception was priced against

**WU2 is 918 changed lines**: 210 production + 708 tests, against the ≈420–520 forecast the owner accepted
`size:exception` with. Surfaced before publishing, not after. The unit is still atomic and the tests are the
reason the contract is observable, so the honest options are a widened exception or keeping it as one over-
large review — decided below, not assumed here.


### WU3 execution log (b3) — five tranches, one dead writer resumed, one forecast that was wrong

**Tranches actually run**, each verified by the parent before the next started:

| Tranche | Tasks | Measured gate after it |
| --- | --- | --- |
| W3-T1 | 3.1, 3.3, 3.4 | `tests/test_api tests/test_repositories` **491 passed** |
| W3-T2 | 3.2, 3.5 | full unit suite **1074 passed, 33 deselected** |
| W3-T3 | 3.6, 3.7, 3.11 | full unit suite **1082 passed** (= 1074 + 8 new cases) |
| W3-T4 | 3.8, 3.9 | full unit suite **1084 passed** (= 1082 + 2) |
| W3-T5 | 3.10, 3.12 | full unit suite **1089 passed** (= 1084 + 5); ruff check + format clean; frontend **615**, `tsc --noEmit` exit 0 (run anyway: W3-T4 widened responses the frontend consumes) |

**A writer died mid-run and was resumed, not relaunched.** W3-T1 errored at turn 35 with
`assistant reported an error` — after implementing the predicate, not before. Reading the task log
(`~/.pi/agent/gentle-agents/tasks/<id>.json`) showed the real state: it had finished the work, run
ruff, and was writing its report when the provider failed. `subagent_continue` on the same session
kept 35 turns of context that a fresh launch would have had to rediscover. The failure mode to
remember: **`Subagent execution failed` with no detail is not "nothing happened"** — check the
worktree and the log before re-dispatching, or you pay for the same work twice and lose the child's
diagnosis.

**The 11 red tests were a fixture lie, not a regression.** After W3-T1, `tests/test_api` +
`tests/test_repositories` read 11 failed / 480 passed. Cause: `seed_task` minted its own extraction
through `seed_extraction`, which defaults `status = PENDING` (`domain/entities/extraction.py:32`), so
tasks were born attached to runs that no current-version read can see. The child refused to edit
files outside its declared surfaces and reported instead; that restraint was correct and the parent
then authorized the reconciliation explicitly. Fix: one place — `seed_task` now mints a `COMPLETED`
extraction — with `seed_extraction`'s default **left alone** because tests that deliberately want a
pending/failed run mint it themselves. **Zero assertions were removed** (`git diff | grep '^-' |
grep -c assert` = 0 on both affected test files): the suite went green by making fixtures describe a
state the domain actually allows, not by weakening what's checked.

**Two premises of mine were wrong and the children caught both.**
1. I told W3-T2 "W3-T1 left the suite at 1080". That number was never measured — it was my
   projection. Reality: 1066 (WU2 head) + 6 (T1) + 2 (T2) = **1074**. The child disputed it instead of
   absorbing it, which is the behaviour I want, and `apply-progress.md` now records that the bad
   number was the parent's. **A parent quotes a number it ran, or says "unmeasured."**
2. I told W3-T4 that `ExtractionResponse` "builds from the entity, so adding fields is enough".
   All four extraction reads hand-build the schema (`routes/extraction.py:268/:304`,
   `routes/extractions.py:143/:182`), so widening it with required fields forced companion edits at
   every construction site — one of them (`routes/extractions.py`) outside the declared surfaces. The
   child ran the suite between the schema widening and the route edits, got a real 17-failure RED,
   and used it as the proof that the companions were **forced, not stylistic**. Required
   non-defaulted Pydantic fields are a mechanical companion detector; the OpenAPI surface was then
   verified live (11 properties on `StoryVersionResponse`, three scalars required on both widened
   schemas).

**3.12 left deliberate dead code, and it is an owner decision, not a cleanup.** After the export
swap, `TaskRepository.list_by_workspace` has **zero production callers** (grep-verified; the
`list_by_workspace` still live in `export.py:120` belongs to the **story** repo). 3.12's letter says
report and leave in place, so it stays. Deleting a public repository method is not a refactor an
agent takes silently.

**The workload was 1,244 lines, not the 600–750 the exception was granted on.** Production 331,
tests 913. Measured before committing, surfaced with the plan's own split (selector+scalars 344,
predicate+`extraction_id`+export 900 — a chain, not siblings, because the selector needs
`list_versions`), and put to the owner as a real choice. **The owner ratified one PR of 1,244**, so
the accepted number in this file and in `tasks.md` is now the measured one, not the forecast.

- Closed: b3-1 … b3-6 above, each with the gate number recorded in the table; b3-7 and b3-8 are the
  last two items of that same list, completed with the ratified 1,244-line single PR (#33) and this
  reconciled handoff. (These ids were briefly duplicated here as a second checklist with contradictory
  state; the plan section is the single owner of b3 ids.)

## Slice (b) WU4 — session 2026-09-30 (b4): the gate and the sanctioned deletion

**Gates.** Fresh native status: `nextRecommended: apply`, `applyState: ready`, **31/77**,
`blockedReasons: []`. Branch `feat/extraction-versioning-api-wu4` stacked on WU3's pushed head
`4404d4b` (so the chain is now #31 → #32 → #33 → this one: four open PRs, a cost of the owner's
"sigue" over "merge first" — restated at delivery). `size:exception` for WU4 was accepted on
2026-09-28 with the plan's own estimate **≈1,300–1,700 lines**; W3's lesson applies: measure before
publishing and restate the accepted size against reality if it drifts, don't let the 2026-09-28
number silently cover whatever shows up.

**What WU4 is.** The owner/admin gate on version-mutating calls (extract, mark, unmark, story
delete) plus the sanctioned story deletion, which is the first **destructive** endpoint in the API and
the first slice-(b) unit that adds a migration (`0029`). Migration `0029` is **additive** — creating
`story_deletions` — so unlike `0028` it needs no empty-database guard (tasks.md 4.10 states this), and
the production/dev purge to `0028` does not block it.

**Three premises of the plan, checked against the repo before dispatching (2026-09-30):**

1. **Task 4.6 is already half done, by WU3.** 4.6 asks for the gate swap *and* "`version_number` to the
   202 `ExtractResponse`". W3-T4 added exactly that (`routes/extraction.py:277` passes
   `version_number=pending.version_number`, measured in the WU3 diff). So 4.6 shrinks to
   `get_workspace_for_user` → `require_owner_or_admin`. Checked 4.6 only when the swap is real; the
   scalar must not be re-added.
2. **Task 4.14's "both locale counts 44 → 47" is not an edit.** `error-codes.test.ts:125` *derives* the
   per-locale expectation as `EXPECTED_REGISTRY_COUNT + ROUTE_ERROR_CODES.length` (39+5=44 today, 42+5=47
   after). Only `EXPECTED_REGISTRY_COUNT` moves. This is the same class of stale arithmetic as WU2's task
   2.8 ("43 → 44"), so the rule now has two instances: **the mirror test has one knob, not three.**
3. **CI does have Docker, so 4.16 and 4.17 are not orphaned.** Locally the unit suite deselects 33
   integration cases and this machine has no Docker/`psql`. CI's backend job reports **1104 passed, 18
   skipped**, and the arithmetic identifies the 18 exactly: 16 `test_few_shot_rag_qdrant` + 2
   `test_ollama_chat_live` (the only cases gated on services CI lacks). The other 15 — 12
   `test_extraction_versioning_schema` + 2 `test_migration_chain` + 1 `test_projects_integration` —
   are `_needs_docker`-gated testcontainers cases that **ran and passed**. Consequence for WU4: the
   cascade proof (record survives without a FK to `stories`, actor deletion nulls `deleted_by`) and
   the `0029`-reaches-head + drift-empty proof are obtainable **in CI**, and the PR description must
   say so rather than reporting the local skip as if nothing verified it.

### Tranches

| Tranche | Tasks | Surfaces |
| --- | --- | --- |
| W4-T1 gate primitives | 4.1 RED, 4.5 GREEN | `tests/test_unit/test_workspace_gate.py` (new), `api/dependencies.py`, `api/routes/tasks.py` |
| W4-T2 error vocabulary | 4.7, 4.8 (exception part) | `api/error_codes.py`, `api/errors.py`, `domain/entities/exceptions.py` |
| W4-T3 frontend mirror | 4.14 | `frontend/src/i18n/en.json`, `es.json`, `frontend/src/lib/__tests__/error-codes.test.ts` |
| W4-T4 storage | 4.4 RED, 4.8 (entity), 4.9, 4.10 | `domain/entities/story_deletion.py` (new), `models/story_deletion.py` (new), `models/__init__.py`, `alembic/versions/0029_story_deletions.py` (new), `tests/test_unit/test_story_deletions_migration.py` (new) |
| W4-T5 relational delete | 4.3 (repo half), 4.11 | `domain/ports/user_story_repository.py`, `repositories/user_story_repository.py`, `tests/test_repositories/test_user_story_repo.py` |
| W4-T6 vector cleanup | 4.12 | `domain/ports/vector_store_port.py`, `infrastructure/vector/qdrant_adapter.py` |
| W4-T7 service + endpoint | 4.6, 4.13, 4.2 (stories half), 4.15 | `application/services/story_deletion_service.py` (new), `api/routes/stories.py`, `tests/test_api/test_stories.py` |
| W4-T8 gate on the rest | 4.2 (extraction/tasks halves) | `api/routes/extraction.py`, `tests/test_api/test_extraction.py`, `tests/test_api/test_tasks.py` |
| W4-T9 Postgres proof | 4.16, 4.17 | `tests/test_integration/test_story_deletion_record.py` (new), `tests/test_integration/test_migration_chain.py` |
| Parent | 4.18 REFACTOR, suites, commit, PR | — |

**Known intermediate red, by design:** between W4-T2 and W4-T3 the frontend mirror test is red (three
codes without locale entries). That is disclosed, not hidden, and W4-T3 closes it — the same pattern
WU1 used with its backend/frontend tranches.

> **[Order amended before dispatching, 2026-09-30 — premise #4]** The table above keeps the plan's
> numbering, but W4-T2 runs **first**. Task 4.5's gate raises
> `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`, and that code is created by task 4.7 — so dispatching 4.5
> before 4.7 would force the writer to either invent an error code outside its declared surfaces or
> stub one that the later tranche then has to reconcile. The plan's sequence has a real
> dependency-in-the-wrong-direction here, not a stylistic preference. Execution order:
> **W4-T2 → W4-T3 → W4-T1 → W4-T4 → …** so the error vocabulary exists before the gate needs it, and
> the frontend mirror goes green before anything else can widen the registry again.

**Runner:** `cd backend && conda run -n storico python -m pytest <target> -m "not integration"`.
**Frontend:** `cd frontend && pnpm test` / `pnpm exec tsc --noEmit`.

- [ ] b4-1. W4-T1: `_is_owner_or_admin` truth table + the `resolve_*_access` extraction, walk byte-for-byte unchanged.
- [ ] b4-2. W4-T2: three error codes, two handlers registered by own class, `VectorStoreError`.
- [ ] b4-3. W4-T3: mirror 39 → 42 with neutral Spanish; intermediate red closed.
- [ ] b4-4. W4-T4: `story_deletions` model + `0029` + the no-FK-to-stories pin.
- [ ] b4-5. W4-T5: `delete_with_record` as one transaction, rollback on no-row.
- [ ] b4-6. W4-T6: `delete_by_story` raising `VectorStoreError`, `wait=True`.
- [ ] b4-7. W4-T7: the service ordering (snapshot → cleanup → relational delete) + `DELETE /stories/{id}`.
- [ ] b4-8. W4-T8: the gate on extract/mark/unmark, `PUT /tasks/{id}` deliberately NOT gated.
- [ ] b4-9. W4-T9: the two Postgres-only files that CI will actually run.
- [ ] b4-10. 4.18 REFACTOR + full suites + ruff, measured by the parent.
- [ ] b4-11. One WU4 commit + PR, size restated against the measurement.
- [ ] b4-12. `tasks.md` + `apply-progress.md` + this handoff reconciled.

### WU4 splits into two chained PRs (owner decision, 2026-09-30) — and premise #5 that forced the timing

**What the owner decided.** WU4's accepted band was ≈1,300–1,700 lines. Measured at the W4-T6 close it was
already **1,332** with eight tasks unwritten, projecting **1,900–2,280**. Rather than ratify a widened
exception (what WU3 did), the owner chose to **cut WU4 in two chained PRs on the seam the code already
had**: gate + error vocabulary + mirror, versus migration `0029` + audit record + delete + vector cleanup.
The cost named and accepted: the open-PR chain grows from four to five. The benefit named: **reverting the
deletion must not revert the authorization tier**, and a human reads a destructive migration in its own
sitting.

**Measured halves, not estimated** (`git diff --numstat` after `git add -N`): gate side **627**, deletion
side **891**, i.e. ≈830 and ≈1,100 once their unwritten tests land. Both still above 400; neither is a
"small PR", and the split is about *separation of concerns per sitting*, not about hitting a number.

**A measurement trap the parent hit and must hand on.** `git diff --numstat` **silently excludes untracked
files**, and W4-T4 shipped four brand-new files (`story_deletions` model, entity, revision `0029`, its test).
My first cumulative read was **903**; the true number was **1,332** — a 429-line hole, entirely made of new
files. The fix is `git add -N <paths>` (intent-to-add) before measuring, and `git reset` right after, because
leaving intent-to-add entries in the index means a later plain `git commit` can commit **empty blobs** for
those paths. Sub-agent tranche totals that were summed from `git diff` alone understate any tranche that
creates files, which is most of WU4: the W4-T4 report's "389 changed lines" and my own earlier arithmetic
need re-derivation at close-out from the real head-to-head diff, not from tranche anecdotes.

**Premise #5 — task 4.2 cannot be completed in Phase 4, in either of the two PRs.** 4.2's letter requires
the `MEMBER`-gets-403 gate case on **extract, mark, unmark and story delete**. Reality: `mark`/`unmark`
endpoints do not exist until Phase 5 (WU5, task 5.9 wires `require_task_owner_or_admin`), and `DELETE
/stories/{id}` does not exist until task 4.13. So 4.2's four cases land in **three different units**:
extract with PR A (task 4.6), story delete with PR B (with 4.13), mark/unmark with WU5. Nobody should
expect a checkbox to be tickable at the point the plan puts it, and the earlier warning W4-T1 left —
"the four wrappers are unwired dead code until 4.6/4.13/5.9" — was this same defect, one tranche before
it bit.

## RESUME POINT — end of session 2026-09-30 (b5). WU4 half-committed, nothing pushed

**Where things stand, physically.** Everything from this session is committed on
`feat/extraction-versioning-api-wu4`; the working tree is clean except the two files that are not mine
(`backend/.gitignore`, `.claude/skills/` — untracked, leave them). **Nothing from WU4 has been pushed and
no WU4 PR exists yet.**

| Local commit | Contains | Status |
| --- | --- | --- |
| `d93349f` | gate primitives + error vocabulary + frontend mirror (**PR A**) | committed, **not** independently CI-proven |
| `155b975` | migration `0029` + `story_deletions` + `delete_with_record` + `delete_by_story` (**PR B**) | committed, depends on A |
| `4d4b8d2` | the ODD record of the split and the measurement trap | docs |

Measured at this head: backend **1120 passed / 33 deselected**, ruff check and format clean (259 files).
WU4 progress in the plan: Phase 4 has **4.1, 4.4, 4.5, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.14** checked;
**4.2, 4.3, 4.6, 4.13, 4.15, 4.16, 4.17, 4.18 are open**. Slice (b) overall: **41/77**.

**Open PRs from earlier units, all green, none merged:** #31 (WU1) → #32 (WU2) → #33 (WU3). The chain is
three deep and WU4 will make it five unless the owner merges. Production is still at `0028` and still
**cannot extract**: the LLM config must be recreated in Configuración (D-a-6).

### What to do tomorrow, in order

1. **Confirm the split commits still stand.** `git log --oneline -4` on `feat/extraction-versioning-api-wu4`
   and `git status --porcelain`. Then decide, at the seam of `d93349f`: PR A branches from WU3's head
   (`4404d4b`) and carries `d93349f`; PR B branches from A and carries `155b975`. If the owner would rather
   not split after all, the two commits squash cleanly.
2. **Task 4.6 + the extract half of 4.2 (this is PR A's remaining work).** `routes/extraction.py`:
   `Depends(get_workspace_for_user)` → `Depends(require_owner_or_admin)`. The `version_number` on the 202
   body is **already done** by W3-T4 (`routes/extraction.py:277`) — premise #1, do not re-add it. Then the
   `MEMBER` → 403 `WORKSPACE_OWNER_OR_ADMIN_REQUIRED` RED on extract, with no data changed.
3. **Tasks 4.13, 4.3(stories half), 4.15 (PR B's remaining work).** `StoryDeletionService` ordering:
   snapshot `list_versions` → build the record with the destroyed numbers → `delete_by_story` **only if a
   store is configured** → `delete_with_record`. Then `DELETE /api/v1/stories/{story_id}` with
   `require_story_owner_or_admin`. Replace the two `delete_by_story` **no-op stubs** (left deliberately in
   `test_api/test_extraction.py` and `test_services/test_extraction_service.py` by W4-T6) with the
   recording fake that 4.3 needs — that recording behaviour is 4.3's RED, it was not pre-built.
4. **4.2 is not completable in WU4 — premise #5.** Its letter asks for the gate 403 on extract, **mark,
   unmark** and story delete. Mark/unmark endpoints arrive in WU5 (5.9 wires the wrapper) and story delete
   arrives with 4.13. So 4.2 lands in three units. Check it only for what exists, and record the split in
   `tasks.md` the way the WU3 exception was recorded — dated, attributed, with the original text kept.
5. **4.16/4.17 and CI.** Write them; they will **skip locally** (no Docker) but **CI does run them** —
   measured: CI's 18 skips are exactly 16 Qdrant + 2 Ollama, so the testcontainers cases (record-survives-
   cascade, `0029`-reaches-head, drift-empty) genuinely execute there. That is premise #3 and it is the
   difference between "unverified" and "verified somewhere".
6. **Deploy risk if any of this reaches `main`:** the window runs `alembic upgrade head` and `0029` applies
   there. `0029` is additive with no data guard, so it is safe on an empty `0028` database — but the D-a-3
   rule still holds for anything with this shape: **a migration that refuses existing data needs its data
   plan in `prod.todo.md` before it reaches `main`.**

**Numbers the next session should not re-derive:** CI on #33 is `1104 passed, 18 skipped`; WU3 shipped
1,244 lines (331 production / 913 tests) as a single PR under an owner-ratified exception restated against
the measurement; WU4's accepted band is 1,300–1,700 and the split into two PRs was the owner's answer to
projecting past it.

## RESUME POINT — end of session 2026-10-02 (b6). WU4 code-complete in two local branches; nothing pushed

**Where things stand, physically.** WU4's three remaining tranches landed this session and the unit is
code-complete except for task 4.2's mark/unmark half, which belongs to WU5. Everything is committed;
the working tree is clean except the two files that are not mine (`backend/.gitignore`,
`.claude/skills/` — untracked, leave them). **Nothing is pushed and no WU4 PR exists.**

| Branch | Commits | Which PR |
| --- | --- | --- |
| `feat/extraction-versioning-api-wu4a` (from WU3's head `4404d4b`) | `d93349f`, `c9f918c`, `718e52b` | **PR A** — the gate, its error vocabulary and the extract gate |
| `feat/extraction-versioning-api-wu4b` (from A's tip) | `9c7ad48`, `8bdc149`, `a4a2ee9`, `ef962ed` | **PR B** — `0029`, the storage layer, `StoryDeletionService`, the gated delete, the Postgres proofs |

The pre-split branch `feat/extraction-versioning-api-wu4` (`5b3e3d6`) is kept locally as a safety net;
`git diff 5b3e3d6 ef962ed` is exactly the W4-T7/T8/T9 files, so nothing was lost in the rebase.

Measured at `ef962ed`: unit suite **1132 passed / 36 deselected**; ruff check clean and 261 files
formatted; the integration file **skips** (this machine has no Docker daemon). Slice (b): **48/77**.
Phase 4: **17 of 18** — 4.2 stays unchecked on purpose.

**Measured size, and the decision it forces** (full table in `apply-progress.md`,
§`Parent close-out of WU4`): PR A **840** code+test lines (1,391 with plan artifacts), PR B **1,869**
(2,587), WU4 **2,701** (3,970) against an accepted `size:exception` band of **1,300–1,700**. The band
came in over, and the delivery decision says such a unit goes back on the table rather than being
absorbed — so the first item below is a real owner decision, not a formality.

**Deploy risk, for the record:** `0029` is additive with no empty-database guard, so the deploy
window's `alembic upgrade head` applies it safely to the current production schema. The D-a-3 rule
does not bite here.

### What to do next, in order

1. **Owner decision on WU4's measured size.** Either ship the two PRs as they stand with the measured
   numbers stated in their bodies, or split B once more on the storage-vs-HTTP seam (its committed
   storage layer + `StoryDeletionService` vs the route + its API and integration tests). Nothing else
   blocks; the code and its evidence do not change either way.
2. **Push and open the two PRs**, chained per this change's `feature-branch-chain` strategy: PR A
   targets `feat/extraction-versioning-api-wu3` (PR #33's branch), PR B targets PR A's branch. Push
   hangs under `credential-osxkeychain` in a non-GUI shell; the recipe that worked is
   `GIT_ASKPASS=/tmp/storico_askpass.sh GIT_TERMINAL_PROMPT=0 git -c credential.helper= push …`.
3. **Before WU5, number the two carried defects inside slice (b)** — the previous resume's item 6,
   still pending. **D-a-4**: `DELETE /api/v1/users/me` (`api/routes/settings.py:335`) has no
   `IntegrityError` handling, so deleting an account that revoked a mark answers 500 once a revoke
   exists. **D-a-1**: the INSERT-only task persist loop (`infrastructure/tasks/extraction_task.py:441`)
   duplicates task rows if a run is ever re-dispatched. Neither is among the 77 tasks.
4. **WU5 (Phase 5, 5.1–5.13) — the invalidation mark and the repetition read.** It also closes **4.2**:
   the 403 gate on mark/unmark is where `require_task_owner_or_admin` finally gets its caller (it is
   committed, unit-pinned and caller-less on purpose), and 4.2's "a MEMBER still reads the board, moves
   a card, edits `labels`, edits the story's four fields and reads versions" clause needs its API pins.
5. **Owner decisions still open from earlier sessions:** recreate the LLM config in production
   (D-a-6 — without it production cannot extract at all); and decide on the two pieces of dead code
   left in place by explicit decision — `TaskRepository.list_by_workspace` (0 callers) and, new since
   W4-T8, the story port/repository `delete` (0 production callers).

**Numbers the next session should not re-derive:** WU4 = 2,701 code+test lines / 3,970 total; PR A 840,
PR B 1,869; unit suite 1132 passed / 36 deselected / 33 → 36 deselected reconciled to 4.16's three new
integration functions; WU3 shipped 1,244 lines under a ratified exception; CI on #33 is
`1104 passed, 18 skipped`; the WU4 band was 1,300–1,700.

**One trap this session hit and the next should keep:** the DELETE route now depends on
`get_vector_store`, and the suite's autouse Qdrant guard fails any test that reaches the real client —
every delete case must pin the boundary with `app.dependency_overrides[get_vector_store]`. And
`git diff --numstat` still does not see untracked files (that is why W4's first measurement was wrong);
measure with `git add -N` and reset immediately.

### Addendum, same session (2026-10-02) — pushed, PRs opened, CI green, and the one thing CI caught

The owner resolved the two open items above in this same session: **ship the two PRs as they are, with
the measured numbers stated**, and **push and open them**. Both happened.

- **PR #34** — `feat/extraction-versioning-api-wu4a` → `feat/extraction-versioning-api-wu3` — open, **green**
  (backend, frontend and Vercel).
- **PR #35** — `feat/extraction-versioning-api-wu4b` → `feat/extraction-versioning-api-wu4a` — open,
  **green** on head `45e0ccf`, with the measured sizes and the evidence split stated in the body.
- The chain is now five deep: #31 → #32 → #33 → #34 → #35, none merged.

**CI's first look at WU4 caught something no local run could.** The branch had never been pushed, and
the first push turned the backend job red on a *slice (a)* integration test:
`test_downgrade_to_0027_and_back_round_trips_on_a_private_database` pinned `declared_head == "0028"`,
which stopped being true the moment `0029` existed. That file needs a Docker daemon, so neither the
local suite nor any earlier WU4 session could see it. Fixed in `034cebd` by making both pins
head-agnostic (the precondition now asserts a head exists *and* that `0028` is still in the walked
chain; the post-re-apply assertion compares against the declared head) instead of bumping the literal,
which would go stale at the next migration. Then the Postgres half **ran for real**: CI reports
**`1150 passed, 18 skipped`**, which reconciles exactly with the local `1132 passed, 36 deselected`
(18 cases run on the testcontainers runner, 18 skip everywhere). Tasks 4.16 and 4.17 are therefore
verified, not merely CI-owned.

**Consequence for the next session:** everything in this file's items 1 and 2 above is done, and the
deploy question is answered (`0029` is additive — the window applies it with no data plan). What is
left is item 3 onward: number **D-a-4** and **D-a-1** inside slice (b), then **WU5** (Phase 5), which
also closes 4.2 and gives `require_task_owner_or_admin` its caller.

**Item 3 is done too, in the same session — the two defects now carry task IDs.** **D-a-4 → task 5.14**
(the account-delete contract; its 409-vs-pre-check choice is flagged as an owner decision inside the
task) and **D-a-1 → task 5.15**, recorded as an **explicit non-goal** with the measurement behind it:
the only production caller of `run_background_extraction` is `api/routes/extraction.py:264`, once per
extraction the route has just minted, and (b) adds no re-dispatch surface. The slice forecast is
restated as ≈4,500–5,800 to include 5.14; 5.15 adds prose only. **WU5 then starts**, split into two
chained PRs on the axis `tasks.md` already named: entity/port/repository/normalizer first, then the
endpoints and the D16 read.

## RESUME POINT — end of session 2026-10-02 (b7). WU5 and WU6 delivered; the slice is one verification pass from done

**Where things stand, physically.** Every commit is pushed; the working tree is clean except the two
files that are not mine (`backend/.gitignore`, `.claude/skills/`). **Nine PRs are open, chained, green
and none merged**: #31 → #32 → #33 → #34 (WU4-A) → #35 (WU4-B) → #36 (W5-A) → #37 (W5-B) → #38 (WU6-A)
→ #39 (WU6-B) → `main`.

| Branch | Tip | Which PR |
| --- | --- | --- |
| `…-wu4a` / `…-wu4b` | `718e52b` / `ef962ed` | #34 / #35 |
| `…-wu5a` / `…-wu5b` | `c9a9f48` / `de75076` | #36 / #37 |
| `…-wu6a` / `…-wu6b` | `a985f83` / `507d447` | #38 / #39 |

**Plan state: 74/79.** Phase 4 **18/18**, Phase 5 **15/15**, Phase 6 **10/10**. The only work left is
**Phase 7, the slice's verification pass** (7.1–7.5). The count grew from 77 to 79 because this session
gave the two carried defects task IDs (5.14, 5.15).

**Measured at the head** (`507d447`, plus the resume commit): unit layer **1206 passed / 36 deselected**
locally, **1150+ passed / 18 skipped** in CI (the Postgres + Qdrant halves run there); frontend
**665 passed** / 57 files; `tsc --noEmit` clean; `pnpm build` completes; ruff check clean and **269 files**
formatted.

**Sizes, for the next session's forecasting** — the slice's one durable pattern: the plan prices
production code and undercounts the proof. WU3 1,244 (forecast 600–750) · WU4 2,701 (1,300–1,700) · WU5
2,426 (≈800–1,050) · WU6 2,408.

### What this session actually did, in order

1. **WU4** — the extract gate (4.6 + the extract half of 4.2), the sanctioned story deletion (4.13,
   4.3's API half, 4.15) and the Postgres-only record proofs (4.16–4.18), split across two chained PRs
   at the seam of `d93349f`, with the W4-T1..T3 evidence sections moved into the PR whose code they
   document.
2. **The first CI run WU4 ever had went red** on a *slice (a)* integration test that pinned
   `declared_head == "0028"`. Only a Docker-bearing machine could see it, and the branch had never been
   pushed. Fixed head-agnostically (`034cebd`), and the Postgres half then ran green in CI.
3. **The two carried defects got task IDs** before WU5 (D-a-4 → 5.14, D-a-1 → 5.15 as an explicit
   non-goal with the measurement behind it).
4. **WU5** — the mark's entity/port/repository/normalizer (W5-A), the four endpoints and the D16 read
   (W5-B1), D-a-4's designed 409 (W5-B2a), and the mirror plus the closing pass (W5-B2b). Task 4.2 closed
   here.
5. **WU6** — the version selector and the gate mirror (W6-A), then the editor recut, the D16 notice,
   the version-aware read and the remaining copy (W6-B1/B2). Phase 6 closed.
6. **A process hole, found and closed**: splitting the i18n mirror into its own task left the frontend
   suite red twice (615 → 613), because backend tranches never run `pnpm test`. Both mirror moves were
   **folded into the commits that added their codes** with `--fixup` + autosquash, and the intermediate
   commit was verified green as well — so the branch has no red commit.
7. **A real UI gap closed**: the account-delete dialog rendered the raw "Conflict" for the backend's
   designed 409; it now resolves the code through the error-code map.

### What to do next, in order

1. **Phase 7 — the slice's verification pass** (7.1–7.5): the whole backend suite, the whole frontend
   suite, the integration layer, lint/format, and then the honest evidence split written into the
   change's verify report — what the SQLite unit layer proved, what only CI's testcontainers proved,
   and what nothing has proven yet. 7.3 must say plainly that the integration layer is evidenced by CI
   on every PR head and cannot run on this machine (no Docker).
2. **The owner's merge decision.** Nine chained PRs are waiting; none is merged and nothing is in
   production from this session. Merging deploys the `0029` migration — additive, no data plan needed,
   so the D-a-3 rule does not bite. **Production still cannot extract until the LLM config is recreated
   in Configuración (D-a-6)**, which is independent of all of this.
3. **Carried and named, not absorbed**: the account-delete race residual (a revoke landing between
   D-a-4's pre-check and the delete still surfaces as the raw integrity refusal; translating it belongs
   to `UserRepository.delete`), the two pieces of dead code left in place by decision
   (`TaskRepository.list_by_workspace`, the story port/repository `delete`), and a failed
   `GET …/invalidations` on editor open treating a task as unmarked (the server's 409 is the backstop).

**Traps the next session should not re-learn:** backend-only tranches do not run `pnpm test`, so a new
error code must move the i18n mirror **in the same commit**; the gated `DELETE /stories/{id}` route
needs `app.dependency_overrides[get_vector_store]` in every test that reaches it; `git diff --numstat`
cannot see untracked files (measure with `git add -N`, reset immediately); and pushes hang under
`credential-osxkeychain` without
`GIT_ASKPASS=/tmp/storico_askpass.sh GIT_TERMINAL_PROMPT=0 git -c credential.helper= push`.

**Addendum, same session, minutes later — the slice closed.** Phase 7 ran and `tasks.md` now reads
**79/79**: no remaining plan work. The report is
`openspec/changes/extraction-versioning-api/verification.md`, with the evidence split stated honestly
(local `1206 passed, 36 skipped` vs CI `1224 passed, 18 skipped`, and the reconciliation that makes both
numbers meaningful), the 36 local skips attributed by gate — 18 Docker-gated that ran in CI and 18
environment-flag opt-ins that skip everywhere, so nothing in this slice has ever run against a real
Qdrant or a real Ollama — and the one cross-slice dependency no test here can prove: nothing in (b) calls
`set_has_invalid_tasks`, so until slice (c) lands 3.6–3.8 every mark excludes nothing from few-shot
retrieval and **nothing goes red**. The only thing left is the owner's merge of the nine-PR chain.

### Slice (b) merged and deployed — 2026-10-02

The owner authorized the merge of the nine-PR chain on 2026-10-02 and it landed in order, each PR
retargeted to `main` immediately before its merge (a stacked chain cannot merge into its own base, or the
content would grow the branch instead of `main`):

`#31` `7fb1384` → `#32` `3bbd784` → `#33` `9380b75` → `#34` `80ecd85` → `#35` `5579121` → `#36` `c35bf9e` →
`#37` `22a8095` → `#38` `d4e7f54` → `#39` `fe9a16d`. **`main` = `fe9a16d`**, zero open PRs, and the nine
branches are deleted (only the pre-split `…-wu4` safety branch and the older `chore/dev-reset-0028`
remain locally, and neither is on the remote).

**Deploys.** `deploy-backend.yml` triggers only on `backend/**`, so the frontend-only merges never
restart the API. Seven merges qualified and the workflow's concurrency group serialized them: GitHub
**cancelled the queued ones** as newer ones arrived, which is the documented behaviour of
`cancel-in-progress: false` — it cancels a *pending* run, never the running one. Two deploys therefore
ran to completion: `c35bf9e`'s, where the migration happened —
`INFO [alembic.runtime.migration] Running upgrade 0028 -> 0029, story_deletions` — and `22a8095`'s,
which found the schema already at head and passed the readiness gate (`Ready after 8s: container
running, http://localhost:8000/api/v1/health/ready answered 2xx`).

**Verified live, from outside:** `GET https://storico-api.163.192.150.75.sslip.io/api/v1/health` →
`{"status":"ok","version":"0.9.0","database":{"status":"ok"},"schema":{"status":"ok"}}`; the readiness
endpoint → **200**; and the Vercel production deployment for `fe9a16d` → **success**.

**Two consequences to keep in view.** Production runs slice (b) now but **still cannot extract**: the
workspace has no LLM configuration and `resolve_llm_config` falls back to an Ollama that does not exist
there (**D-a-6**). And the version string still reads `0.9.0` because no `make bump` has run — the merged
commits are `feat`s, so the release is the owner's call, never a task in a change.

## Slice (c) `extraction-versioning-prompt` — session 2026-10-03 (c1): WU1 delivered as three chained PRs

Slice (c) started after `v0.10.0` (the release that carried slice (b)) and after this session merged the
nine-PR chain of (b) into `main`. Its apply progress lives in the change folder
(`openspec/changes/extraction-versioning-prompt/apply-progress.md`), section by tranche; this is the
index a reader needs to find it.

**WU1 measured 2,205 changed lines against a 750–1,000 forecast** — the slice's usual pattern, now its
fourth instance — so the owner chose to open it as **three chained PRs on the plan's own axes**, which
is the reading of the delivery decision that respects the 400-line budget:

| PR | Branch → base | Part | Measured |
| --- | --- | --- | --- |
| **#40** | `…-wu1a` → `main` | the two unbounded context reads (`list_for_context` on both repositories) | 685 |
| **#41** | `…-wu1b` → `…-wu1a` | `ProjectContext`, the **required** `context` argument, the two template blocks, the call-site churn | 713 |
| **#42** | `…-wu1c` → `…-wu1b` | the triangulations, the Postgres scale file, the closing pass | 809 |

All three are green. **CI on #42 reports `1252 passed, 18 skipped`**, which reconciles exactly with the
local `1231 passed, 39 deselected`: of the 39 integration cases, 21 ran in CI (18 Docker-gated plus the
three new scale cases) and 18 skip everywhere (16 Qdrant live + 2 Ollama live). So the **1000-row scale
proof ran and passed in CI** — the half this machine could never show.

**Phase 1 of the slice is complete (1.1–1.15).** Three things in it a reviewer should not have to
rediscover: the reads are unbounded **on purpose** (the API's page window would truncate prompt context
silently, and the 120-story case proves the consequence); `context` is required because a `None` default
would let a caller render 0.8.0's prompt while the row claimed 0.9.0; and the blessed opt-out needs no
code (Jinja ignores unreferenced variables, and the snapshot records what was composed, so the
divergence is readable from the version's own stored facts).

**One split recorded rather than papered over:** the row-level half of that snapshot is WU2's write
(task 2.5 fills `prompt_config` from `template_variables`; 2.6 reads those keys back from the row), so
part (iii) asserts the boundary facts that exist today and names the deferral.

**Next:** WU2 — what the version records (the negative-example composer, the snapshot dictionary, the
`usage` types and the four adapters, `record_usage`). Its third part is the slice's largest atomic
commit (`LLMResponse` + the `.text` ripple, ≈305 lines) and it is the unit that closes **D10**.
