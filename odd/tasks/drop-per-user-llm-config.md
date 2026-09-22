# ODD Feature: drop-per-user-llm-config

> **Status**: done — five commits on `feat/drop-per-user-llm-config` (`711d9cd`..
> `a4c92f9`), plus the evidence commit that carries this line (six against the parent
> branch); the work is on `origin/main` (every named commit is an ancestor of it, measured
> 2026-09-22). Receipt-driven development is **off** in this clone, so no
> native review ran; one independent verification did, recorded below with its findings and
> their disposition.
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

- **Status**: done (commit `711d9cd`)
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

- **Status**: done (commit `82f0129`)
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

- **Status**: done (commit `52d8a6f`)
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

- **Status**: done (commit `ba3f975`, corrected in `a4c92f9`)
- **Files to modify**: `docs/api.md`, `docs/security.md`
- **What**: state that the user-preferences payload carries no LLM configuration and no
  credential, and update the security note so it describes where a key *is* stored (the
  workspace row) after this change removed the per-user one.
- **Acceptance**: no document still implies a per-user LLM configuration exists.
- **Depends on**: T-002
- **Allowed edit surfaces**: `docs/api.md`, `docs/security.md`

### T-005 — Verification gate

- **Status**: done (one independent `gentle-ai-verify` run; its findings are fixed in
  `a4c92f9`)
- **What**: run the repo gate and record it; delegate an independent verification that looks
  for **any** remaining reader or writer of a per-user LLM setting (backend, frontend,
  scripts, e2e), exercises the legacy-row path and the migration, and checks the `422`.
- **Commands**: `cd backend && .venv/bin/pytest -q`, `.venv/bin/ruff check src tests`,
  `.venv/bin/ruff format --check src tests`; `cd frontend && node_modules/.bin/vitest run`,
  `node_modules/.bin/tsc --noEmit`.
- **Acceptance**: every command passes and the counts are recorded.
- **Depends on**: T-001, T-002, T-003, T-004

### T-006 — Close the feature

- **Status**: done (this document's commit)
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
| T-001 | `711d9cd` | Revision `0022` removes the key from every stored document, leaves `updated_at` alone (it answers *when the user last saved*), and is idempotent. 7 cases in `test_drop_user_preference_llm_migration.py`, including non-object documents. Chain checked mechanically: 22 revisions, one head (`0022`), no branch points. |
| T-002 | `82f0129` | `AppSettings` keeps only `export`; `LLMSettings`/`LLMProviderConfig` and their re-exports deleted; the read drops the removed key; the two routes get their first tests (8 cases). Red run: **4 of 8 fail** against the previous schema — exactly the four that assert the credential is gone. |
| T-003 | `52d8a6f` | `AppSettings`/`DEFAULT_SETTINGS` lose `llm`; the store loses its `llm` state and four setters and takes its toast copy from the caller; `testLLMConnection` and its two types deleted; the export select now **persists** and shows the localized label instead of the raw value. 10 new cases. Full frontend suite **33 files / 382 passed**. |
| T-004 | `ba3f975`, fixed in `a4c92f9` | `docs/api.md` and `docs/security.md` updated — and the verification caught that `docs/frontend-state.md` had been missed (F1 below). |
| T-005 | `a4c92f9` | Gate and independent verification, below. Six findings addressed. |
| T-006 | this document | Status, evidence, the verification record and the dispositions. Final gate: backend **646 passed, 1 skipped**, `ruff` clean; frontend **33 files / 382 passed**, `tsc` exit 0. |

## Verification (RDD off — independent verification, not native review)

One `gentle-ai-verify` run, read-only, probes in `/tmp` copies. It first corrected the range:
the branch had accumulated the previous feature's commits, so it verified `c02ec63..ba3f975`
instead of the four it was given. Gate it observed: backend **646 passed, 1 skipped**, `ruff
check` and `ruff format --check` clean over 214 files; frontend **33 files / 382 passed**,
`tsc` exit 0.

What it confirmed independently:

- **No reachable survivor** of a per-user LLM setting anywhere — backend, frontend, `scripts/`,
  `e2e/`, config, gitignored paths — with the deliberate exception of `POST /api/v1/llm/test`,
  whose credential arrives in the request body and belongs to no stored preference.
- **The legacy path end to end**: a document in the old shape (with a real-looking key) answers
  `200`, and the **raw response text** contains no `llm`, no `sk-`, no `AIza`. The read is
  tolerant, not a migration: storage is byte-identical afterwards.
- **The migration in isolation** over nine seeded shapes: exactly five `UPDATE`s — only the
  dict rows carrying the key — with `updated_at` and the row count unchanged, `downgrade()`
  issuing **zero** statements, and a second `upgrade()` a no-op.
- **Both deploy orders are functionally safe** (old code + migrated data → `200`; new code +
  unmigrated data → `200`), which is what the shim is for.
- **The `PUT` refusal is bounded**: `llm`, an unknown key, a nested extra, a top-level extra, a
  `LLM`-cased variant and a missing `preferences` all answer `422`. The tolerance did not become
  a general ignore-extras.
- **The bundled frontend fix, both ways**: with the old `AccountPage` restored the trigger read
  `trello▼` and `saveSettings` was called **0** times; with the candidate it reads `Trello▼`
  (and `Trello` in Spanish) and saves once with the right payload. A raw-value audit of every
  other `Select` found `AccountPage` was the only one using `<SelectValue />` without `items`.
- **Teeth, in both directions**: reverting only the backend schema+route fails **4** tests with
  zero pre-existing failures; reverting only the frontend types+store fails **4** more.

### Findings and disposition

- **F1 (fixed in `a4c92f9`) — candidate-caused drift, low, and a miss against my own acceptance
  criterion.** `docs/frontend-state.md` still documented the removed store shape
  (`settings: AppSettings // { llm: LLMConfig, … }`, `syncToApi(toastLabels?)`, the four
  `set*Config` setters). T-004 claimed no document still implied a per-user LLM configuration;
  this one did. Updated.
- **F3 (addressed in `a4c92f9`) — candidate-caused, medium: the deploy-order hazard.** With the
  migration applied and the *previous* release still serving, an old-client `PUT` re-stores the
  whole `llm` block including the credential; the revision never runs again, and the new read
  hides it, so the residue would be silent. Migrating first is therefore the wrong order. The
  migration's docstring now says so where an operator will look; there is no code fix, because
  the acceptance of that block belongs to the old release.
- **F4 (fixed in `a4c92f9`) — candidate-caused, low.** `llm_saving`, `llm_save_error` and
  `llm_saved_description` became unreferenced when the store stopped hardcoding its copy. This
  slice created that dead copy, so it removes it from both locales (`llm_saved` stays: the
  workspace editor still uses it).
- **F6 (fixed in `a4c92f9`) — candidate-caused, informational.** The read dropped the removed
  keys while the `PUT` response did not, an asymmetry that is unreachable today but latent. Both
  now go through one `_for_schema` helper, so the invariant holds by construction instead of by
  one call site remembering it.
- **F7 (fixed in `a4c92f9`) — candidate-caused, informational.** The removed key name exists as
  two literals. The migration now says why it does not import the schema's constant — a
  migration must keep working against the schema as it was when written — which turns a latent
  drift risk into a stated decision.
- **Plus an eighth, found while settling the analyzer question**: `schemas/__init__.py`'s
  `__all__` listed `ExtractionResultResponse`, a name that does not exist anywhere (a leftover
  from an old rename, pre-existing). Removed; it was the only warning a cold Pyright run
  reported.
- **F2 (recorded) — pre-existing, informational.** `frontend/.vercel/output` and `dist` hold a
  pre-change bundle that still contains the API-key fields; gitignored and regenerated by a
  build, but a deploy reusing them would ship the old contract.
- **F5 (recorded) — pre-existing, low.** No code removes the legacy `storico-settings`
  localStorage key, so a browser upgraded from the release that persisted API keys keeps them.
  Out of scope here (a behaviour change of its own), and already in the follow-ups below.
- **Not verified:** the migration against Postgres — no Docker here, and the CLI cannot be
  pointed at SQLite, so a bound `Operations` over a scratch database was used instead. On
  SQLite the JSON round-trip is exact; Postgres-specific typing of the column is untested.

### The `ExportSettings is unknown import symbol` report

An automated analyzer repeatedly reported that `api/schemas/settings.py` did not define
`ExportSettings`/`AppSettings`. That was true for a few minutes: a backup-and-restore script I
wrote during a red run keyed its temporary files by **basename**, and both
`api/schemas/settings.py` and `api/routes/settings.py` are named `settings.py`, so the second
backup overwrote the first and the restore copied the *routes* content into the schema module —
a file importing itself, which is exactly the fingerprint the analyzer showed (`Module cannot be
used as a type` for every imported name). It was repaired immediately; a **cold Pyright 1.1.408
run reports `errorCount: 0`** on those files, `typing.get_type_hints` resolves the annotations to
classes (not modules), and `create_app().openapi()` builds with `AppSettings.properties:
['export']`. The analyzer kept serving the cached analysis; clearing
`~/.cache/opencode/packages/pyright` is the likely fix and needs the user's go-ahead, since it is
a destructive command outside the repository. **Lesson recorded: never key a temporary backup by
basename when two paths can share it.**

## Follow-ups (not part of this change)

- **`removeItem('storico-settings')`** so a browser upgraded from the build that had the
  per-user LLM editor drops the keys it may still hold (D7, confirmed by the verification).
- **Stale build artifacts**: `frontend/.vercel/output` and `frontend/dist` still contain the
  pre-change bundle with the API-key fields. Regenerate before any deploy that reuses them.
- **Deploy order**: run revision `0022` **after** the release that refuses the `llm` block.
  Stated in the migration's own docstring (F3); it is a process constraint, not a code one.
- The comment on `AccountPage`'s label fix says the other selects "render an explicit label
  span"; two of them actually use `<SelectValue />` **with** `items` on the root. The conclusion
  holds (`AccountPage` was the only one without `items`), the wording is imprecise.
- The remaining review follow-ups from earlier slices: at-rest encryption for workspace keys,
  the stale provider enumerations, the undocumented operations, `TaskEditor`'s `getSnapshot`
  loop, and the store's flattened `error`.
