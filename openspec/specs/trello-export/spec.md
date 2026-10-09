# trello-export Specification

## Purpose

Export a workspace's current-version tasks to a new Trello board, asynchronously,
using per-workspace credentials an admin stores encrypted. The feature is
specified against the code that carries it: the port
`backend/src/storico/domain/ports/trello_export_port.py`, the adapter
`backend/src/storico/infrastructure/export/trello_adapter.py`, the routes in
`backend/src/storico/api/routes/export.py` and
`backend/src/storico/api/routes/workspace_trello.py`, migrations `0030`
(`workspace_trello_configs`) and `0031` (`trello_exports`), and the browser
surface `frontend/src/lib/trello-api.ts`,
`frontend/src/components/react/TrelloCredentialsForm.tsx` and
`frontend/src/components/react/ExportPanel.tsx`.

## Requirements

### Requirement: Per-Workspace Trello Credentials

The system MUST store one credential pair (Trello API key and token) per
workspace, in the `workspace_trello_configs` table created by migration `0030`,
both columns encrypted at rest. The repository
(`backend/src/storico/infrastructure/database/repositories/workspace_trello_config_repository.py`)
MUST take a `CipherPort`, encrypt on write and decrypt on read, so no caller
ever handles ciphertext and the column never stores plaintext.

`PUT /api/v1/workspaces/{workspace_id}/settings/trello` and
`GET /api/v1/workspaces/{workspace_id}/settings/trello` MUST require the
workspace `admin` role and MUST return the decrypted pair. An omitted field on
`PUT` MUST preserve the stored value; a blank value MUST be stored as absent.

`GET /api/v1/workspaces/{workspace_id}/settings/trello/status` MUST be readable
by any workspace member and MUST report `{configured, missing}` with the
**names** of the missing fields (`api_key`, `token`) — never a credential value
or an endpoint URL.

A stored row MUST survive a server without a master key configured in a defined
way, not a crash: writing answers `500` with `ENCRYPTION_KEY_MISSING`, and
reading an already-encrypted row answers `500` with `CREDENTIAL_UNDECRYPTABLE`,
both in the canonical error envelope.

#### Scenario: Admin stores and reads back the pair

- **GIVEN** a workspace admin
- **WHEN** they `PUT` an API key and token to `/settings/trello`
- **THEN** the pair is stored encrypted and a following `GET` returns it decrypted

#### Scenario: A member can check status but never read the pair

- **GIVEN** a workspace member (non-admin) and a stored credential pair
- **WHEN** they call `GET /settings/trello/status`
- **THEN** the response reports `configured: true` and names no missing fields
- **AND** `GET /settings/trello` refuses them, and no response ever carries a credential value

### Requirement: Export Trigger — asynchronous, scoped, member-accessible

`POST /api/v1/workspaces/{workspace_id}/export/trello` MUST be open to any
workspace member (D7): the admin-only surface is the credential pair, not the
export, which reads the same tasks `GET .../export/tasks` already lets any
member read. The endpoint MUST create a job row in `trello_exports` (migration
`0031`), dispatch the work with `asyncio.create_task` in the API process (no
Celery, no Redis — D5), and answer `202` immediately with the job.

The scope MUST be exactly one of three (D1): no target exports the whole
workspace; `project_id` exports one project; `user_story_id` exports one story.
A body carrying both `project_id` and `user_story_id` MUST be refused with
`422 REQUEST_VALIDATION_FAILED` — the rule the Kanban cascade already applies.
A target that exists but does not belong to the path workspace MUST be refused.

Only each story's **current** extraction version's tasks MUST be exported (D8),
the same filter the file export applies. Tasks of superseded versions MUST NOT
appear on the board.

A workspace with no complete credential pair stored MUST answer
`409 TRELLO_CREDENTIALS_MISSING` before any job row is created — a state
conflict, not a malformed request. Half a pair (one credential present, the
other absent) counts as not configured.

#### Scenario: A member exports the whole workspace

- **GIVEN** a workspace with credentials and tasks across several projects
- **WHEN** a member POSTs to `/export/trello` with no target
- **THEN** the response is `202` with a job whose `status` is `pending`
- **AND** the board covers the current-version tasks of every story in the workspace

#### Scenario: Two targets in one request are refused

- **GIVEN** a workspace with credentials
- **WHEN** a POST carries both `project_id` and `user_story_id`
- **THEN** the backend answers `422 REQUEST_VALIDATION_FAILED` and creates no job

#### Scenario: No credentials is a conflict, not a start

- **GIVEN** a workspace whose Trello credentials were never stored
- **WHEN** a member POSTs to `/export/trello`
- **THEN** the backend answers `409 TRELLO_CREDENTIALS_MISSING` and no job row exists

### Requirement: Job Lifecycle and Polling

`GET /api/v1/workspaces/{workspace_id}/export/trello/{export_id}` MUST be
readable by any workspace member and report the job: `status`, `board_url`,
`error_code`, `cards_created`. The status MUST move through `pending` and
`running` to one of the two terminal states, `completed` or `failed`;
`completed_at` is stamped exactly when the state becomes terminal. A job whose
id exists but belongs to another workspace MUST be reported as `404
TRELLO_EXPORT_NOT_FOUND` — a foreign id is not distinguishable from an absent
one.

On `completed`, `board_url` MUST carry the created board and `cards_created`
the number of cards written. On a `failed` job, `error_code` MUST name the
failure, and when the failure happened **after** the board was created,
`board_url` MUST still carry the partially built board: a member must never be
left with a board they cannot find.

#### Scenario: The member polls until the board exists

- **GIVEN** a triggered export
- **WHEN** the member polls `GET .../export/trello/{export_id}` until the status stops changing
- **THEN** the terminal status is `completed` with a `board_url` and a `cards_created` count

#### Scenario: A failure after the board was created keeps the board visible

- **GIVEN** an export whose board was created but whose card writes then fail
- **WHEN** the job reaches its terminal state
- **THEN** the status is `failed` with a typed `error_code` and the `board_url` of the half-built board

### Requirement: Board Shape

Every export MUST create a **new** board (D3): re-exporting never overwrites or
reconciles a previous board, and duplicates are accepted. The board name is the
workspace's name.

The board MUST always have the five Kanban lists, in canonical `TaskStatus`
order, even when empty — an empty column is information about the workspace,
and conditional lists would make two exports of the same data structurally
different. Each task becomes a card in its status's list, with its title as the
card name, its description plus a story-attribution metadata block (csv2trello's
shape, story text preview truncated at 100 characters) as the card description,
every distinct task label as a board label (created with a deterministic color
from a fixed palette, so the same data exports to the same colors), and its
dependencies as checklist items resolved by the shared rule — an id first, then
a casefolded title, then the raw reference. An unresolvable dependency MUST
render as the reference text, never disappear.

#### Scenario: The board mirrors the Kanban

- **GIVEN** a workspace with tasks in several statuses, with labels and dependencies
- **WHEN** the export completes
- **THEN** the board has five lists in Kanban order, each task is a card in its status's list carrying its labels and a dependency checklist, and every distinct label exists as a board label

#### Scenario: Re-exporting creates a second board

- **GIVEN** a workspace exported once successfully
- **WHEN** the same scope is exported again
- **THEN** a second, independent board is created and the first is untouched

### Requirement: Failure Contract, including the Startup Sweep

Every Trello failure MUST be typed and mapped to exactly one error code, shared
by the job row and the HTTP envelope:

- `TRELLO_CREDENTIAL_REJECTED` — Trello refused the stored key or token
- `TRELLO_SERVICE_UNAVAILABLE` — Trello unreachable
- `TRELLO_RATE_LIMIT_EXHAUSTED` — retry attempts exhausted against the rate window
- `TRELLO_BOARD_REFUSED` — Trello refused the board creation
- `TRELLO_CARD_REFUSED` — Trello refused a card after the board existed (carries `board_ref`)
- `TRELLO_EXPORT_INTERRUPTED` — the job was cancelled or swept by startup recovery
- `TRELLO_EXPORT_NOT_FOUND` — the polled id is absent or foreign (404)
- `TRELLO_CREDENTIALS_MISSING` — the trigger refused a workspace with no pair (409)

The runner MUST never leave a job row without a terminal state: a cancelled
task MUST write `failed`/`TRELLO_EXPORT_INTERRUPTED` (under `asyncio.shield`,
so the write survives the cancellation) and re-raise; a non-typed failure MUST
land as `failed` with `INTERNAL_ERROR`, keeping the board reference when one
exists. `py-trello` is synchronous, so every client call MUST be offloaded with
`asyncio.to_thread` and every wait with `asyncio.sleep` — the export runs on the
API's event loop and must never block it.

At application startup, the sweep (`infrastructure/tasks/trello_export_task.py`,
wired in the same lifespan block as the extraction's recovery) MUST mark every
`pending` or `running` job older than the age bound as `failed` with
`TRELLO_EXPORT_INTERRUPTED`, so a job stranded by a crash or a cancelled task
answers a poll instead of leaving the member waiting forever. It inherits the
extraction sweep's age limitation: a row younger than the bound at boot waits
for the next boot.

#### Scenario: A crash-stranded job is swept at the next boot

- **GIVEN** a job row left at `running` by a process that died mid-export, older than the age bound
- **WHEN** the application starts
- **THEN** the sweep marks the row `failed` with `error_code: TRELLO_EXPORT_INTERRUPTED`, and the next poll gets an answer instead of waiting

#### Scenario: A cancelled export still answers

- **GIVEN** an export task cancelled while running
- **WHEN** the cancellation unwinds
- **THEN** the row lands `failed` with `TRELLO_EXPORT_INTERRUPTED` and the `CancelledError` re-raises out of the task

### Requirement: Accepted Limits

The feature accepts these limits on purpose, and documents must not describe
them as gaps to fix silently:

- **A new board per export** (D3). No `board_id` is stored, no board is
  designated, and no reconciliation is attempted. A repeated export duplicates.
- **Not two-way.** The board never writes back: no card import, no status sync
  from Trello. The other connectors (Jira, GitHub Projects, Azure DevOps) stay
  unimplemented.
- **No richer card.** No due dates, no assignees, and no checklists beyond the
  dependency checklist (D6).
- **No request timeout in the pinned `py-trello`.** The adapter pins
  `py-trello>=0.20.1` and does not build a custom `http_service`; a hung Trello
  request holds one worker thread and its task, not the event loop.
- **A reload loses the poll.** The client persists no job id, so a member who
  reloads while an export runs cannot resume watching it; the job keeps running
  server-side and the board still gets created — what is lost is the progress view.
- **One container.** The sweep and the dispatch run in the API process; a second
  container would run its own exports and sweep, with nothing coordinating them.
- **No rate tier of its own.** The trigger lands on the default rate tier, like
  every other POST.
