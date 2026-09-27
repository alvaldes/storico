# ODD Feature: task-control-copy-truth

> **Status**: complete and opened as **PR #23** against `main` on 2026-09-27. Two copy commits
> (`f286718`, `0605514`) carry the change; the rest of the branch is this record. `git log
> main..HEAD` is the list, and the count is deliberately **not** written anywhere in this
> document: a commit that records how many commits exist is falsified by its own existence, and
> this branch paid for that lesson more than once. Merging is the owner's call.
> **Created**: 2026-09-27
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/task-control-copy-truth`, from a clean `main` @ `ded4031`
> **Receipt-driven development**: **off** in this clone (`gentle-ai review mode status`:
> global on, clone-local off). No native review lineage will be started; the gate is an
> independent verification instead, the same shape `honest-llm-copy-and-doc-drift` used.
> **TDD**: `strict_tdd: true` in `openspec/config.yaml`. This slice is copy-only, so the
> tests that carry it are the existing i18n guards (`neutral-spanish`, `no-duplicate-keys`,
> key parity); no new behaviour, no new test.
> **Runners**: `pnpm vitest run` + `pnpm exec tsc --noEmit` (frontend).

## Problem

Two public surfaces state things about generated tasks that the app does not do, and one
of them is a privacy policy.

`landing.faq.a4` — `frontend/src/i18n/en.json:89`, `es.json:89`:

> "Absolutely. You can review, edit, or **delete** any task before exporting. You also have
> **full control over the resulting Kanban board**."

`pages.privacy.retention` — `en.json:652`, `es.json:652`:

> "Projects, stories, **and tasks** can be deleted at any time from within the application."

Both promise deletion of an individual task. **There is no way to delete a task from the UI.**
`grep` for a task delete over all of `frontend/src` returns nothing outside prose and tests;
the only artifact that exists is an orphan backend endpoint no client calls. The privacy
sentence is the worse of the two: it asserts a data-removal right the product does not
implement, which is exactly the class of defect this repo has been closing
(`honest-llm-copy-and-doc-drift`, `public-surface-truth`).

The rest of the claim is the mirror image: **editing, which the FAQ also promises, is real**
and supported end to end. So the fix is not "delete the sentence" — it is to keep what is
true, name where it happens, and stop promising what is not.

## Established facts (measured, 2026-09-27)

| Claim | Verdict | Evidence |
| --- | --- | --- |
| Title/description are editable in the app | **TRUE**, four layers deep | `TaskEditor.tsx:219-231` `<Input value={title} onChange…>` + `<Textarea value={description}…>`, no `readOnly`, no `disabled`, no gate → `lib/tasks-api.ts:68-79` `updateTask()` sends both → `routes/tasks.py:288-289` `if body.title is not None: kwargs["title"] = body.title` then `repo.save()` → `schemas/task.py:30-31` `UpdateTaskRequest` declares both with **no validator**. One handler, `@router.put("/{task_id}")`, nothing shadows it. |
| Where editing is reachable | Story detail only | `StoryDetail.tsx:474` pencil sets `editingTaskId`; dialog mounts at `:567-577`. Route `/[locale]/stories/[id]`. Not on the Kanban board, not on the export page. |
| Editing is intentional, not an accident | **Yes** | `TaskEditor.test.tsx` covers save; `AGENTS.md` lists it as feature 32 ("Revisión/edición manual de tareas: editar título, descripción, etiquetas"). |
| A task can be deleted from the UI | **FALSE** | No task-delete affordance in `frontend/src`. Backend `DELETE /api/v1/tasks/{task_id}` (`routes/tasks.py:317-333`) exists but is unreferenced by any client. |
| "Full control over the resulting Kanban board" | **Overclaim** | The board moves cards across the 5 statuses subject to `getAllowedTaskTransitions` (`KanbanBoard.tsx:124-141`), optimistic `updateTaskStatus` (`:150-190`). Cards are read-only: `KanbanCard.tsx:66-70` renders the title as a link to the story. No card edit, no delete, no column management, no in-column reorder (same-column drop is ignored, `KanbanBoard.tsx:105-106`). |
| "tasks can be deleted at any time from within the application" (privacy) | **FALSE** for tasks, **TRUE** for projects and stories | `Trash2` consumers: `ProjectsList`, `StoriesList`, `ProjectDetail`, `WorkspaceSettings`, `MemberManagement`, `StoryDetail` — none of them a task. |
| Deleting a story does remove its tasks | **TRUE, at the schema level** | `alembic/versions/0014_add_cascade_deletes.py:46-58` puts `ON DELETE CASCADE` on `tasks.user_story_id → user_stories.id`; `models/task.py:23-24` mirrors it. `user_stories.project_id → projects.id` cascades too (`:31-43`), so the project path cascades two levels. |
| "you can edit at export time" (the owner's model of the app) | **NOT IMPLEMENTED** | `ExportPanel.tsx` has no inputs and no preview — only a count line (`:181-184`) and a download that hits `GET /api/v1/workspaces/{id}/export/tasks?format=…` (`:46`). Editing happens in the downloaded file, in the destination tool. |
| Export formats | **JSON and Markdown only** | `ExportPanel.tsx:20,145-176` offers two; `routes/export.py:77,89-92` rejects anything else with 422. So `landing.faq.a5` is accurate and `export-copy.test.ts` already guards it. |
| Task versioning / "mark as invalid" | **Does not exist yet** | `TASK_STATUSES` = backlog/todo/in_progress/review/done (`types/task.ts`); no invalid state, no version field, no ODD feature doc. `prod.todo.md:36` reserves **`0.9.0`** for "el versionado de extracción". |

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Which half is wrong: the copy or the app | **The copy.** The owner chose to align text to code rather than rip the editor out. Making LLM output non-editable is a product change with its own consequences and is not smuggled into a copy slice (see Follow-ups). |
| D2 | Editing | **Kept in the copy**, and the ambiguity removed by naming where it happens (the story). The FAQ question is rewritten so it asks about *changing* tasks, not about a pre-export step that does not exist as a distinct screen. |
| D3 | Deletion | **Stated as absent, explicitly.** The owner asked for no ambiguity here, so the answer says you cannot delete a single task instead of quietly omitting it. |
| D4 | The Kanban clause | **Described, not sold.** "Full control" becomes the one thing the board does: move tasks between workflow stages. |
| D5 | Versioning and "mark as invalid" | **Not announced.** Neither exists. Copy that pre-ships a mechanism is the same defect class in the other direction. |
| D6 | Privacy sentence | **Corrected to the real removal paths**: projects and stories delete from the app, and deleting either removes the tasks under it (cascade, verified above). It stops claiming per-task deletion. |
| D8 | "…or status" in the first cut of `a4` | **Removed.** `f286718` listed `status` among the freely editable fields. Measured against `types/task.ts:9-15`, `VALID_TASK_TRANSITIONS.done` is the **empty list**: a task in Done cannot change status at all, and every other status reaches only its neighbours (`TaskEditor.tsx:261` disables the illegal options). So the clause was a fresh overclaim of exactly the class this slice exists to remove, and it is narrowed: title, description, labels and dependencies stay "edit any of them", status becomes "move a task through the workflow stages". The pencil itself is gated **only** by a pending extraction (`StoryDetail.tsx:471`), never by task status, so "edit any of them" is otherwise correct. |
| D9 | Two citations that do not exist in this repository | **Rejected, and attributed to nobody I can prove.** A review of the first candidate came back citing `isEditDisabled`/`canTransition` at `StoryDetail.tsx:426,438,471` and a `prod.todo.md:61` row named "Correcciones de copy". Both are false as facts and I checked them myself: `grep -rn "isEditDisabled\|canTransition" frontend/src/` → 0 matches, and `prod.todo.md` has 66 lines with `:61` = `\| Comparativa manual vs automática \|` and no such row anywhere in the repo. When challenged, the verifier re-ran its own greps, agreed both do not exist, and stated it had never written them — so the honest record is **two unfounded citations reached this session**, not "the verifier lied". What is settled is the consequence: nothing from that report was accepted without re-derivation, the gate was re-run on the corrected tree, and re-deriving its one useful pointer produced D8. A third thing I had flagged as a fabrication was **my own error**: its "Markdown export has zero identifiers" is correct (`_build_markdown`, `routes/export.py:33-66` emits no `id`, no `status`); only the JSON payload has them (`:96-112`). Withdrawn. |
| D10 | "de a una" in the first cut of the narrowed Spanish `a4` | **Replaced with "una por una" — my error, caught by the writer, not by the suite.** ADR-008 requires neutral international Spanish, and "de a una" is a Rioplatense construction. It is **not** voseo, so `neutral-spanish.test.ts` cannot catch it: that guard is a finite `Set` of voseo forms (`:15-60`), which is the whole class of thing a blocklist can see. Same for "todo lo que hay debajo", a calque of "everything under it", which became "todo lo que contienen". Lesson recorded rather than silently patched: the no-voseo test proves *no voseo*, not *neutral Spanish*. |
| D7 | `pages.docs.step_6` and the hero subtitle | **Left alone.** The explore pass flagged them as carrying "the same overclaim"; under D1 they are simply true — editing exists. Rewriting accurate copy to match a scope that includes them would be churn, and churn in two catalogs is review workload for nobody. |

## Non-goals

- No behaviour change of any kind. No `TaskEditor` edit, no backend edit, no route, no schema.
- No removal of the task editor, no read-only title/description (D1 defers that to its own feature).
- No mention of task versioning or invalid marking (D5).
- No new test: the guards that protect this change already exist and are the acceptance gate.
- No sweep of unrelated stale marketing prose found on the way (see Follow-ups).

## Tasks

### T-001 — Rewrite `landing.faq.q4` and `a4` in both locales

- **Status**: pending
- **What**: the question stops presupposing a pre-export editing screen; the answer keeps
  review + edit (true), names the story as where it happens, states plainly that a single
  task cannot be deleted (D3), and reduces the board claim to moving tasks between stages
  (D4). Neutral Spanish, no voseo.
- **Acceptance**: no "delete"/"eliminar" promise for tasks survives in `a4`; no "full
  control"/"control total"; `en`/`es` keep identical key sets.

### T-002 — Correct `pages.privacy.retention` in both locales

- **Status**: pending
- **What**: replace "Projects, stories, and tasks can be deleted at any time from within the
  application" with the true removal surface (D6). Everything else in the sentence — ownership,
  account data, usage data, no selling — stays byte-identical; this is a privacy document and
  an unrequested rewrite of it is worse than the defect.
- **Acceptance**: the clause no longer claims per-task deletion, and the replacement names only
  mechanisms verified above (project delete, story delete, cascade).

### T-003 — Record the D7 judgement

- **Status**: pending
- **What**: `pages.docs.step_6` and the hero subtitle are audited and left unchanged, with the
  reason written here rather than silently skipped.
- **Acceptance**: this document states both were checked and why they are true.

### T-004 — Gate

- **Status**: pending
- **Commands**:
  - `cd frontend && node_modules/.bin/vitest run`
  - `cd frontend && node_modules/.bin/tsc --noEmit`
  - `cd frontend && node_modules/.bin/astro build`
- **Acceptance**: all three green, with the suite counts recorded. The i18n suites
  (`neutral-spanish.test.ts`, `no-duplicate-keys.test.ts`, `provider-copy.test.ts`,
  `export-copy.test.ts`, `api-docs-copy.test.ts`) are the regression check: they enforce key
  parity, the no-voseo rule, and that no catalog string names a retired export format.

### T-005 — Record the deferred product decision

- **Status**: pending
- **What**: write the owner's actual intent — non-editable LLM output, delete → mark invalid,
  export by version with or without invalid tasks — into the follow-ups here and into
  `prod.todo.md`, tied to the `0.9.0` extraction-versioning slot `prod.todo.md:36` already
  reserved, so the copy is named as part of that feature's scope and cannot be "forgotten".
- **Acceptance**: a reader of `prod.todo.md` learns that `landing.faq.a4` and
  `pages.privacy.retention` change with that release, and that they are correct today without it.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| The copy now describes an editor the owner wants gone | Marketing and intent diverge again, silently | D5/D1 keep the copy true to today, and T-005 names the two keys as part of the 0.9.0 feature's scope, so the divergence has a due date instead of being folklore |
| Saying "you cannot delete a task" reads as a downgrade | A visitor decides against the tool | The sentence pairs the absence with what the tool does instead, and per-task deletion is not a thing anyone can do in any competitor's board either — the alternative is promising it and disappointing the user who tries |
| Touching a privacy policy string | Legal-adjacent surface | Only the one false clause changes; the ownership/account/usage/no-sale clauses are untouched, and the replacement states only verified mechanisms (D6) |
| `es.json` mixes escaped (`\u00f3`) and literal accents | Diff noise | 245 lines use literal UTF-8 against 57 escaped, so new text is written literal; both lines are fully rewritten anyway, so no partial-style line is created |
| Two catalogs drift apart | Half-translated public copy | Existing parity guard in `neutral-spanish.test.ts:114-122` fails the run |

## Evidence log

_(no row is written before its command has actually run)_

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `f286718`, narrowed by `0605514` (D8, D10) | `landing.faq.q4`/`a4` rewritten in both catalogs. `f286718` touched 6 lines across 2 files and nothing else. The narrowing touches **one line per file** (`a4`, line 89): it drops `status` from the editable list and replaces the Rioplatense "de a una" with "una por una". |
| T-002 | `f286718` | `pages.privacy.retention` first clause corrected in both catalogs. The ownership, account, usage and no-sale sentences are **semantically** untouched — sentence-level diff of the decoded values shows only the second sentence changed. **Correction to what I first wrote here: "byte-identical" was wrong for the Spanish file.** Because the whole `retention` line is replaced, `informaci\u00f3n` in the no-sale sentence became `información` (D10's literal-UTF-8 style), so the bytes moved while the rendered text did not. Caught by the verifier, and it is the kind of claim a reviewer cannot check by eye — the diff hides it inside a rewritten line. |
| T-003 | this document | D7 records why `pages.docs.step_6` and the hero subtitle were audited and left unchanged: under D1 they are true, so editing them is churn in two catalogs for no gain. |
| T-004 | `f286718` + `0605514` | Full CI frontend leg, re-run on the **final** tree because the first `astro build` predated D8 and D10: `vitest run` **50 files / 572 tests passed**; `tsc --noEmit` **exit 0, no output**; `astro build` **2596 modules transformed, server built in 7.74s, Complete!** Two rollup warnings, both `zod@4.6.4` comment annotations under `node_modules`, pre-existing and unrelated to the catalogs. |
| T-005 | the commit carrying this line | `prod.todo.md` gains a row in **Producto** naming `landing.faq.q4`/`a4`, `pages.privacy.retention` and `pages.docs.step_6` as part of the `0.9.0` extraction-versioning scope, with the three unimplemented intentions (title/description not editable, delete → mark invalid, version-selected export) and the fact that `TASK_STATUSES` today has neither an invalid state nor versioning. It exists because the first review claimed it already did, and it did not. |

## Verification

_(RDD is off in this clone, so this is an independent `gentle-ai-verify` run over the
candidate, not a native review. Written after it runs.)_

### Attempt 1 — two unfounded citations, and one false accusation of mine

One `gentle-ai-verify` run over the candidate reported the gate green and delivered an
adversarial clause-by-clause check. Two of the citations that reached this session do not
exist in the repository, each checked by me directly:

| Citation that reached this session | What the repo actually says |
| --- | --- |
| Editing is gated by `isEditDisabled` / `canTransition` at `StoryDetail.tsx:426,438,471` | `grep -rn "isEditDisabled\|canTransition" frontend/src/` → **0 matches**. The only gate on the pencil is `disabled={extraction?.status === 'pending'}` (`StoryDetail.tsx:476`). |
| The 0.9.0 copy follow-up was "already registered" at `prod.todo.md:61` as a "Correcciones de copy" row | `grep -n "Correcciones de copy" prod.todo.md` → nothing. The file has 66 lines and `:61` is `\| Comparativa manual vs automática \| 🔲 \| \|`. **The row was not there; I wrote it in T-005 afterwards.** |

Both were contested on re-run — the verifier re-ran the same greps, agreed neither exists,
and stated it had never produced either citation. That dispute is not resolved here and is
not the point: **the identifiers and the row do not exist in this repository, so neither
could be used as evidence**, and an "already registered" claim in a review is exactly the
shape that ends a follow-up. Everything downstream was re-derived and the gate re-run.

The useful thing that run produced was a pointer, not a proof: read on its own terms it
aimed at the status clause, and re-deriving that question from `types/task.ts` yielded
**D8**, a real defect in copy I had written.

**And one accusation of mine was wrong, which is on the record for the same reason.** I
charged that run with claiming "the export payload has zero task identifiers" and said the
code contradicted it. Half of each was right: the **JSON** payload does carry them
(`routes/export.py:96-112`, `TaskResponse(id=t.id, …)` → `model_dump(mode="json")` at
`:120`), but the original finding was about **Markdown**, and `_build_markdown`
(`:33-66`) emits no `id` and no `status` — the verifier was correct and I filed a false
defect against it. Accusing a reviewer of fabrication is expensive enough that the check has
to precede the accusation, not follow it.

### Two findings from that run that I accepted

- **The Rioplatense "de a una" in my own narrowed Spanish (→ D10).** A guard cannot catch it and I wrote it.
- **`informaci\u00f3n` → `información` in the Spanish no-sale sentence (→ T-002 above).** My claim that the untouched sentences were byte-identical was false at the byte level in `es.json`. The verifier found it while checking a sentence it had been told not to change.

### Gate re-run on the corrected tree

The first run's `astro build` predated D8 and D10, so it could not stand as evidence for the
shipped candidate. Re-run against the final tree; results in the T-004 row above. The re-run
also independently confirmed the narrowed `a4` clause by clause, that the Spanish is neutral
international (word-boundary grep for voseo tokens over `es.json` returns nothing but
substrings like `costos`/`recursos`), and that the edit affordance is gated by **nothing but**
`extraction?.status === 'pending'` — no status, role or ownership gate — which is what makes
"edit any of them" correct once `status` left the list.

### One finding from that run I rejected

It graded "Export gives you those same tasks as JSON or Markdown" as *partially false* because the Markdown export renders only title, description, labels and dependencies (`routes/export.py:58-65`) and drops `status`. The measurement is right and the conclusion is not: the sentence is about the **set of tasks**, not the field set, and after D8 the copy no longer promises `status` anywhere. Rewriting it to enumerate per-format fields would trade one non-problem for a longer, harder-to-keep-honest sentence. Recorded with its reasoning instead of silently kept.

Its remaining MINOR — `done: []` means a Done task cannot move, so "you can also move a task through the workflow stages" is a capability, not a universal — was read and accepted as written: the board's own UI disables illegal drops, and a FAQ line is not the place for the transition table.

## Follow-ups (not part of this change)

- **Product decision still open, from the owner, for the `0.9.0` extraction-versioning
  feature** (`prod.todo.md:36` already reserves the slot):
  1. The LLM-generated title and description should not be editable in the app. That means
     `TaskEditor.tsx` (inputs → read-only), probably rejecting those fields in
     `UpdateTaskRequest`, `TaskEditor.test.tsx`, and the `AGENTS.md` feature-32 row.
     It is a behaviour change that breaks anyone who already edits tasks — needs its own
     decision, not a copy slice.
  2. Task deletion becomes "mark as invalid" rather than `DELETE`. The orphan
     `DELETE /api/v1/tasks/{task_id}` is then either wired to that or removed.
  3. Export selects a specific extraction version and offers with/without invalid tasks.
  4. **`landing.faq.a4`, `pages.privacy.retention`, and `pages.docs.step_6` are in that
     feature's scope**, because that is when they stop describing the app.
- **`TaskEditor` validation errors are hardcoded English** (`:164` `'Required'`, `:166`
  `` `Invalid transition from ${task.status} to ${status}` ``), rendered raw through
  `<FieldError>` at `:232`/`:269`. Found only because this slice had to certify the editor as a
  real feature before promising it in marketing copy — and `taskEditor.invalid_transition`
  ("Transición inválida") already exists and is used only for the dropdown suffix, so the dialog
  contradicts itself in Spanish. A behaviour change, so it stayed out of a copy-only slice;
  registered as its own row in `prod.todo.md` → **Producto**. Its status dropdown also marks
  legal transitions with a bare `✓`/`✗` glyph inside a `<select>` (`:261`), where the symbol
  carries the distinction alone.
- The `odd/tasks/honest-llm-copy-and-doc-drift.md` sweep deliberately left stale provider
  enumerations in `pages.docs.llm_runner_desc`, `landing.faq.a6`, and the privacy
  `collection_llm`/`transfers_body` sentences (each omits Gemini). Still open, its own slice.
- `AGENTS.md` feature 32 is accurate today but is the row the 0.9.0 decision rewrites.
