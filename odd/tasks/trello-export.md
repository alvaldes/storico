# trello-export

> **Status**: authorized by the owner on 2026-10-08 — the product decisions were taken the same day
> through a structured questionnaire. Started the same day on branch `feat/trello-export`. Nothing
> pushed. The design note that precedes this record lives outside the repository, in the second-brain
> vault (`00 - Inbox/Storico — conector Trello — diseño de implementación.md`).
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

## Tasks

- [ ] **WU1 — the credentials**: `workspace_trello_configs`, migration `0030`, repository and domain
  port, the admin-only `GET`/`PUT .../settings/trello` plus the member-readable `.../status`, the
  cipher wiring, and the secrets that must never reach a log (backend + tests + `docs/api.md`).
- [ ] **WU2 — the port and the adapter**: board, five status lists, cards with labels, dependency
  checklists, rate window, retry and backoff, typed errors, `py-trello` pinned (backend + tests).
- [ ] **WU3 — the job and the routes**: `trello_exports` + migration `0031`,
  `POST …/export/trello` → `202`, `GET …/export/trello/{export_id}`, the scope resolver, and
  current-version-only export (backend + tests).
- [ ] **WU4 — the UI**: scope selector and export on `/export`, the credentials form in the
  workspace settings page, polling, the board link, both locales and the new error codes
  (frontend + tests).
- [ ] **WU5 — specs and documents**: the OpenSpec capability, `docs/api.md`'s remaining rows, and the
  two doc-drift lines that already assert the connector exists (`docs/architecture.md:197`, `:203`,
  `docs/deployment.md:389`) — corrected to describe what actually landed.

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

## Evidence log

(one row per work unit, added as each lands)

| Work unit | Commit | Evidence |
| --- | --- | --- |
| | | |
