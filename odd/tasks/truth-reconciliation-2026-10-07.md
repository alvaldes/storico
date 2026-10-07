# truth-reconciliation-2026-10-07

> **Status**: authorized by the owner on 2026-10-07 ("reconciliar la verdad documental"), **closed
> 2026-10-07** — WU1, WU2 and WU3 landed on branch `docs/truth-reconciliation`, **stacked on `fix/llm-test-workspace-scoped`** off `main`.
> Nothing pushed. Receipt-driven development is off in this clone.
> **Created**: 2026-10-07

## Goal

Make the three documents a reader trusts — `AGENTS.md`, `prod.todo.md` and the extraction-versioning
record — describe the application that is actually deployed, and archive the two completed OpenSpec
changes so the canonical spec store stops describing pre-(b) behaviour.

The trigger was not a complaint. It was that **two of the four items offered as "pending" turned out to
be finished**, and the documents said otherwise. A thesis evaluation agenda built on `AGENTS.md` would
have planned around a versioning feature it believed was not applied.

## What was measured, 2026-10-07

| Claim | Evidence |
| --- | --- |
| Slice (b) is task-complete | `openspec/changes/archive/2026-10-07-extraction-versioning-api/tasks.md` → **79 checkbox lines, all `[x]`, zero open** |
| Slice (c) is task-complete | `openspec/changes/extraction-versioning-prompt/tasks.md` → **47 checkbox lines, all `[x]`, zero open** |
| Neither slice has an open box — and a naive count says otherwise | searching the string `[ ]` anywhere in either file returns three hits, and all three are prose quoted inside dated notes describing an intermediate state. In (b) the UI seam that note names was closed the same day by W6-B1 (`TaskEditorProps`: `markDefaultChecked` / `reasonAutofocus` / `activeMark`); in (c) tasks 3.1/3.2/3.3 and 3.9 are checked today. **This row is itself a correction**: the first version of this page read the raw string counts, called the result "80/81 and 51/53", and built a story about three live deferrals on top of it. A subagent measured the checkbox lines and refuted it |
| (b) landed | PRs **#31–#39**, merged 2026-10-02, carried by `v0.10.0` |
| (c) landed | PRs **#40–#50**, merged 2026-10-03, carried by `v0.11.0` (tag date 2026-10-03). **Annotated same day:** the range reads as eleven merges but **#43 was closed unmerged and re-opened as #44** — ten PRs merged, corroborated by the merge commits on `main` |
| Production runs all of it | `GET https://storico-api.163.192.150.75.sslip.io/api/v1/health` → `{"status":"ok","version":"0.12.0","database":{"status":"ok"},"schema":{"status":"ok"}}`; `/api/v1/health/ready` → **200** |
| The retired creation endpoint is retired **in production** | `POST /api/v1/tasks/` against production → **410** with `error_code: TASK_CREATION_ENDPOINT_REMOVED`. Measured live; the handler only raises, so the probe changes nothing |
| The app ships a version selector | `frontend/src/components/react/VersionSelector.tsx`, consumed by `StoryDetail.tsx`, with its own test file |
| The board and the export read the current version | `api/routes/tasks.py:228,252,266` all go through `repo.list_page` (the current-version predicate); `api/routes/export.py:102` uses `list_current_by_workspace`; `frontend/src/lib/tasks-api.ts:24-32` documents the version-aware read |
| The version-blind repository reads are **unreachable from HTTP** | `TaskRepository.list_by_story` / `list_by_workspace` are wrapped only by `TaskService.list_tasks_by_story` (`application/services/task_service.py:87`), and **no module under `api/` calls it** — its only caller anywhere is `tests/test_api/test_tasks.py:272` |

## What the documents say, and what is false

| Document | Claim | Reality |
| --- | --- | --- |
| `AGENTS.md:4` | "Los slices (b) `extraction-versioning-api` y (c) `extraction-versioning-prompt` siguen sin aplicar" | Both applied; (b) 2026-10-02, (c) 2026-10-03 |
| `AGENTS.md:4` | "la versión publicada de 0.9.0 contiene sólo el lado del esquema de la feature: sin endpoints de versionado sin UI de versiones" | The published version is **0.12.0**; it carries the endpoints, the prompt composition and a shipped `VersionSelector` |
| `prod.todo.md:49` | 🟡 `POST /api/v1/tasks/` advertises `201` and answers `500`; a deploy is missing | Measured live: **410** with the canonical error code. Closed |
| `prod.todo.md:50` | 🔴 Re-extracting a story shows **both** runs' task sets in the board, story detail and export; "el filtro de versión vigente llega en (b) WU3" | WU3 landed. The board reads `list_page`, the export reads `list_current_by_workspace`, the frontend passes `extractionId` when it wants a frozen version. Closed |
| `prod.todo.md:50` vs `:98` | `:50` says the export groups by story id with no version criterion; `:98` says it exports only the current version | Both written the same day and they contradict each other. `:98` is right |
| `prod.todo.md:98` | 🟡 "a medias": the export selection, and the LLM's `title`/`description` still editable | Half right. The export half stands: no user-facing version choice, `format` being the only query parameter. The title/description half was **refuted by the verification pass** (F2): the D5/D21 field matrix is implemented — `UpdateTaskRequest` refuses `title`/`description`/`priority` with 422 via `extra="forbid"` (`backend/src/storico/api/schemas/task.py:11-27`), pinned by `backend/tests/test_api/test_tasks.py:954`, and the UI renders both fields as read-only text (`frontend/src/components/react/TaskEditor.tsx:376-389`). Corrected in `prod.todo.md` in this commit |
| `odd/tasks/extraction-versioning-090.md` items 11 and 12 | `[ ]` "Apply slice (b)" / "Apply slice (c)" | Both applied and deployed |
| both change folders | still under `openspec/changes/`, not archived | (a) is the only one in `archive/`; the two complete changes were never archived |

## The archive is not a move, and that is the finding that changed the plan

`openspec/changes/archive/2026-09-30-extraction-versioning-schema/archive-report.md` is the precedent,
and it was **written by hand** because `openspec` is neither installed nor a project dependency. It did
not just move a folder: it transformed each delta into the canonical store
(`openspec/specs/<capability>/spec.md`) and recorded the counts, the open defects at archive time, the
merge and deploy evidence, and the one check that could not run.

Sized for the two changes still in flight:

| Change | Capabilities touched | Requirement blocks to merge | New canonical files |
| --- | --- | --- | --- |
| `extraction-versioning-api` | 7 (`export-download`, `extraction-versioning`, `extraction-workflow`, `kanban-board`, `task-editor`, `task-invalidation`, `workspace-permissions`) | **25** (16 `ADDED`, 9 `MODIFIED`) | 1 (`workspace-permissions`) |
| `extraction-versioning-prompt` | 4 (`extraction-context`, `extraction-versioning`, `few-shot-retrieval`, `vector-store-isolation`) | **22** (18 `ADDED`, 4 `MODIFIED`) | 1 (`extraction-context`) |

**47 requirement blocks across 11 delta files spanning 10 distinct capabilities** — `extraction-versioning` appears in both changes, so the file count overcounts the capability count by one — two of them new capabilities. The `MODIFIED` half
is in-place replacement of canonical text, and nothing in the repository validates the result: the deltas
are only checked against the applied files by reading them. So the archive is the one part of this
option whose failure is durable and silent — the canonical store would disagree with the deployed
behaviour and no test would say so.

**Consequence for the plan:** the prose reconciliation (WU1) is the low-risk half and lands first; the
two archives are sized above and were put to the owner again rather than absorbed silently, because the
option as offered implied a move, not 47 semantic merges.

## Tasks

- [x] **WU1 — Reconcile the three prose surfaces.** The `AGENTS.md` header block, `prod.todo.md` rows
  49, 50 and 98, and `odd/tasks/extraction-versioning-090.md` items 11/12 plus a 2026-10-07 handoff
  section. History is appended or annotated, never rewritten: the rows and the record keep what was true
  when they were written and gain the correction beside it.
- [x] **WU2 — Archive `extraction-versioning-api`** — `6e9a92c`. 25 requirement blocks merged into the
  canonical store (16 `ADDED`, 9 `MODIFIED`), `workspace-permissions` created, the folder moved to
  `archive/2026-10-07-extraction-versioning-api/` with its deltas intact, and the hand-written
  `archive-report.md` carrying slice (a)'s caveat.
- [x] **WU3 — Archive `extraction-versioning-prompt`** — `8992164`. 22 requirement blocks merged
  into the canonical store (18 `ADDED`, 4 `MODIFIED`), `extraction-context` created, the folder moved
  to `archive/2026-10-07-extraction-versioning-prompt/` with its deltas intact, and its own hand-written
  `archive-report.md` carrying the caveats.

## Non-goals

- **Not** the Docker Compose drift (item D of `docs-pass-open-findings.md`). The owner decided not to
  correct it; touching it here would be re-opening a decision through the back door, and it is a
  different claim in a different section of the same file.
- **Not** item B (the admin reading back the stored key). Also already decided.
- **Not** the three deferred sub-clauses of (b) and (c), and not the product gaps row 98 still records
  — the export having no user-facing version choice is real and stays real.
- **Not** a rewrite of any historical measurement. A `prod.todo.md` row that was measured against a tree
  that has since moved keeps its measurement and gains the outcome.
- **Not** dead-code removal. `list_tasks_by_story` and the two version-blind repository reads have no
  route caller; deleting them is a code change with its own justification and is only recorded here.

## Evidence log

| Work unit | Commit | Evidence |
| --- | --- | --- |
| WU1 — prose reconciliation | `ef7a7bb` | No RED/GREEN: passive documentation with no test surface. `git diff --check` clean; a voseo scan of the added lines found nothing. The writer re-verified every code claim and **corrected one of mine**: `list_current_by_workspace` is at `export.py:102`, not `:105`. Parent's check: the `AGENTS.md` diff demotes the 2026-09-30 paragraph with its text intact and adds exactly one dated note covering the two sentences that were true on their date; the Docker-Compose and 2026-09-25 paragraphs are untouched. |
| WU2 — archive (b) | `6e9a92c` | No test surface. The parent verified the merge **mechanically and independently of the writer**: a script compared all 25 delta requirement blocks against their canonical counterparts and found **25 identical, 0 differing**, with the legacy requirements the deltas do not mention still in place — **22 of them as measured when (b) merged; the same check run after (c) merged returns 29**, because (c) grew `extraction-versioning` by another 7 blocks. Neither number is wrong; each belongs to its own point in time. The first run reported one false differ — the extractor swallowed the `## ADDED Requirements` header that follows the last block of a section — which is recorded because it is the trap any future check of this kind will hit. |
| WU3 — archive (c) | `8992164` | Same method as WU2, same shape of evidence: the merge was verified mechanically and independently of the writer, and the (c) archive's own `archive-report.md` records the counts. |
| verification — independent pass over all three archives | this commit | **No network probe, no test re-run.** The pass covered **all three archives** (`2026-09-30-extraction-versioning-schema`, `2026-10-07-extraction-versioning-api`, `2026-10-07-extraction-versioning-prompt`): **61 delta blocks, 61 identical, 0 differing**, legacy preservation checked per capability, 0 duplicate requirement titles. The verifier reproduced the mechanical result and additionally returned **10 stale claims and 1 semantic finding**. **Confirmed:** the mechanical merges of both archives, the reconciliation's code references, the task-count numbers (79/47 checkbox lines), the version tags and the archive layout. **Refuted:** the `title`/`description`-still-editable claim (F2 — corrected in `prod.todo.md` row 98, in `AGENTS.md` row 32, and in the 2026-10-07 handoff of `odd/tasks/extraction-versioning-090.md`) and the `extraction-context` status requirement the code does not satisfy (F1 — recorded, not absorbed, in `prod.todo.md`). **Could not verify:** the live production HTTP claims (`/api/v1/health`, `/api/v1/health/ready`, the `410` on `POST /api/v1/tasks/`) — no network probe was run, so those rest on the measurements recorded when they were taken — and the backend/frontend suites were not re-run. |
| correction | this commit | The two wrong numbers below, fixed in `AGENTS.md`, in `odd/tasks/extraction-versioning-090.md` and in the table above. No other claim changed. |
| production checklist cleanup | `80719a7` | `prod.todo.md` 403 → 153 lines. The closed D-a-3 post-mortem moved verbatim to `odd/tasks/prod-purge-d-a-3.md` — proved line-by-line: only 7 heading demotions and one dated correction — with a redirect left at the old path because archived OpenSpec records cite it there. Three live items surfaced at the top; 9 closed rows compressed after verifying their pointer targets really carry the detail; 10 left whole because their evidence exists only in that row. |
| the owner's four decisions | this commit | **F1 → (ii)** align the requirement: the canonical sentence was trimmed with a dated note and the slice's archive report declares the byte-identity broken on purpose. **Version → `feat(api)`**: the probe commit was reworded from `fix(api)` (`a2897ae`), so the next bump cuts `0.13.0` and not the `0.12.1` that would understate a moved public path nor the `1.0.0` the roadmap reserved for observability; the base branch was rebased and the docs branch replayed onto it, with the base tree verified **identical** before and after (only the message changed). **Push → both branches, two stacked PRs**. **Environments → documented, not separated**: the accepted risk now names the three shared things, including that a token signed in development is valid in production. |

**Two of my own numbers were wrong in the briefs, and a subagent caught both.** The mode split is 16
`ADDED` / 9 `MODIFIED`, not 18/7 — I counted section headers, not requirements. And both `tasks.md` are
**fully checked** — 79 and 47 checkbox lines, zero open — not "80/81 and 51/53": I searched for the
string `[ ]` anywhere, which finds prose quoted inside dated notes. Both numbers were propagated into
`AGENTS.md` and into the extraction-versioning record by WU1 before being caught, and both are corrected
in the commit that follows. The lesson is narrow and worth keeping: **for these files, count checkbox
lines, never string occurrences** — and a document this dense will punish a citation made from memory.

## Limitations

- **F1 — a canonical requirement the code does not satisfy, found by the semantic pass.** The
  `extraction-context` requirement "The Prompt Carries the Project's Other Stories and Existing
  Tasks" demands each existing task's title, **status** and story in the rendered prompt
  (`openspec/specs/extraction-context/spec.md:25-29`). The service composes the status
  (`backend/src/storico/domain/services/extraction_service.py:80-90`); the template drops it
  (`backend/src/storico/infrastructure/llm/prompts/task_generation.j2:24`, zero `status`
  occurrences). **Resolved 2026-10-07**: the owner chose to align the requirement, so the canonical
  sentence was trimmed to what the change specified, implemented and tested — the title and the
  owning story — with a dated note in the spec and a note in the slice's archive report recording
  that this single block is deliberately no longer byte-identical to its delta. The archived
  `tasks.md` and the delta files were not touched. The reasoning: the code matches its tasks and
  tests, so it was the normative sentence that promised more than the change specified.
- **F1's diagnosis, refined by reading the change's own task list: (c) never asked for the status.**
  Task 1.6 builds the `## Project Context` block without naming it, and task 1.7 — its RED case —
  pins "each existing task's title **with its owning story**". The only artifact that carries the
  status is the data structure, `TaskContextRow(title, status, user_story_id)`
  (`openspec/changes/archive/2026-10-07-extraction-versioning-prompt/tasks.md:236`). So **the code is
  coherent with its own tasks, and it is the normative sentence that promises more than the change
  specified** — a drafting inconsistency inside (c), not an implementation miss. That changes what
  the options cost: rendering the status is new behaviour rather than a fix, and trimming the
  sentence is alignment with what was actually specified and tested.
- **PR-enumeration nit:** the archive report and this page's measured table originally described
  slice (c) as the PR chain **#40–#50**, which reads as eleven merges. **#43 was closed unmerged and
  re-opened as #44** — ten PRs merged, corroborated by the merge commits on `main` (`git log --merges`
  lists #40, #41, #42, #44–#50 and no #43). The archive report's two enumerations were made precise
  and the table row annotated; the historical range is kept where it stands, not rewritten.
- The verification pass could not probe production HTTP (no network access) and did not re-run the
  backend or frontend suites; those checks rest on the measurements recorded when they were taken.
