# export-page-rework

> **Status**: authorized by the owner on 2026-10-09; the design decisions E1–E4 below were taken the
> same day in conversation. **Stacked on `feat/trello-export`**, because this rewrites the panel that
> branch just created and cannot be reviewed or merged without it. Nothing pushed.
> **Created**: 2026-10-09

## Goal

One section, four formats, one preview. The export page stops being two unrelated panels — a file
form and a Trello form, each with its own idea of what is being exported — and becomes one toolbar
that states exactly what will be exported, in any of four formats, with the result visible before it
leaves.

## The owner's decisions

| # | Decision | Answer |
| --- | --- | --- |
| E1 | Scope | **one toolbar**: project → story → version, and the project selector carries **all projects**, which is the whole workspace |
| E2 | The editor | **read-only** with a copy button; the file still comes from the server |
| E3 | CSV | **one row per task**, with the story and the version among the columns |
| E4 | Trello's preview | **the board plan as JSON** — the board name, its lists and its cards with their labels |

E1 keeps the workspace scope D1 chose and adds the two levels the board already has. E3 makes this
export three file formats wide, and the fourth is not a file at all.

## What was measured before designing

| Claim | Evidence |
| --- | --- |
| The export page is two sections | `ExportPanel.tsx` renders the file export (`:277-323`) and the Trello section (`:326-462`) with separate state; the file URL is built at `:207-208` |
| **The file export has no scope parameters at all** | `api/routes/export.py:120-125` reads the path `workspace_id` and the query `format`, nothing else; the task read is `list_current_by_workspace` at `:159` |
| **No parameter of either export can choose a version** | the file export filters through `list_current_by_workspace` (`export.py:159`), the Trello one through `list_current_by_{workspace,project,story}` (`application/export/export_workspace_to_trello.py:326-343`); the version predicate is the repository's `_current_version_only` (`task_repository.py:54-77`) |
| The Trello export already takes two scope targets and refuses two | `body.project_id`/`body.user_story_id` (`export.py:340-347`) through `resolve_export_scope` (`application/export/export_workspace_to_trello.py:70-86`) → `422` |
| **CSV has no serializer, in either direction of the frontend** | honest count **0**: `backend/src` holds only the importer (`infrastructure/parsers/story_csv.py:120`) and `frontend/src` only the import path (`lib/stories-api.ts:58-77`) |
| The copy-to-clipboard pattern exists once | `ErrorDisplay.tsx:50` (`navigator.clipboard.writeText`) inside a collapsible error disclosure; `grep clipboard` finds nothing else, so there is no helper to import |
| The versions of a story are already readable | `GET /api/v1/stories/{story_id}/versions` (`api/routes/stories.py:308`) returns a bare array with `id`, `version_number`, `is_current` (`:347-361`); the frontend consumes it through `lib/versioning-api.ts:60` into `VersionSelector.tsx` |
| **The cascade has no shared implementation** | `KanbanBoard.tsx` owns one (`:101-105`, `:203-223`, `:462-480`) and `ExportPanel.tsx` re-implements another (`:56-150`); the only reusable pieces are `resolveTrelloExportTarget` (`lib/trello-api.ts:160`), `VersionSelector.tsx` and `lib/context-treatment.ts` |
| The format selector's copy is guarded by name | `i18n/__tests__/export-copy.test.ts:91-93` lists the keys the guard reads, so `exportPage.format_csv` has to join that list deliberately |
| The FAQ promises CSV as unreleased | `i18n/en.json:152` and `es.json:152` say CSV and XML export are on the roadmap; CSV stops being true the day this lands |

## Design

- **One serialization, two dispositions.** The preview and the download must not be two code paths:
  `preview=true` on the same endpoint returns the same body without the attachment header, so what the
  editor shows cannot differ from what the browser saves. A preview assembled in the frontend, or in a
  second endpoint, is the same file built twice and free to disagree.
- **The Trello preview is the plan, and creates nothing.** `GET …/export/trello/preview` returns the
  same `TrelloBoardPlan` the runner would send, serialized, with no job row: an export that only
  describes itself must not cost a board.
- **One scope rule for both exports.** `resolve_export_scope` is the rule already written and tested
  for Trello; the file export adopts it rather than growing a second resolver with the same three
  branches. It moves to a neutral module, with the values it stores and returns unchanged — the job
  row's `scope` column and the API's `scope` field must keep the exact spellings they have today.
- **A version belongs to a story.** `extraction_id` is accepted only together with `user_story_id`;
  asking for a version without its story is `422`, the same shape as asking for two targets. The
  version is identified by the extraction id, not by the version number: numbers are positions in a
  history that a new run moves, and an export must not silently follow them.
- **CSV is one row per task**: `story, version, title, description, status, priority, labels,
  dependencies`, written through the `csv` module so a description with newlines survives, with
  multi-value cells separated by `;`. The column order is a contract: a file people parse stops being
  free to change, so it is written down here and in the spec.
- **The copy button becomes a thing.** There is no helper to import, and the preview needs one; it
  becomes a small shared component. Moving `ErrorDisplay` onto it happens only if the change is
  mechanical — otherwise the duplication is recorded, because an error disclosure is not the same
  shape as a code block and pretending otherwise is how a shared component turns into a switchboard.
- **The toolbar follows the board's cascade in behaviour, not by copy.** Most-specific-wins, one
  target always, and the version selector is disabled unless a story is chosen — with the same
  resolver the Trello body already uses, so the frontend cannot build two targets to begin with.

## Tasks

- [x] **EP1 — the export contract grows a scope, a version and a format.** `project_id`,
  `user_story_id`, `extraction_id` and `format=csv` on `GET …/export/tasks`; the shared scope rule;
  a version predicate; the CSV serializer; its tests; `docs/api.md`.
- [ ] **EP2 — the preview.** `preview=true` on the file export (same body, no attachment header) and
  `GET …/export/trello/preview` returning the plan with no job created.
- [ ] **EP3 — the Trello export accepts a version.** The trigger body and the plan take the chosen
  version, and the job row records which one it exported.
- [ ] **EP4 — the UI: one section.** The toolbar (project → story → version, with all projects), the
  four formats in order — CSV, JSON, MD, Trello — the read-only preview with its copy button, the
  existing poll and board link folded into that one section, both locales and the guard's key list.
- [ ] **EP5 — specs and documents.** The OpenSpec capabilities (this export gains a scope, a version
  and a third format; the Trello one stops being current-version-only), `docs/api.md`'s remaining
  rows, the FAQ copy that calls CSV unreleased, the regenerated reference pages, and the amendment
  D8 needs in `odd/tasks/trello-export.md`.

## Non-goals

- **Not an editable preview.** E2 is explicit: the text is shown and copied, never submitted back.
- **Not a version at project or workspace level.** A version belongs to a story; widening that would
  mean exporting two versions of three stories and answering a question nobody asked.
- **Not XML**, which stays where it is.
- **Not a second scope resolver**, and not a second serialization for the preview.
- **Not a refactor of the board's cascade.** Extracting one cascade and landing both pages on it is a
  real improvement and its own unit: the board has cascade tests and a URL-seeding contract that this
  feature has no reason to put at risk.

## Limitations to record, not bury

- **The cascade stays duplicated** between the board and this page until that unit exists. The
  resolver is shared; the selection state and the option loading are not.
- **A chosen version's export is a snapshot.** Exporting `v2` after `v3` completed gives the tasks as
  that run left them, which is the point — but the file carries the version number, and a file without
  one is only as good as its timestamp.
- **CSV columns are a contract.** Adding a column later is compatible; renaming or reordering one is
  not, and this record is where that is stated rather than discovered by whoever parses it.
- **The workspace scope has no version**, by construction, so the toolbar's third selector is empty
  exactly when the scope is widest.
- **The preview costs a request per format change.** It shares the export's work, so a large
  workspace pays the serialization twice — once to look, once to save. Debouncing is a UI decision,
  and no caching is added without a measurement that asks for it.

## Evidence log

(one row per work unit, added as each lands)

| Work unit | Commit | Evidence |
| --- | --- | --- |
| EP1 — the export contract | `548fcac` | RED observed first: the new scope suite failed at collection (`ModuleNotFoundError: No module named 'storico.domain.services.export_scope'`) and the export suite showed 14 new failures — the scope parameters ignored entirely, whole workspace exported whichever target you asked for, and `csv` answering `400` — while the 13 existing json/markdown tests passed untouched. GREEN: 71 across the four focused files; **full suite 1469 passed, 45 skipped**; `ruff` clean; `tests/test_api_reference.py` 5 passed after regenerating both pages (1768 lines each, only the export-tasks entry changed). The refusal order is the contract and reads top to bottom in the route: `400` unknown format → `422` two targets → `422` a version without its story → `403`/`404` a target outside the workspace. **The storage spellings were the risk and got their own proof**: `TestScopeSpellingsAreTheStoredContract` pins `workspace`/`project`/`story`, because the job row writes `scope.value` and reads it back through `TrelloExportScope(model.scope)` — renaming one string would silently change what every historical job row means. `list_by_story_version` keeps **both** filters in the `WHERE`, so an extraction id from another story matches nothing instead of leaking that story's tasks into a story-scoped export. JSON and Markdown keep their own branches and their old tests pass unchanged, which is the acceptance criterion rather than a hope. **Two references were corrected afterwards, both by the parent**: a `(D9)` comment citing a decision that exists in no record, and a docstring still pointing at `(application/export)` for a resolver that had moved. | |
