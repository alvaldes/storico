# trello-export

> **Status**: authorized by the owner on 2026-10-08 — the product decisions were taken the same day
> through a structured questionnaire. Started the same day on branch `feat/trello-export`; **WU1
> (`81e37ee`) and WU2 (`b883425`) both landed**, and WU3 is next. Nothing pushed. The design note that
> precedes this record lives outside the repository, in the second-brain vault
> (`00 - Inbox/Storico — conector Trello — diseño de implementación.md`).
> **Created**: 2026-10-08

## Goal

Implement the Trello export the copy once promised and the code never had: an admin stores the
workspace's Trello credentials, a member sends the workspace's tasks to a new Trello board, and the
board mirrors the Kanban instead of a flat list.

It matters because the repository still asserts the connector exists in two places that are not
copy: `docs/architecture.md:203` (ADR-009, "el conector Trello reutiliza lógica de csv2trello") and
`docs/deployment.md:389` ("Trello connector 🔲 Pendiente"). Until now those lines described an
intention; this feature is what makes them true.

## The owner's decisions

| # | Decision | Answer (2026-10-08) |
| --- | --- | --- |
| D1 | Scope of an export | the admin picks: whole workspace, one project, or one story |
| D2 | Board structure | one list per task status — the five Kanban columns |
| D3 | Re-exporting | a new board every time; duplicates are accepted |
| D4 | Credentials | entered in the UI per workspace, encrypted with Fernet |
| D5 | Execution | asynchronous: `202` + polling, like the extraction |
| D6 | Beyond title and description | the task's labels, and its dependencies as a checklist |
| D7 | Permissions (parent, not asked) | credentials admin-only like `/settings/llm`; **triggering** an export open to any member, like the file export |
| D8 | Exported version (parent, not asked) | only each story's current version, like `api/routes/export.py:100` |

D7 is deliberately split: what needs the admin is the secret, not the export. `GET .../export/tasks`
already lets any member read the same tasks out of the workspace
(`api/routes/export.py:79`, `get_workspace_for_user`), so making the board require an admin would
protect nothing and would contradict the endpoint sitting next to it.

## What was measured before designing

| Claim | Evidence |
| --- | --- |
| No Trello connector exists | `backend/src/storico/infrastructure/` holds `cache, crypto, database, llm, parsers, tasks, vector`; no `trello` module anywhere under `backend/src` or `frontend/src` |
| `trello` was a false option, not an unimplemented one | the export endpoint validated its format and answered `400` for `trello`; the value was then retired in `api/schemas/settings.py:45` and `frontend/src/types/settings.ts:12` (`RETIRED_EXPORT_FORMATS`) |
| The file export is per workspace and current-version only | `api/routes/export.py:76` (route), `:92` (format guard), `:100` (`list_current_by_workspace`) |
| Credentials live per workspace, encrypted | `infrastructure/database/models/workspace_llm_config.py:36` (`api_key`, `String(1000)`); the cipher is `FernetCipher` with the `v1:` prefix (`infrastructure/crypto/fernet_cipher.py`) |
| **The credential cipher belongs to the repository, not to the route** | `SQLAlchemyWorkspaceLLMConfigRepository.__init__(session, cipher)` (`repositories/workspace_llm_config_repository.py:26`) encrypts on write (`:85`) and decrypts on read (`:70`), so "no caller ever holds ciphertext" (`:19-22`); a value that is not ciphertext is tolerated on read, so a row written before encryption existed still reads back (`:58-62`). It is built by a **dedicated factory, not `get_repository`**, because that one injects only a session: `api/dependencies.py:163-170` (`get_llm_config_repository`) with `get_cipher` at `:154`. **This row corrects an earlier version of this record that claimed the opposite** — the first read of the cipher's callers stopped at `head -20` and never reached `repositories/`; the WU1 writer's read refuted it. |
| Cipher failures already have an envelope and a handler | `api/errors.py:290-316`, `api/error_codes.py:84` — a missing or wrong master key answers `500` with an actionable code instead of crashing at import |
| The migration head is `0029` | `infrastructure/database/alembic/versions/0029_story_deletions.py`; its `down_revision` is `0028`, so the next revision is `0030` |
| The Kanban scope rule already exists: never two targets | the board's cascade resolves `project_id`, `user_story_id` or `workspace_id` and answers `422` for two (AGENTS.md, `versioning-visibility`) — the export selector reuses the rule rather than inventing one |
| csv2trello's reusable core, and its gaps | 54 tests across 4 files. `core/trello_client.py`: `py-trello>=0.20.1`, auth passed as `api_secret` to force query-param auth (`:246-258`), rate limit of 300 req/10 s (`:231`), retry with backoff `2**n` only on `ResourceUnavailable` (`:317`), typed errors (`:73-81`). `core/mapper.py`: one board per CSV, a single list named `Backlog` (`:91`), card title `[{PROY}-{US}.{TAREA}] {summary}` (`:163`). Gaps that must not be inherited: `create_card(..., labels=...)` **accepts labels and never sends them** (`:436`, docstring `:444`); no checklists, due dates, or dedup; `core/config.py:79-83` ends the process with `sys.exit(1)`, and the mapper prints through `tqdm` to stdout |
| Background work runs in the API process | `asyncio.create_task` in the event loop, no broker and no worker (AGENTS.md, ADR-004 and feature row 38) |
| The copy already stopped promising Trello | `exportPage.*` in `i18n/en.json` and `i18n/es.json`; `frontend/src/i18n/__tests__/export-copy.test.ts` exists precisely to catch the promise coming back, so WU4 has to change that guard deliberately, not accidentally |

## Design

- **Port**: `domain/ports/trello_export_port.py`, next to `cipher.py` and `llm_port.py`.
  `create_board(cards_by_status, label_names, credentials) -> BoardRef`, implemented in
  `infrastructure/export/trello_adapter.py` over `py-trello`.
- **The adapter owns the four Trello facts** csv2trello measured: the 300 req/10 s window, the
  `2**n` backoff applied only to the retryable error, the typed errors, and the fact that labels are
  a separate API call after the card exists. `py-trello` gets pinned in `backend/pyproject.toml`.
- **Five lists, always, in Kanban order**, even when empty: an empty column is information about the
  workspace, and creating lists conditionally would make two exports of the same data structurally
  different.
- **The card keeps its story in the description**, because D2 chose status lists and there is no list
  per story. The metadata block follows csv2trello's shape (`core/mapper.py:240-244`) rather than
  inventing a new one.
- **Dependencies become checklist items**, resolved with the same rules the Markdown export already
  implements (`api/routes/export.py:_build_markdown`, `resolve_dependency`): an id first, then a
  casefolded title, then the raw reference. An unresolvable reference must render as the reference,
  never disappear.
- **Labels**: every distinct task label becomes a board label, and the color is deterministic from a
  fixed palette, so exporting the same data twice produces the same board. A deterministic choice is
  worth more here than a pretty one.
- **Credentials**: `workspace_trello_configs` — `workspace_id` unique FK, `api_key` and `token` both
  `String(1000)`, timestamps. The repository mirrors the sibling exactly: it takes a `CipherPort`,
  encrypts on write and decrypts on read (`repositories/workspace_llm_config_repository.py:58-105`),
  and is built by its own factory in `api/dependencies.py` next to `get_llm_config_repository`,
  because `get_repository` injects only a session. The admin `GET .../settings/trello` returns the
  decrypted pair, which is the sibling's convention — asserted by
  `tests/test_api/test_workspace_settings_llm_config.py:393` — while `GET .../settings/trello/status`
  copies the `/settings/llm/status` shape: `{configured, missing}` with field names and never a value
  or an endpoint.
- **The job is persisted** in `trello_exports` (id, workspace_id, scope, target id, status,
  `error_code`, `board_url`, `cards_created`, `created_at`, `completed_at`). In-process state would
  be cheaper, but the extraction precedent persists and a restart must not lose the answer the
  member is polling for.
- **Scope is one of three, never two.** Two targets in one request is `422`, the rule the Kanban
  cascade already applies, so the selector cannot be used to export a project and a story at once.
- **The adapter must not block the event loop.** `py-trello` is synchronous and D5 runs the export
  inside the API process (`asyncio.create_task`), so every client call is offloaded with
  `asyncio.to_thread` and the rate window waits with `asyncio.sleep`. A `time.sleep` there would
  stall every request the API is serving, not only the export. csv2trello could afford a blocking
  window because it is a CLI with one job; this is not, and the difference is the whole reason the
  decision is written down here rather than discovered in production.

## Tasks

> **WU3 split when its size was measured, and the numbering after it moved.** The unit as written
> came in at roughly **2,150 added lines** — past the ~900 the note below had set — so it landed as
> two commits along a seam the parent then checked file by file: everything under `domain/`,
> `infrastructure/` and `application/`, the migration, the error codes with their frontend half, and
> the plan and job tests are WU3; the routes, the schemas, the tests that drive them and the
> generated pages are WU4. `api/routes/export.py` deliberately was not split across the two: the
> Markdown export adopting the shared dependency rule rides with the routes, because that is where
> the second consumer of the rule arrives.

- [x] **WU1 — the credentials**: `workspace_trello_configs`, migration `0030`, repository and domain
  port, the admin-only `GET`/`PUT .../settings/trello` plus the member-readable `.../status`, the
  cipher wiring, and the secrets that must never reach a log (backend + tests + `docs/api.md`).
- [x] **WU2 — the port and the adapter**: board, five status lists, cards with labels, dependency
  checklists, rate window, retry and backoff, typed errors, `py-trello` pinned (backend + tests).
- [x] **WU3 — the export job**: `trello_exports`, migration `0031`, the entity, port and repository,
  the pure plan builder, the one dependency rule, the scope resolver, the runner, and the seven
  failure codes with their frontend half (`a21c4e4`). — **the runner clause was refuted by the
  verification of the range; see `## Corrected claims` and the repair unit WU5.**
- [x] **WU4 — the routes**: `POST …/export/trello` → `202` open to any member,
  `GET …/export/trello/{export_id}`, `409` for a workspace with no credentials, the schemas,
  `docs/api.md` and the regenerated reference pages (`32e7cf9`).
- [ ] **WU5 — repair the runner's failure contract.** Found by verifying the range rather than by
  reading it, and it runs before the UI because it is a defect in what already shipped. Three
  blockers: (a) `except Exception` does not catch `asyncio.CancelledError`, which is a
  `BaseException` in this Python, so a cancelled task leaves the row at `running` for good; (b) the
  generic handler stores `INTERNAL_ERROR` with **no** board reference, so a non-typed failure after
  `create_board` loses a board that exists — the exact thing the design section says must not happen;
  (c) `find_by_id` and the `running` write sit outside the `try`, so a database fault there raises
  with the row still `pending`. Fix: keep the board reference in a local the moment it exists and
  use it in every handler; catch `BaseException`, write the terminal state under `asyncio.shield`
  and re-raise a cancellation; and add the startup sweep this job never got, the one
  `recover_stuck_extractions` has had all along (`infrastructure/tasks/extraction_task.py:185`) and
  which the runner's docstring wrongly claimed already covered it.
- [ ] **WU6 — the UI**: scope selector and export on `/export`, the credentials form in the
  workspace settings page, polling, the board link, both locales (frontend + tests).
- [ ] **WU7 — specs and documents**: the OpenSpec capability and the two doc-drift lines that already
  assert the connector exists (`docs/architecture.md:197`, `:203`, `docs/deployment.md:389`) —
  corrected to describe what actually landed.
- [ ] **WU8 — invert the failure-code mapping.**
  `application/export/export_workspace_to_trello.py:32` imports `api/errors.py`, which imports
  FastAPI — **the repository's first and only application→api import**, introduced here and
  documented in that module's docstring as deliberate. The reason it gives is real (one mapping, so
  the job row and the HTTP envelope cannot disagree), but it does not need the coupling: each
  exception can carry its code as a class attribute, with `api/error_codes.py` keeping the literals
  the frontend guard greps for and a test pinning the two together. Small, and worth doing before
  this branch becomes a pull request.

## Non-goals

- **Not two-way.** The board never writes back into Storico: no import of Trello cards, no status
  sync from Trello.
- **Not a designated board.** D3 says a new board per export, so no `board_id` is stored and no
  reconciliation is attempted.
- **Not the other connectors.** Jira, GitHub Projects and Azure DevOps stay where they are.
- **Not a richer card.** No due dates, no assignees, no checklists beyond dependencies (D6).
- **Not a Trello OAuth flow.** The credential is a key and a token an admin pastes; Storico never
  holds the user's Trello password.
- **Not retroactive.** Tasks from a superseded extraction version stay out of the board, exactly as
  they stay out of the file export.

## Limitations to record, not bury

- A repeated export creates a second board. That is D3, not an accident, and the UI should say so
  where the button is.
- Board labels get a deterministic color from a fixed palette; Trello's palette is small, so two
  different labels can share a color.
- A Trello token acts as the person who created it. Revoking it breaks the workspace's export, and
  rotating it is a manual step with no UI beyond the same form.
- The job is persisted but the work runs in the API process: two containers would each run their
  own exports, and nothing coordinates them.
- `py-trello` is a new backend dependency with its own release cadence. It is pinned, and pinning it
  is part of WU2 rather than a follow-up.
- **The export trigger has no rate tier of its own.** `POST …/export/trello` lands on the default
  tier, like every other POST, while the extraction has its own `10/min` bucket
  (`api/rate_limit.py:126`). A flood of triggers is a flood of background jobs holding threads
  against an external API, so an export tier is worth adding — recorded here because `rate_limit.py`
  was not in this unit's surfaces and the omission is not a defect in what landed.
- **WU1's non-blocking review findings, recorded rather than fixed.**
  `TrelloConfigStatusResponse.missing` is an unconstrained `list[str]`, bounded by the route's logic
  rather than by the schema. `_SettingsWithoutAMasterKey` is imported across test modules — fine with
  one consumer, and it belongs in `tests/_helpers.py` when a third appears. And the Postgres-level
  enforcement of `String(1000)` and the `ondelete="CASCADE"` FK is **inspected in source only**:
  Docker is absent in this machine, so the 21 testcontainers integration tests, `test_migration_chain.py`
  among them, skip, and neither the column width nor the cascade is proven against a real database
  here.

## Corrected claims

**The runner's failure contract — refuted 2026-10-08 by the verification of `6c2fdc8..HEAD`.** The
WU3 commit message and this record's task line both said the runner never raises, that every failure
lands in the job row, and that a failure after the board exists keeps its URL. All three are false,
and the verification found them by reading what the code catches rather than what it claims:

| Claim | What the code does |
| --- | --- |
| "Every failure lands in the job row" | `except Exception` does not see `asyncio.CancelledError`, a `BaseException` in this Python, so a cancelled task leaves the row at `running` |
| "A failure after the board exists keeps its URL" | only the typed family does, because only it carries `board_ref`; the generic handler stores `INTERNAL_ERROR` and drops the board |
| "Never raises" | `find_by_id` and the `running` write sit outside the `try`, so a database fault there raises with the row still `pending` |

And the part that is worse than a wrong claim, because it is the claim that hid the hole: the
runner's docstring says a row left at `running` "is what the extraction flow handles with its own
startup recovery". `recover_stuck_extractions` exists in `infrastructure/tasks/extraction_task.py:185`
and is wired at `api/app.py:134`; **nothing equivalent exists for `trello_exports`**, and a `grep`
for it returns nothing. The docstring pointed at a mechanism that covered a different table.

Three times now this feature has produced a text that asserts something the code does not do — the
cipher that belonged to the route, the py-trello message that carried the token, and now a recovery
that was never written. They are recorded instead of quietly fixed because the pattern is the finding:
claims written from memory of the design rather than from reading the code.

## Evidence log

(one row per work unit, added as each lands)

| Work unit | Commit | Evidence |
| --- | --- | --- |
| WU1 — the credentials | `81e37ee` | RED observed first: both new test files failed at collection with `ModuleNotFoundError: No module named 'storico.domain.entities.workspace_trello_config'`; GREEN `22 passed`. Re-run with the LLM-config sibling suites alongside: `53 passed`, which is what proves the shared `__init__` exports were not broken. **Full backend suite on the verified tree: `1364 passed, 45 skipped`** — all 45 environmental (21 × Docker daemon unreachable for testcontainers, 22 × live Qdrant/Ollama opt-ins, 2 × live Ollama chat), so no skip hides a feature path. `ruff check` clean; `ruff format --check` 286 files; `alembic heads` → `0030 (head)`, single. Migration inspected: one `create_table`, `down_revision = "0029"`, `downgrade()` drops exactly what `upgrade()` creates, and every shared column matches `workspace_llm_configs` (`Uuid` PK, unique `Uuid` FK `ondelete="CASCADE"`, `String(1000)`, `DateTime(timezone=True)`). **The load-bearing question was answered by construction, not by assertion**: with `_encrypt` replaced by a pass-through, six tests go red — `tests/test_unit/test_workspace_trello_config_repository.py:87,90` (`startswith("v1:")`), `:147,150` (a re-encrypt must differ from the first ciphertext), `tests/test_api/test_workspace_trello_settings.py:93,95`, `:116`, `:132,133`, `:211-212` (a keyless write must answer `500`, which a pass-through cannot trigger). **A docstring was corrected after verification**: `repositories/workspace_trello_config_repository.py:_to_domain` claimed a row written before encryption existed could be read here, and no such row can exist in a table `0030` creates — comment-only change, with the focused suite and both ruff gates re-run green before the commit. Boundary: 21 paths, all inside the declared surfaces (the delegation under-described the six `__init__.py` files as "the two", and those six are registration only). |
| WU2 — the port and the adapter | `b883425` | RED observed first: the adapter suite failed at collection with `ImportError: cannot import name 'TrelloBoardPlan' from 'storico.domain.entities'`; GREEN `24 passed`. **Full backend suite: `1388 passed, 45 skipped`** (base 1364 + 24 new; the 45 skips are the same environmental set WU1 measured). `ruff check` clean; `ruff format --check` 291 files. **The decisive check was not the suite but the library**: the tests drive an injected fake, and a fake is only as strict as its author made it, so a call real `py-trello` would reject still passes. Audited against the installed 0.20.1 with `inspect`: `List.add_card(labels=...)` **does** send `idLabels`, and it builds that string from `label.id` (`trellolist.py:103-106`), so it needs **objects** — passing strings raises `AttributeError` at runtime, before any request. The adapter passes the `Label` objects `Board.add_label` returns (`trello_adapter.py:170-178`, `:190-195`) and the test asserts identity, so csv2trello's gap is closed rather than inherited. Every other call was matched against the installed signature (`TrelloClient(api_key, api_secret)`, `Board.add_label(name, color)`, `Board.add_list(name, pos)`, `Card.add_checklist(title, items)`, `TrelloClient.add_board(...)`) with no mismatch. Blocking audit: every request call goes through `_call` → `asyncio.to_thread`, every wait through `asyncio.sleep`. Retry: `_MAX_ATTEMPTS=3`, `2**(attempt-1)` = 1 s then 2 s, only for the retryable class, a quota refusal never retried, each attempt counted against the window. Partial failure: all four post-board error kinds carry `board_ref`. **Two claims were corrected after verification, one the parent's and one the writer's.** The adapter docstring and `TrelloExportError`'s rationale asserted that py-trello embeds `key`/`token` in the error URL; the installed 0.20.1 passes them in a separate `params` dict (`trelloclient.py:243-253`), so the messages are already credential-free. The `raise from None` policy stayed, now justified by what it actually buys — a chained cause reaches every traceback a logger prints without passing through anything this module controls. And the credential-hygiene test could not have caught a chaining regression at all, because its blob reads `str`, `repr` and log records and never the cause; two assertions were added and **proven load-bearing by removing ` from None` and watching it go red at `tests/test_unit/test_trello_adapter.py:690`**, then restoring the file byte-identical. |
| WU3 — the export job | `a21c4e4` | RED observed first: all three new test files failed at collection with `ModuleNotFoundError: No module named 'storico.domain.entities.trello_export'`; the frontend guard went red the moment the backend registry grew (mirror missing seven keys, count pin 45 ≠ 52). GREEN: `60 passed` focused, of which **12 are the pre-existing Markdown export tests** — that is the proof the extracted dependency rule changed nothing. `ruff check` clean; `ruff format --check` 304 files; `alembic heads` → `0031 (head)`, single. Design decisions worth keeping: `project_id`/`user_story_id` are **deliberately FK-less**, because a project deleted while its export is being polled must not cascade the row away — the job row survives pointing at something gone, which is the honest state. The migration creates and drops its own enum, following the extraction's pattern. Two test bugs were found and fixed while going green, both of the kind where the test agrees with itself: cards asserted in column 0 while seeded elsewhere, and two tasks sharing a title masking the current-version assertion. **One finding the parent added after reading the code, not the report:** `application/export/export_workspace_to_trello.py:32` imports `api/errors.py`, and `grep` across `application/` and `domain/` shows it is the repository's **only** application→api import — the writer documented it as deliberate and its reason is real, but it drags FastAPI into the application layer, so it became WU7 rather than a footnote. |
| WU4 — the routes | `32e7cf9` | `POST` answers `202` and `GET` answers the job, open to any member (D7), and a workspace with no credentials answers **`409`** rather than starting a job that cannot finish — the conflict-of-state posture the repo already takes for `ACCOUNT_DELETE_BLOCKED`, chosen over `400` and stated rather than assumed. The three red gates before this commit were the generated reference pages (regenerated: 1744 lines each) and `frontend/src/i18n/__tests__/export-copy.test.ts`. **That guard was changed deliberately, and the change is principled rather than convenient:** it asserts that no catalog string names a retired export *format*, which was the same sentence as "names Trello" while Trello was only a retired format — and stopped being the same sentence when the connector became real. It was first scoped to skip the `errorCodes.` namespace (`402336e`), and that turned out to be half a fix: the panel's own copy is about to name Trello legitimately, so the **premise** had to go rather than one namespace at a time. The guard now scans only the keys that present the **download format choice** (`FORMAT_COPY_KEYS`) — which is the bug it was born from, since `trello` was a *selectable* format whose every request answered `400` — and it fails when one of those keys stops resolving, so a rename cannot quietly turn it into a scan of nothing. Proven by flipping both halves at once: renaming `exportPage.format_json` and planting `Format (Trello)` in `exportPage.format_label` turned the two assertions red, and restoring the catalog returned 6/6. Parent's own re-run: the i18n guards green, `tsc` exit 0, `tests/test_api_reference.py` 5 passed. |
