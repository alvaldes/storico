# ODD Feature: drop-per-user-llm-config

> **Status**: in progress
> **Created**: 2026-06-30
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/drop-per-user-llm-config`, stacked on `feat/error-display`.
> **Receipt-driven development**: off in this clone.

## Problem

Slice 4 of the review follow-ups. A **per-user** LLM configuration still exists in the
schema, the API and the client, and nothing uses it:

- `backend/src/storico/api/schemas/settings.py` declares `LLMSettings` and
  `LLMProviderConfig` (provider + a `model`/`api_key`/`base_url` per provider) inside
  `AppSettings`, so `GET /api/v1/users/me/settings` **returns them and
  `PUT` accepts them**. The `api_key` fields are stored in `user_preferences.preferences`,
  a plain `JSON` column.
- Nothing reads them: no route, no background task and no adapter consults the user's
  preferences for an LLM setting. The live configuration is
  `workspace_llm_configs`, which is a different row with a different owner.
- `frontend/src/stores/settingsStore.ts` still carries `settings.llm` plus four setters and
  a `syncToApi` whose default toast copy is LLM-flavoured ("Saving LLM configuration…").
  **`syncToApi` has no caller**, so `saveSettings` — its only consumer — is effectively dead
  too, and so is `testLLMConnection` in `lib/settings-api.ts`.
- The per-user LLM editor that used to write all of this was removed in `75b4882`
  (`SettingsPage.tsx`, 786 lines, replaced by `AccountPage.tsx`), which is also why a
  browser upgraded from an older build can still hold API keys under the legacy
  `storico-settings` localStorage key.

So a credential store nobody reads is still reachable over the API, and the user has no way
to know it is there.

### The prerequisite the review found

`AppSettings` sets `extra="forbid"`, so simply deleting the `llm` field makes
`AppSettings(**existing.preferences)` raise
`ValidationError: Extra inputs are not permitted` for **every** row that still stores it —
turning `GET /users/me/settings` into a 500 for those users. Verified empirically. Stored
data therefore has to be handled in the same change, and both halves are needed:

- a **migration** so the table stops holding keys, and
- a **tolerant read** so a row the migration did not cover (a restore, a client on the old
  contract) degrades instead of failing.

### The adjacent defect this uncovered

`AccountPage`'s export-format select calls `setExportFormat` and nothing else, so the
"Default Format" preference is never persisted — it looks saved and reverts on reload.
With `syncToApi` uncalled, the app currently has **no** working path to write preferences.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The stored data | **Migration `0022` strips the `llm` key** from every `user_preferences.preferences` row (user-approved). The keys have no reader; keeping them is only a liability. |
| D2 | The read | **Tolerant, and narrowly so**: the GET drops exactly the removed `llm` key before constructing `AppSettings`, rather than relaxing `extra="forbid"` for the model. A targeted migration-era shim, named as such. |
| D3 | The API contract | `PUT` rejects `llm` with `422` (the field no longer exists and extras are forbidden). That is the point: there is no way to put a key back through this endpoint. |
| D4 | The endpoint survives | `GET`/`PUT /users/me/settings` stay. `export.defaultFormat` is a real preference the UI exposes, and `DEFAULT_SETTINGS` keeps a shape for it. |
| D5 | The dead client code | Delete `testLLMConnection`, `LLMTestParams`, `LLMTestResult`, the store's `llm` slice and its four setters. The backend's `POST /api/v1/llm/test` stays: it is a documented endpoint that takes a credential from the body and belongs to no user's stored preferences. |
| D6 | The adjacent defect | **Wire the export save** in `AccountPage` and make `syncToApi`'s copy caller-supplied. Flagged as a deliberate bundling: the alternatives were leaving dead code inside a slice whose purpose is deleting dead code, or deleting the only writer and making the gap unfixable by one line. |
| D7 | The legacy localStorage key | **Not touched.** `removeItem('storico-settings')` is a behaviour change with its own risk (a browser that never upgrades keeps it), and the honest statement about current code already holds. Recorded. |

## Non-goals

- No change to `workspace_llm_configs` or to the workspace-facing LLM routes.
- No encryption work (that is its own feature; this change removes a plaintext store rather
  than encrypting one).
- No new preference and no change to what `export` accepts beyond persisting it.
- No removal of `GET`/`PUT /users/me/settings` (D4) and no change to the `/llm/test` route.
- No migration of the legacy `storico-settings` localStorage key (D7).

## Established facts (verified)

- `AppSettings` (`api/schemas/settings.py`) holds `llm: LLMSettings` and
  `export: ExportSettings`, with `extra="forbid"` on every nested model.
- `AppSettings(**{'llm': …, 'export': …})` raises `ValidationError` once `llm` stops being a
  declared field (verified with a stand-in model).
- Nothing reads `preferences['llm']`: `grep` over the backend finds only the schema itself
  and the route that round-trips it.
- `user_preferences.preferences` is `Mapped[dict] = mapped_column(JSON)`, written through
  `SQLAlchemyUserPreferencesRepository.upsert`.
- Alembic head is `0021`; the migration-test pattern is
  `tests/test_unit/test_custom_provider_migration.py` (loads the revision module from its
  path, runs it against a scratch SQLite engine via `MigrationContext`/`Operations`).
- `POST /users/me/settings` tests do not exist today: `tests/test_api/test_users.py` covers
  `/me` and onboarding only.
- Frontend dead code: `syncToApi` (no caller), `saveSettings` (only `syncToApi`),
  `testLLMConnection`/`LLMTestParams`/`LLMTestResult` (no caller).
- `AccountPage.tsx:202` calls `setExportFormat` with no save (D6).
- i18n keys `settings.llm_saving`, `settings.llm_saved`, `settings.llm_saved_description`
  are the store's default toast copy and are LLM-flavoured; the store should own no copy.

## Tasks

### T-001 — Strip the stored per-user LLM slice

- **Status**: pending
- **Files to modify**:
  `backend/src/storico/infrastructure/database/alembic/versions/0022_drop_user_preference_llm.py`
  (new), `backend/tests/test_unit/test_drop_user_preference_llm_migration.py` (new)
- **What**: revision `0022` removing the `llm` key from every
  `user_preferences.preferences` JSON document, leaving the rest of the document intact.
  `downgrade()` is a no-op with the reason stated: the deleted keys are unrecoverable and
  re-adding the field is not a data operation.
- **Acceptance**: the new suite passes. Cases: a row with `llm` loses it and keeps `export`;
  a row without `llm` is untouched; a row whose preferences are `{}` is untouched; the
  migration is idempotent if run twice.
- **Allowed edit surfaces**:
  `backend/src/storico/infrastructure/database/alembic/versions/0022_drop_user_preference_llm.py`,
  `backend/tests/test_unit/test_drop_user_preference_llm_migration.py`

### T-002 — The preferences contract loses `llm`, and tolerates it in storage

- **Status**: pending
- **Files to modify**: `backend/src/storico/api/schemas/settings.py`,
  `backend/src/storico/api/routes/settings.py`,
  `backend/tests/test_api/test_user_settings.py` (new)
- **What**: `AppSettings` keeps only `export`; `LLMSettings` and `LLMProviderConfig` are
  deleted. The GET drops a stored `llm` key before constructing the model (D2), with a
  comment saying why it exists. First tests for these two routes.
- **Acceptance**: the new suite passes. Cases: GET for a user with no row returns the
  default export shape; GET for a row still holding `llm` answers `200` with `export` only
  and no `llm` in the payload; GET never returns an `llm` key at all; `PUT` with a body
  carrying `llm` answers `422`; `PUT` with `{"preferences": {"export": …}}` round-trips.
- **Depends on**: T-001
- **Allowed edit surfaces**: `backend/src/storico/api/schemas/settings.py`,
  `backend/src/storico/api/routes/settings.py`,
  `backend/tests/test_api/test_user_settings.py`

### T-003 — The client stops carrying a per-user LLM config

- **Status**: pending
- **Files to modify**: `frontend/src/types/settings.ts`,
  `frontend/src/stores/settingsStore.ts`, `frontend/src/lib/settings-api.ts`,
  `frontend/src/components/react/AccountPage.tsx`,
  `frontend/src/components/react/__tests__/AccountPage.test.tsx` (new),
  `frontend/src/stores/__tests__/settingsStore.unit.test.ts` (new),
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`
- **What**: `AppSettings` and `DEFAULT_SETTINGS` lose `llm`; the store loses its `llm` state
  and the four setters; `syncToApi` takes required labels so it owns no copy (D6); the export
  select persists its change; `testLLMConnection` and its two types are deleted (D5). New
  i18n keys for the preferences-saving copy, neutral Spanish.
- **Acceptance**: `vitest run` and `tsc --noEmit` pass. Cases: changing the format calls the
  save with the new value; the store's state has no `llm`; a failed save reports an error and
  a successful one reports success.
- **Depends on**: T-002 (the shape it mirrors)
- **Allowed edit surfaces**: `frontend/src/types/settings.ts`,
  `frontend/src/stores/settingsStore.ts`, `frontend/src/lib/settings-api.ts`,
  `frontend/src/components/react/AccountPage.tsx`,
  `frontend/src/components/react/__tests__/AccountPage.test.tsx`,
  `frontend/src/stores/__tests__/settingsStore.unit.test.ts`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`

### T-004 — Say what the endpoint now carries

- **Status**: pending
- **Files to modify**: `docs/api.md`, `docs/security.md`
- **What**: state that the user-preferences payload carries no LLM configuration and no
  credential, and update the security note so it describes where a key *is* stored (the
  workspace row) after this change removed the per-user one.
- **Acceptance**: no document still implies a per-user LLM configuration exists.
- **Depends on**: T-002
- **Allowed edit surfaces**: `docs/api.md`, `docs/security.md`

### T-005 — Verification gate

- **Status**: pending
- **What**: run the repo gate and record it; delegate an independent verification that looks
  for **any** remaining reader or writer of a per-user LLM setting (backend, frontend,
  scripts, e2e), exercises the legacy-row path and the migration, and checks the `422`.
- **Commands**: `cd backend && .venv/bin/pytest -q`, `.venv/bin/ruff check src tests`,
  `.venv/bin/ruff format --check src tests`; `cd frontend && node_modules/.bin/vitest run`,
  `node_modules/.bin/tsc --noEmit`.
- **Acceptance**: every command passes and the counts are recorded.
- **Depends on**: T-001, T-002, T-003, T-004

### T-006 — Close the feature

- **Status**: pending
- **Depends on**: T-005

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| The migration deletes data irreversibly | Keys are gone | They have no reader, and that is the user-approved decision; `downgrade()` says so instead of pretending |
| A row the migration missed breaks the endpoint | A user's settings page 500s | The tolerant read (D2) covers it, and a test seeds the legacy shape |
| Removing the field breaks `PUT` callers | A client sending `llm` gets `422` | The only client is this repo's, updated in the same change; `422` is asserted |
| Bundling the export-save fix (D6) | Scope beyond "kill the dead config" | Its own commit; flagged in the report so it can be rejected on its own |
| `AccountPage` now writes on every select change | Extra requests | One `PUT` per change of a single select; the store already debounces nothing and the request is small |

## Evidence log

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | | |
| T-002 | | |
| T-003 | | |
| T-004 | | |
| T-005 | | |
| T-006 | | |

## Follow-ups (not part of this change)

- **`removeItem('storico-settings')`** so a browser upgraded from the build that had the
  per-user LLM editor drops the keys it may still hold (D7).
- `ErrorDisplay`? No. The open slices from earlier are done; the remaining review follow-ups
  are the at-rest encryption decision, the stale provider enumerations, the undocumented
  operations, `TaskEditor`'s `getSnapshot` loop and the store's flattened `error`.
