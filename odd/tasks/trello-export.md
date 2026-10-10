# trello-export

> **Status**: authorized by the owner on 2026-10-08 — the product decisions were taken the same day
> through a structured questionnaire, and **WU1 through WU10 all landed**, so the feature is complete
> on branch `feat/trello-export`. The chain is applied on the **dev** database (`0031 (head)`, `alembic
> check` clean); **production is untouched** and the deploy applies migrations in its own window.
> **Nothing is pushed**: push, pull request and merge are the owner's decisions. The design note that
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

> **Amendment (2026-10-09) — D8 was replaced.** "Only each story's current version" was the rule
> when this feature landed and remains the **default**, but it is no longer the only answer: the
> Trello trigger now accepts `extraction_id` beside `user_story_id` and exports the named version
> even when a newer run superseded it, the job row records which `extraction_id` it exported, and
> one pairing rule (`extraction_id` without its story answers `422`) governs all three export
> routes — file, trigger and preview. The export page rework replaced it: decision E1 and work
> unit EP3 in `odd/tasks/export-page-rework.md`. The decision rows above stay as history,
> unrewritten.

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
- [x] **WU5 — repair the runner's failure contract.** Found by verifying the range rather than by
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
  which the runner's docstring wrongly claimed already covered it. **Where the sweep deviates from
  the extraction's** (also stated in the sweep module's docstring): it sweeps `running` as well as
  `pending`, because a cancelled task strands the row there — the extraction only sweeps `pending`;
  it bounds the status in the query (`TrelloExportRepository.find_by_statuses`) and filters only the
  age in Python with the same `_as_utc` guard, where the extraction lists every row and filters both
  in Python; it writes the code `TRELLO_EXPORT_INTERRUPTED` instead of free-text `error_info`;
  it inherits the extraction's age limitation — a row younger than the bound at boot waits for the
  next boot. Evidence in the log below.
- [x] **WU6 — the UI**: scope selector and export on `/export`, the credentials form in the
  workspace settings page, polling, the board link, both locales (frontend + tests) — `7436da1`.
- [x] **WU7 — specs and documents**: the OpenSpec capability and the two doc-drift lines that already
  assert the connector exists (`docs/architecture.md:197`, `:203`, `docs/deployment.md:389`) —
  corrected to describe what actually landed. — **done; see the evidence row, which also records the
  drift WU5 left in `docs/api.md` and the stale rows the search found outside this unit's claim list.**
- [x] **WU8 — invert the failure-code mapping.**
  `application/export/export_workspace_to_trello.py:32` imports `api/errors.py`, which imports
  FastAPI — **the repository's first and only application→api import**, introduced here and
  documented in that module's docstring as deliberate. The reason it gives is real (one mapping, so
  the job row and the HTTP envelope cannot disagree), but it does not need the coupling: each
  exception can carry its code as a class attribute, with `api/error_codes.py` keeping the literals
  the frontend guard greps for and a test pinning the two together. Small, and worth doing before
  this branch becomes a pull request.
- [x] **WU9 — close the findings both verifications left open.** Listed in
  `## Findings the verifications left open`, which is the authoritative list. The one that matters
  is the shield: it is load-bearing and nothing tests it.
- [x] **WU10 — repair `0031`'s enum creation.** Found by applying the chain to a real database rather
  than by reading it: the revision created the type explicitly and then let `create_table` create it a
  second time inside the same transaction, which PostgreSQL refuses. One keyword — `create_type=False`,
  matching what the model already declares — with the reason written in the file, because the next
  reader will be tempted to put it back. — **done; findings 1–4 and 6 are closed
  (4 on the Trello sweep only — the extraction sweep is another feature's code), 5 accepted, 7–10
  left as stated; see the evidence row.**

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
  they stay out of the file export. — **Amended 2026-10-09** (EP3 of
  `odd/tasks/export-page-rework.md`): true by default only — a version chosen by `extraction_id`
  beside its story exports the tasks as that run left them, and the job row records which one.

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
- **A reload loses the poll.** No job id is persisted client-side, so a member who reloads while an
  export is running cannot resume watching it: the job keeps running server-side and the board still
  gets created, but the page has forgotten it. Trello still ends up with the board; what is lost is
  the progress view. Consistent with the extraction precedent (D5), and recorded rather than
  implied.
- **WU1's non-blocking review findings, recorded rather than fixed.**
  `TrelloConfigStatusResponse.missing` is an unconstrained `list[str]`, bounded by the route's logic
  rather than by the schema. `_SettingsWithoutAMasterKey` is imported across test modules — fine with
  one consumer, and it belongs in `tests/_helpers.py` when a third appears. And the Postgres-level
  enforcement of `String(1000)` and the `ondelete="CASCADE"` FK is **inspected in source only**:
  Docker is absent in this machine, so the 21 testcontainers integration tests, `test_migration_chain.py`
  among them, skip, and neither the column width nor the cascade is proven against a real database
  here.

## Findings the verifications left open

Every item below was found by an independent verification **reading what the code does**, and none
of them is blocking. They are listed with the reason they are not being fixed on the spot, because
"non-blocking" is a scheduling decision and not a verdict.

1. **The `asyncio.shield` is load-bearing and no test covers it.** Replacing both shield call sites
   with a direct `await` leaves all four contract tests **green**. An independent double-cancel
   experiment settled what that means: with the shield the row lands `failed`/
   `TRELLO_EXPORT_INTERRUPTED`, without it the row stays `running`. So the shield is the difference
   between a member getting an answer and waiting forever, and the suite would not notice its
   removal. **This is the fourth assertion in this feature that accompanies the implementation
   instead of guarding it**, and the reason is the same every time: the test was written by the same
   pass that wrote the code. WU9 adds the double-cancel test. — **closed by WU9.**
2. **The two terminal writes are unguarded while `_mark_interrupted`'s is not.** A fault in the
   typed or generic handler's own `save` escapes the task, which the module docstring's unqualified
   "every failure must land in it" does not admit. The asymmetry is the finding: the same author
   guarded one write and not the other two. The sweep is the backstop, which is why it is not
   blocking. WU9 guards them and rewrites that sentence. — **closed by WU9.**
3. **`except TrelloExportError` dereferences `job` with no `None` guard.** Unreachable today — the
   early return covers the only way `job` can be `None` — and latent. One line, in WU9. — **closed
   by WU9: guard added, deliberately without a test** — any test would have to fake an impossible
   state (a `find_by_id` that returns `None` and a port that still runs), exercising the fake rather
   than the code.
4. **The sweep aborts on a per-row fault**, leaving later rows for the next boot. Identical to
   `recover_stuck_extractions` (`infrastructure/tasks/extraction_task.py:209`), so it is inherited
   rather than introduced here. Accepted as is; WU9 may align both or leave both. — **closed by WU9
   on the Trello sweep only** (guarded, continues, logged, documented as the sweep module's fourth
   deviation); the extraction sweep is another feature's code and this branch does not own it.
5. **The age bound is a real wait.** A row stranded minutes before a restart is only swept at the
   *next* boot, so the poller sees `running` in the meantime. Stated in the module and here; not a
   defect, a cost this design chose.
6. **N1's resolution assertion is tautological, and this corrects the record's own phrasing about
   it.** `job.workspace_id == seeded.workspace_id` cannot fail, because the route stamps the path
   workspace onto the row. What the test actually catches is a *refusal* regression — a project that
   is not the workspace's only one being rejected — and no test covers a story resolved to the wrong
   workspace. The earlier sentence here over-claimed what N1 bought; this is what it bought. —
   **closed by WU9**: the member-trigger test's tautology was deleted (no coverage lost — the row's
   workspace binding is stamped from the path by the route under test, and cross-workspace read
   isolation is `test_another_workspaces_job_is_not_readable`), and the story-resolution test's
   tautology was replaced with `job.project_id is None`, which can fail and pins the never-two-targets
   rule on the persisted row.
7. **A slow but alive export at boot is swept.** The age bound cannot tell a live export from a dead
   one. In one container it cannot happen — nothing of ours is running before startup finishes — so
   this presupposes the multi-container case the record already declines to support.
8. **The Postgres enum binding of `find_by_statuses` was unverified — closed 2026-10-09, and closing it
   found a defect.** Applying the chain to a real database failed `0031` with a duplicate-object error
   on its own enum: the revision created the type explicitly *and* let `create_table` create it again.
   **Fixed in WU10**, and the same database then answered everything this item asked for: the enum's
   four labels in domain order, both FKs `CASCADE`, `api_key`/`token` measured at 1000,
   `find_by_statuses` executing, `alembic check` clean, `downgrade`/`upgrade` round-tripping. So the
   gap was real, and it was hiding a revision that could not be applied at all.
9. **`frontend/docs/design-brief.md` describes a Trello the product did not build** — a Trello OAuth
   flow, the connector as a pending checkbox, and `trello` as a download format. It is a design
   document written before the feature, and the design that landed differs from it on purpose: the
   credential is a pasted key and token, never OAuth, and every export creates a new board rather
   than updating a designated one. **Found by WU7's drift search and left alone deliberately**: it is
   not this feature's drift, and correcting a design brief is a decision about what that document is
   for, not a factual correction.
10. **`docs/deployment.md`'s Rate limiting row still reads `🔲 Pendiente`** while `AGENTS.md` row 42
    records it implemented and wired on 2026-10-07. A different feature's drift, surfaced by the same
    search. Left for its own commit for the same scope reason — a Trello branch that fixes the rate
    limiter's documentation is a branch whose story no longer matches its name.

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
| WU3 — the export job | `a21c4e4` | RED observed first: all three new test files failed at collection with `ModuleNotFoundError: No module named 'storico.domain.entities.trello_export'`; the frontend guard went red the moment the backend registry grew (mirror missing seven keys, count pin 45 ≠ 52). GREEN: `60 passed` focused, of which **12 are the pre-existing Markdown export tests** — that is the proof the extracted dependency rule changed nothing. `ruff check` clean; `ruff format --check` 304 files; `alembic heads` → `0031 (head)`, single. Design decisions worth keeping: `project_id`/`user_story_id` are **deliberately FK-less**, because a project deleted while its export is being polled must not cascade the row away — the job row survives pointing at something gone, which is the honest state. The migration creates and drops its own enum, following the extraction's pattern. Two test bugs were found and fixed while going green, both of the kind where the test agrees with itself: cards asserted in column 0 while seeded elsewhere, and two tasks sharing a title masking the current-version assertion. **One finding the parent added after reading the code, not the report:** `application/export/export_workspace_to_trello.py:32` imports `api/errors.py`, and `grep` across `application/` and `domain/` shows it is the repository's **only** application→api import — the writer documented it as deliberate and its reason is real, but it drags FastAPI into the application layer, so it became a task of its own rather than a footnote — numbered WU8 after the WU3 split moved the numbering (the "WU7" an earlier version of this row named was the pre-split number). |
| WU4 — the routes | `32e7cf9` | `POST` answers `202` and `GET` answers the job, open to any member (D7), and a workspace with no credentials answers **`409`** rather than starting a job that cannot finish — the conflict-of-state posture the repo already takes for `ACCOUNT_DELETE_BLOCKED`, chosen over `400` and stated rather than assumed. The three red gates before this commit were the generated reference pages (regenerated: 1744 lines each) and `frontend/src/i18n/__tests__/export-copy.test.ts`. **That guard was changed deliberately, and the change is principled rather than convenient:** it asserts that no catalog string names a retired export *format*, which was the same sentence as "names Trello" while Trello was only a retired format — and stopped being the same sentence when the connector became real. It was first scoped to skip the `errorCodes.` namespace (`402336e`), and that turned out to be half a fix: the panel's own copy is about to name Trello legitimately, so the **premise** had to go rather than one namespace at a time. The guard now scans only the keys that present the **download format choice** (`FORMAT_COPY_KEYS`) — which is the bug it was born from, since `trello` was a *selectable* format whose every request answered `400` — and it fails when one of those keys stops resolving, so a rename cannot quietly turn it into a scan of nothing. Proven by flipping both halves at once: renaming `exportPage.format_json` and planting `Format (Trello)` in `exportPage.format_label` turned the two assertions red, and restoring the catalog returned 6/6. Parent's own re-run: the i18n guards green, `tsc` exit 0, `tests/test_api_reference.py` 5 passed. |
| WU5 — the runner's failure contract repaired | `6dcea48` | **RED observed twice, at two levels.** First with the new tests alone and the code untouched: `pytest -q tests/test_unit/test_trello_export_job.py tests/test_unit/test_trello_export_recovery.py tests/test_api/test_trello_export.py` → **2 collection errors** (`ImportError: cannot import name 'TRELLO_EXPORT_INTERRUPTED'`). Then with only the registry entry + its frontend half added (so the modules could import) and the runner still unfixed: `pytest -q tests/test_unit/test_trello_export_job.py` → **4 failed, 18 passed** — each failure is one reproduced defect: the real-cancel test left the row `running`; the cancel-after-board test left it `running` with no board; the non-typed-failure test stored `INTERNAL_ERROR` with `board_url=None`; and the pre-work database fault propagated `RepositoryError` out of the runner. The sweep suite stayed at its collection error (`cannot import name 'trello_export_task'`). **GREEN:** after the runner rewrite, the sweep (`infrastructure/tasks/trello_export_task.py`), the port's `find_by_statuses` and the lifespan wiring: the same three files → **40 passed**. **Gates:** full backend suite `pytest -q` → **1444 passed, 45 skipped** — the same environmental skip set every unit has measured (21 × Docker daemon unreachable for testcontainers, the rest live Qdrant/Ollama opt-ins), none hiding a feature path. `ruff check` clean; `ruff format --check` 306 files (three reformat of this unit's own files first). Frontend half: `vitest run src/lib/__tests__/error-codes.test.ts src/i18n` → **89 passed (7 files)**; `tsc --noEmit` exit 0. **The new failure code moved with its frontend half in the same unit**: `TRELLO_EXPORT_INTERRUPTED` added to the registry (a swept or cancelled job was never a typed Trello failure, and `INTERNAL_ERROR`'s copy — "something went wrong on the server" — does not tell the member the truth, which is that the export can simply be re-triggered), both locales (neutral Spanish: "La exportación se interrumpió antes de terminar. Actívala de nuevo para reintentarlo"), and the count pin 52 → 53. **The cancellation tests cancel for real**: `task.cancel()` on a live `asyncio.create_task` of the runner, with the port or the completion write held at an event gate, and the test asserts the `CancelledError` re-raises out of the task — so a runner that swallowed the cancellation would fail the test twice, once for the swallowed exception and once for the row. **The fresh-row half of the sweep is asserted against both states** (`pending` and `running`, both fresh), because the fresh `running` row is exactly what a slow-but-alive export looks like at boot. **N1 fixed by making the body match the name**: the "another project in this workspace" test now seeds its story in a *second* project of the same workspace and asserts the job resolved to the path workspace (`scope=story`, `user_story_id`, `workspace_id`), not just `202` — the old body seeded the story in the *same* project, so a bug that assumes the workspace holds exactly one project would have stayed green — `job.workspace_id == seeded.workspace_id` cannot fail, because the route stamps the path workspace onto the row (finding 6). Boundary: 13 paths, all inside the declared surfaces. |
| WU6 — the UI | `7436da1` | RED observed first, and it is the honest red for a unit whose subject is a component that does not exist yet: both new test files failed at import resolution — `Failed to resolve import "@/lib/trello-api"` and `"@/components/react/TrelloCredentialsForm"`. GREEN: 18 passed on those two files, then **921 passed across 80 files** for the whole frontend, `tsc` clean, both re-run by the parent. **The one-target guarantee was verified by reading it rather than by trusting its test:** `resolveTrelloExportTarget` (`frontend/src/lib/trello-api.ts`) writes its two keys in mutually exclusive branches — a story wins over its project, one return each — so a body carrying both is unreachable by construction, which is what makes the API's `422` a backstop instead of the user's experience. The admin/member split was read too: `getTrelloConfig` sits behind `if (isAdmin)` (`TrelloCredentialsForm.tsx:71-72`), the member path calls only the status endpoint, and that endpoint's client keeps only the field codes it knows, the way the LLM status client does. The poll holds one timer per non-terminal job and clears it on cleanup (`ExportPanel.tsx:179-201`). **One change was made by the parent after the writer's handoff:** `WorkspaceSettings.test.tsx` already mocked its two other heavy children, and left real, the new form rendered its own load-error line in a state that test never set up — the form is mocked there now, like its neighbours, and its behaviour lives in its own file. |
| WU7 — specs and documents | `4a49324` | **No behaviour changed: 6 files, all documents — `AGENTS.md`, `docs/architecture.md`, `docs/deployment.md`, `docs/api.md`, `prod.todo.md` and the new `openspec/specs/trello-export/spec.md`; `git diff --stat` shows 14 insertions, 7 deletions plus the untracked spec.** The finding grep, before the edits: `grep -rni "trello" --include="*.md" . --exclude-dir=node_modules --exclude-dir=.git` → **188 lines in 15 files**; the four stale current-state claims located exactly — `docs/architecture.md:203` ("reutiliza lógica de csv2trello"), `docs/deployment.md:389` (`Trello connector | 🔲 Pendiente`), `AGENTS.md:554` (row 25 🔲) and `AGENTS.md:559` (the note asserting the connector does not exist), `prod.todo.md:124` ("El conector no existe"). After the edits the same four greps return **zero matches** (each run exits 1), the file count goes 15 → 16 (the 16th is the new spec), and every correction names what carries the behaviour: the port `domain/ports/trello_export_port.py`, the adapter `infrastructure/export/trello_adapter.py`, migrations `0030`/`0031`, the routes in `api/routes/export.py` and `api/routes/workspace_trello.py`, and the browser surface `trello-api.ts` / `TrelloCredentialsForm.tsx` / `ExportPanel.tsx`. The spec follows the house shape (`## Requirements` / `### Requirement:` / `#### Scenario:` with GIVEN-WHEN-THEN; `## Purpose` has precedent in `onboarding-flow`) and covers credentials, scope rule, lifecycle, board shape, the failure contract **with the sweep**, and the accepted limits verbatim from this record's non-goals and limitations — the no-two-way-sync, new-board-per-export, no-timeout and reload-loses-the-poll clauses are stated as accepted, not as gaps. **One real drift found beyond the three named claims and fixed:** WU5 added `TRELLO_EXPORT_INTERRUPTED` and the startup sweep after WU4 had written `docs/api.md`, and that document still listed only the five typed codes — the family paragraph now names the sweep, its age limitation, and the interrupted code as the one member outside the typed family; `grep -c TRELLO_EXPORT_INTERRUPTED docs/api.md` was 0 before, 1 after. The rest of `docs/api.md`'s Trello rows were confirmed accurate against the routes as they stand (202/404/409/422, both paths, both settings endpoints, the decrypted-pair convention) and left unduplicated. **Checked, not assumed, that nothing else still counts the connector as pending:** `grep -rni trello --include="*.md"` over the repo returns, besides the files above, only dated historical records left as history (`CHANGELOG.md`, `odd/tasks/prod-honesty-followups.md`, `odd/tasks/prod-checklist-honesty.md`, `odd/tasks/drop-per-user-llm-config.md`, the archived OpenSpec proposals) and two findings reported rather than fixed: `frontend/docs/design-brief.md` still describes an OAuth flow, a pending connector checkbox and a `trello` download format — a pre-feature design document outside this unit's edit surfaces — and `docs/deployment.md`'s checklist row for **Rate limiting** still reads `🔲 Pendiente` while `AGENTS.md` row 42 records it implemented on 2026-10-07; that row is a different feature's drift and belongs to a different unit. No document edited here is generated or asserted by a test — `grep` over `backend/tests` finds no consumer of `AGENTS.md`, `docs/*.md`, `prod.todo.md` or `openspec/` (the only `docs/api.md` hit is a docstring citation in `test_stories_import.py`) — and no OpenAPI-derived source was touched, so no gate was owed; `tests/test_api_reference.py` was still run as cheap confirmation: **5 passed**. |
| WU9 — the findings both verifications left open, closed | `4d2b65d` | **RED observed for three of the four code findings before any implementation change:** with only the new tests added, `pytest -q tests/test_unit/test_trello_export_job.py tests/test_unit/test_trello_export_recovery.py tests/test_api/test_trello_export.py` → **3 failed, 41 passed** — the typed handler's save fault escaped as `RepositoryError`, the generic handler's likewise, and the sweep died on the poisoned row leaving the healthy one behind. The double-cancel shield test was green against the shielded code **by design** — it pins an existing correct behaviour, and its red comes from the scratch-copy experiment below. Finding 6's edits are assertion replacements, not new tests; both touched tests stayed green. **The shield proven load-bearing, the record's fifth application of the sentence:** with both `asyncio.shield` wrappers replaced by direct `await`s in the worktree file (backed up first, restored byte-identical after — `sha256sum -c` verified), `pytest -q tests/test_unit/test_trello_export_job.py::TestTheFailureContract` → **1 failed, 6 passed** — only the new double-cancel test went red, and its failure is the exact defect the independent experiment reported: `assert row.status.value == "failed"` → `AssertionError: assert 'running' == 'failed'`. The six older contract tests stayed green without the shields, which is the gap this test closes. **GREEN after the fixes:** the same three focused files → **44 passed**. **Gates:** full backend suite `pytest -q` → **1448 passed, 45 skipped** (the same environmental skip set every unit has measured: 21 × Docker daemon unreachable for testcontainers, the rest live Qdrant/Ollama opt-ins); `ruff check src tests` → clean; `ruff format --check src tests` → 306 files already formatted (one first-pass reformat of this unit's own recovery test — a comment moved above the assert — re-run green). **What landed:** (1) the double-cancel test — a second `task.cancel()` delivered while the shielded interrupted write is held at a gate must still land the row `failed`/`TRELLO_EXPORT_INTERRUPTED`; the gated repo signals when the write has landed so the test never races the shielded inner task for the session; (2) both terminal writes guarded through a shared `_record_failure` (log, never raise, sweep named as the backstop), and the module docstring's unqualified "every failure must land in it" rewritten to say which faults cannot — the ones in a terminal write itself — plus a failure-contract bullet in `execute_trello_export`'s docstring; (3) the latent `job` dereference in `except TrelloExportError` guarded with a comment marking it unreachable today, no test (see finding 3); (4) the sweep's per-row `save` guarded — log, continue to the remaining rows — and the difference from `recover_stuck_extractions` documented as the sweep module's fourth deviation; the extraction sweep itself untouched, as it is another feature's code; (5) the tautologies — `job.workspace_id == seeded.workspace_id` deleted from the member-trigger test (nothing lost: stamped by the route under test, and `test_another_workspaces_job_is_not_readable` owns cross-workspace leakage) and replaced in the story-resolution test with `assert job.project_id is None`, which can fail and pins the never-two-targets rule on the persisted row. Boundary: 5 paths, all inside the declared surfaces (`export_workspace_to_trello.py`, `trello_export_task.py`, the three test files, this record). |
| WU8 — the failure-code mapping inverted | `5fa9efa` | **Purely structural: no behaviour change, no route change, no code string changed.** The import count, before and after, measured with the same grep: `grep -rnE "^\s*(from storico\.api|import storico\.api)" src/storico/application/ src/storico/domain/` returned **1 match before** (`export_workspace_to_trello.py`, two lines — `trello_export_error_code` from `api.errors` and `TRELLO_EXPORT_INTERRUPTED` from `api.error_codes`) and **0 matches after** (exit 1) — the only residual grep hits are a docstring cross-reference in `domain/services/llm_config_readiness.py:14` and a stale `.pyc`, neither an import; `domain/` was 0 before and after. **What landed:** every `TrelloExportError` member now declares its code as a class attribute with the registry's literal (`TrelloExportError.code = "INTERNAL_ERROR"` on the base — the same fallback an untyped member always received, so `exc.code` reproduces the old dict's semantics exactly, including for a subclass that forgets to declare one); the runner reads `exc.code` and imports `TRELLO_EXPORT_INTERRUPTED` from the domain mirror (`domain/entities/exceptions.py`), never from `api`; `api/errors.py` deleted `_TRELLO_ERROR_CODES` and `trello_export_error_code` is now `return exc.code`; `api/error_codes.py` **untouched** (`git diff --stat` over the file is empty) — the literals and `__all__` the frontend guard parses keep their exact shape. **RED observed at two levels:** with only the new test added, `pytest -q tests/test_unit/test_trello_error_codes.py` → collection `ImportError: cannot import name 'TRELLO_EXPORT_INTERRUPTED'`; with the domain constant added but no `code` attributes, the same run → `1 failed, 2 passed` — `AssertionError: TrelloExportError declares no code`. **GREEN:** after the attributes, the same file → `3 passed`; the focused runner suites `test_trello_export_job.py` + `test_trello_export_recovery.py` alongside → **33 passed**. **The pin proven able to fail:** `TrelloCardRefusedError.code` pointed at `TRELLO_CARD_REFUSED_TYPO` — a code nobody registered — in a scratch copy of `exceptions.py` (original backed up to `/tmp`, restored byte-identical, `sha256sum -c` → OK), and the pin test went red with `AssertionError: TrelloCardRefusedError.code = 'TRELLO_CARD_REFUSED_TYPO' is not declared in api/error_codes.py — the frontend cannot translate it`; the test discovers the family by walking `__subclasses__`, so a future member is covered without remembering to list it. **No code string changed:** a script comparing each member's `code` (and the interrupted mirror) against the registry's literal assignments printed `registry literal match: True` for all six, the two route codes of WU3's seven (`TRELLO_CREDENTIALS_MISSING`, `TRELLO_EXPORT_NOT_FOUND`) still present in the untouched registry — `ALL MATCH: True`. **Gates:** full backend suite `pytest -q` → **1451 passed, 45 skipped** (1448 + this unit's 3; the same environmental skip set every unit has measured: 21 × Docker daemon unreachable for testcontainers, the rest live Qdrant/Ollama opt-ins); `ruff check src tests` → clean; `ruff format --check src tests` → 307 files (one first-pass reformat of the new test file itself, re-run green). **Frontend guard, which parses the untouched registry:** `vitest run src/lib/__tests__/error-codes.test.ts` → **8 passed (1 file)**. Boundary: 5 paths, all inside the declared surfaces (`exceptions.py`, `export_workspace_to_trello.py`, `errors.py`, the new `test_trello_error_codes.py`, this record; `error_codes.py` and `test_trello_export_job.py` were authorized but needed no edit). One residual noted, not fixed: `infrastructure/tasks/trello_export_task.py:39` still imports `TRELLO_EXPORT_INTERRUPTED` from `api.error_codes` — an infrastructure→api import, not the application→api one this unit owns, and the sweep file is outside this unit's surfaces. |
| WU10 — `0031` created its enum twice | `43a119f` | Found by running the chain against the dev database on 2026-10-09, which is the one thing the local suite cannot do: `alembic upgrade head` failed with `DuplicateObjectError: type "trello_export_status_new" already exists`, because `_STATUS_ENUM` carried `create_type=True` while `upgrade()` already created it explicitly — so `create_table` issued a second `CREATE TYPE` inside the same transaction. The rollback left the schema clean and `alembic_version` at `0029`: loud, and harmless. One keyword fixed it. **Verified on that same real database, which also closes finding 8**: `alembic current` = `0031 (head)`, `alembic check` reports no drift, the enum's four labels are the domain's members in order, `fk_trello_exports_workspace_id_workspaces` and the credentials' FK are both `CASCADE`, `api_key`/`token` measured at width 1000, `find_by_statuses` executing against Postgres without a binding error, and `downgrade -1` → `upgrade head` round-tripping. **Why local never saw it**: the 21 testcontainers tests skip without Docker, and `test_migration_chain.py` — which applies the whole chain against a container and exists to prove no revision is broken — is one of them. CI runs it, so this branch was never a production risk; but nothing local would have caught it before a pull request, and that is the honest cost of the gap this record already listed. |
