# ODD Feature: extraction-versioning-090 (OpenSpec change authoring)

> **Status (2026-09-30, close of this session)**: **slice (a) is code-complete — 46/46 tasks** — on
> `feat/extraction-versioning-schema-wu1`, PR #30 still **OPEN** with CI green at head. Task 4.4 landed
> with the owner's Option A (`revoked_by` → `RESTRICT`). **D-a-3 is decided (purge window) and NOT
> executed**: the wipe and the merge are separate confirmations the owner fires, in that order. New
> defect **D-a-4** (the account-delete route exists and would 500) is recorded and carried into slice
> (b). → read **"Session handoff — 2026-09-30"** at the end of this file first.
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
  Harmless at 1 row and 4 configs; look at it if a custom provider is ever deleted.
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

---

## Session handoff — 2026-09-30 (slice (a) delivered, merge blocked on purpose)

Written for a session that starts with nothing in context. Read in this order: this section, then
`openspec/changes/extraction-versioning-schema/verification.md`, then `prod.todo.md`'s
"Bloqueo de despliegue" item.

### Where things stand

| | |
| --- | --- |
| PR | **#30** — <https://github.com/alvaldes/storico/pull/30> — base `main`, **OPEN, NOT MERGED**. Its body still describes `4.4` as open and cites "15 commits / 38 files": both are stale as of `7e3aa6e`, and updating it is the owner's call |
| Branch | `feat/extraction-versioning-schema-wu1`. **Deliberately not pinned to its own HEAD sha or commit count** — a commit cannot truthfully cite the sha it is creating. Measure at review time: `git rev-list --count main..HEAD` and `git diff --shortstat $(git merge-base main HEAD)..HEAD`. Two counts were wrong here before this note (the PR body's "15 commits / 38 files" and this table's "21 commits"), which is why the commands replaced the numbers |
| Last measured | at `7e3aa6e`: **26** commits over `main` `1737708`, `41 files changed, 5027 insertions(+), 1001 deletions(-)` |
| CI on `382a9c5` | **`1064 passed, 18 skipped`** (run 36658068793) — the same 15 integration cases as the earlier run, now including the renamed revoker-FK case, so `RESTRICT` is observed and not inferred |
| Local suite | `1049 passed, 33 deselected`, 0 failed · `ruff check`/`format --check` exit 0 |
| Open tasks in the change | **none** — 4.4 closed 2026-09-30; 1.1–1.20, 2.1–2.6, 3.1–3.9, 4.1–4.5 and 5.1–5.6 are closed |
| Blocked on | the D-a-3 runbook (**not executed**): inventory → purge (relational + Qdrant) → merge. No backup — the owner waived it 2026-09-30, so the measured inventory in `prod.todo.md` is the only record of what is destroyed |
| Not authorized | slice (b) `extraction-versioning-api`, slice (c) `extraction-versioning-prompt` |
| Receipt-driven development | still **off** in this clone; no native review ran on any tranche |

Landed tranches, in order: `1a90aff` + `1f2d573` (merged WU1+WU2: schema and birth), `c47a1b2` (3a
render snapshot), `3364c43` (3b-i marks), `366c341` (3b-ii-a dead path deleted), `3a23655` (3b-ii-b
`save()` removed), `94db112` (3b-iii triangulates), `20a7e02` (WU4a invariants + mutation matrix),
`7a98c19` (WU4b Postgres half), then the `fix(test)` chain `3333b7b` / `4da58fb` / `962359a` and the
doc commits.

### The blocker (D-a-3), which was the reason the PR was not merged

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
3. **Execute the runbook, in its own order: inventory → purge (relational + Qdrant) → confirm the counts
   are 0 → merge.** No backup: the owner waived it, and the inventory stands in its place. Wiping *before*
   merging is not a detail: merging first fails the deploy on every later push until somebody empties the
   pair. Two choices are still open inside the runbook:
   - **step 2b, the scope of the vector wipe** — only `storico_extractions_prod` (1 point), or all three
     collections (`_prod` 1, `_dev` 1, the legacy `storico_extractions` 19).
   - **step 3, the denormalized story state** — `user_stories.status` keeps saying `extracted` /
     `failed_extraction` over stories that will have no extraction row at all. Reset to
     `pending_extraction`, or leave it.
4. Slice (b) then needs its own apply authorization, carrying **three** named requirements: **D-a-1**
   (re-dispatch duplicates task rows), **D-a-4** (the account-delete 500), and retiring
   `POST /api/v1/tasks/`, which slice (a) currently pins as a 500 refusal (`tasks.extraction_id NOT
   NULL`) — that pin is honest about being temporary. Slice (c) after that.
5. Do not renumber task IDs. Slices (b) and (c) reference (a) IDs such as 2.3, 3.4 and 3.7.
6. Side item, closed by measurement rather than by a fix: the production `provider = 'Nan'` that an
   earlier version of this document called a defect is a legitimate custom provider (`custom_providers`,
   added by revision `0021`, free-form names). The correction and the lesson are in `prod.todo.md`.

## Session handoff — 2026-09-30 (b): the blocker got decided, and the measurement corrected two documents

Everything above stays true. This is what changed in the session that closed 4.4.

**Two owner decisions, both taken inside the session's question round:**

- **D-a-3 → path 1, the purge window.** Nothing was executed. `prod.todo.md` carries the runbook; the
  backup step was replaced by a measured inventory (the owner's call — "nothing worth saving"), and the
  wipe now names Qdrant as well as the relational pair.
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
