# ODD Feature: extraction-versioning-090 (OpenSpec change authoring)

> **Status**: **planning landed; apply authorized in tranches** — slice (a) WU1 started, RED phase
> only, with the human reviewing between tranches. No source file under `backend/src/` is written yet.
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
`openspec/changes/extraction-versioning-schema/explore.md` (shared base for the three changes).

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
  re-reads) → ledger in `openspec/changes/extraction-versioning-schema/explore.md`
- [x] 2. Resolve the four drifts into change requirements (Δ1–Δ4 above)
- [x] 3. Write slice (a) `extraction-versioning-schema` — proposal, delta specs, design, tasks
  (`sdd-proposal` → `sdd-spec` → `sdd-design` → `sdd-tasks`, auto mode, each gate-validated)
- [x] 4. Write slice (b) `extraction-versioning-api` — proposal, 7 delta specs, design, tasks
- [x] 5. Write slice (c) `extraction-versioning-prompt` — proposal, 4 delta specs, design, tasks
- [x] 6. Validate all three with native `gentle-ai sdd-status --contract gentle-ai.sdd-status/v2`
  and report the per-slice Review Workload Forecast (ask-on-risk gate)
- [x] 7. Land the planning artifacts on `main` (`3ddbe28`, `66bbb3b`)
- [ ] 8. Apply slice (a) WU1 — Schema Identity, **in tranches**: RED (1.1–1.3) authorised; GREEN
  (1.4–1.17), TRIANGULATE (1.18–1.19) and REFACTOR (1.20) each wait for the user's review of the
  tranche before it

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

Planning landed on `main` before any implementation branch was cut:

| Commit | Content |
| --- | --- |
| `3ddbe28` | `chore: ignore the local CodeGraph index` — `.codegraph/` is derived state and must not ride a docs commit |
| `66bbb3b` | `docs(openspec): commit the 0.9.0 extraction-versioning planning` — 27 artifacts |

```
openspec/changes/extraction-versioning-schema/{explore,proposal,design,tasks}.md
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
