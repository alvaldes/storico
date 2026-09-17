# ODD Feature: workspace-custom-providers

> **Status**: in progress
> **Created**: 2026-09-18
> **Workflow**: Organic Driven Development (ODD)

## Problem

A workspace can be configured with a provider name outside the four first-class
providers (`ollama`, `openai`, `anthropic`, `gemini`) — e.g. `deepseek`, `groq`,
`together`. Today that name is a bare string on `workspace_llm_configs.provider`
and the only way to set it is a `+` button in `LLMConfigEditor` that swaps the
provider `<Select>` for a free-text `<Input>`. Three defects follow:

1. **Nothing is owned or listed.** The custom name exists only as the current
   value of one config row. There is no per-workspace registry, so a second custom
   provider cannot exist, a rename is indistinguishable from switching providers,
   and nothing separates one workspace's custom providers from another's.

2. **The interaction is a hidden mode switch.** The `+` button flips
   `isCustomProvider` and re-renders a text input in the same slot. The field the
   user sees stops being a select and becomes editable in place, with no modal, no
   confirmation, and an empty `provider` until the first keystroke is committed by
   a separate Save. Users read this as "the `+` does nothing".

3. **Provider names are unvalidated.** `provider` is `str | None` with
   `max_length=50` and no pattern, so `DeepSeek Inc.` or an empty string can be
   persisted and then flow into extraction, where the name picks the adapter.

## Decisions (user-approved 2026-09-18)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Storage | Custom providers live in a **new `custom_providers` table**, one row per provider, scoped by `workspace_id` so workspaces never share or leak names. Not `localStorage`, not a JSON column. |
| D2 | Provider selection control | The provider field is a **`<Select>` at all times** — the user can never type into it. The free-text path and the `+`/`isCustomProvider` mode switch are deleted. |
| D3 | Create path | The select's last option is **"Add custom provider…"**. Choosing it opens a **modal**; the modal is where the name is typed. The selection does not change until a provider is actually created. |
| D4 | Rename path | A **pencil button to the right of the select** (the slot the `+` occupies today) opens the **same modal**, pre-filled, for the selected custom provider. It renders only when the selected provider is custom. |
| D5 | Name rules | Trimmed, lowercased, `^[a-z0-9][a-z0-9._-]{0,49}$` — the value is a provider slug that reaches the adapter selector. Colliding with a known provider name or an existing row in the same workspace is a `409`. |
| D6 | Rename cascade | Renaming a provider that is the workspace's **currently selected** provider also updates `workspace_llm_configs.provider`, in the same request. Otherwise the pencil would leave the select pointing at a name that no longer exists. |
| D7 | Existing rows | The migration backfills one `custom_providers` row per existing `workspace_llm_configs` row whose `provider` is not one of the four known names, so live custom providers appear in the new list after deploy. |
| D8 | Delete | **Out of scope.** Rename covers the typo case. A delete endpoint with no UI affordance would be dead code. |
| D9 | `PUT /llm` validation | Unchanged — it still accepts any provider string. Rejecting unknown names there would break workspaces whose provider predates the table and would couple the extraction path to the new table. |

## Non-goals

- No new first-class provider and no change to the OpenAI-compatible routing
  (`_build_llm_port` already sends unknown names to `OpenAIAdapter`).
- No per-provider model list, credentials, or base URL on the new table. Those
  stay on the workspace LLM config row; the custom provider is a name registry.
- No delete/unarchive endpoint, no pagination, no ordering controls.
- No change to how `ollama`, `openai`, `anthropic`, `gemini` are listed or probed.

## Established facts (verified in code)

- `KNOWN_PROVIDERS = ['ollama', 'openai', 'anthropic', 'gemini']` at
  `frontend/src/components/react/LLMConfigEditor.tsx:38`; `isKnownProvider()` is the
  membership test. Reused as the frontend's notion of "known", and mirrored
  server-side as the collision guard for D5.
- `provider` is `str | None = Field(None, max_length=50)` at
  `backend/src/storico/api/schemas/workspace_llm_config.py:11`, and
  `String(50)` on `WorkspaceLLMConfigModel`. The new table's `name` column must
  match that 50-char bound or a valid custom row could not be selected.
- `workspace_settings.py` routes are all `Depends(require_admin)` and use
  `get_repository(SQLAlchemyXRepository)` from `api/dependencies.py` — the new
  endpoints follow the same shape.
- Both existing 1:1 workspace tables (`workspace_prompts`, `workspace_llm_configs`)
  carry `workspace_id ... unique=True, ondelete="CASCADE"`. The new table is 1:N,
  so it is `indexed=True` and **not** unique, with `UniqueConstraint(workspace_id,
  name)`.
- Alembic head is `0020` (`0020_add_few_shot_config_to_workspace_prompts.py`), so
  the new revision is `0021`.
- Backend tests build the schema with `Base.metadata.create_all`
  (`backend/tests/conftest.py:97`), so the new model must be imported in
  `infrastructure/database/models/__init__.py` or its table will not exist in tests.
- `select_related` fixture: `seed_workspace(user=..., stories=0, role=WorkspaceRole.ADMIN)`
  returns a workspace the caller can reach as admin.
- `Select` wrapper (`frontend/src/components/ui/select.tsx`) re-exports `SelectGroup`,
  `SelectLabel`, `SelectSeparator`; base-ui `Select.Root` accepts `open` +
  `onOpenChange`, and `Select.Item` has **no** `closeOnClick`, so the popup close
  after choosing the sentinel option is driven by the controlled `open` state.
- The frontend tests mock whole API modules (`vi.mock('@/lib/llm-config-api', ...)`),
  so the new client module needs its own mock in `LLMConfigEditor.test.tsx`.
- `useEffect` model auto-probe is gated on `!isCustomProvider`
  (`LLMConfigEditor.tsx`), which becomes `isKnownProvider(llmConfig.provider)`.

## Tasks

### T-001 — Backend: `custom_providers` persistence layer

- **Status**: done (commit `7d5429c`)
- **Files to create**:
  - `backend/src/storico/domain/entities/custom_provider.py`
  - `backend/src/storico/domain/ports/custom_provider_repository.py`
  - `backend/src/storico/infrastructure/database/models/custom_provider.py`
  - `backend/src/storico/infrastructure/database/repositories/custom_provider_repository.py`
  - `backend/src/storico/infrastructure/database/alembic/versions/0021_add_custom_providers.py`
- **Files to modify**:
  - `backend/src/storico/domain/entities/__init__.py`
  - `backend/src/storico/domain/ports/__init__.py`
  - `backend/src/storico/infrastructure/database/models/__init__.py`
  - `backend/src/storico/infrastructure/database/repositories/__init__.py`
- **What**:
  - Table `custom_providers`: `id` UUID PK (Python-side `uuid7` default, matching
    every other table), `workspace_id` UUID FK → `workspaces.id` `ondelete=CASCADE`
    `nullable=False` **indexed, not unique**, `name` `String(50)` NOT NULL,
    `created_at` / `updated_at` `DateTime(timezone=True)` NOT NULL,
    `UniqueConstraint("workspace_id", "name")`.
  - `CustomProvider` frozen slotted dataclass mirroring the row, with
    `field(default_factory=uuid7)` and `datetime.now(UTC)` defaults — the same
    shape as `WorkspaceLLMConfig`.
  - Port with the minimum the routes need: `list_by_workspace`, `get`,
    `find_by_workspace_and_name`, `create`, `rename`. `get` exists for the
    ownership check on rename; `rename` returns the updated entity.
  - SQLAlchemy repository raising `RepositoryError` on `SQLAlchemyError`, wrapping
    the session exactly like `SQLAlchemyWorkspacePromptRepository`.
  - Migration `0021` creating the table plus the D7 backfill
    (`INSERT INTO custom_providers ... SELECT` from `workspace_llm_configs` where
    `provider NOT IN` the four known names), and a `downgrade()` that drops it.
- **Acceptance**: `ruff check` and `ruff format --check` clean; `pytest -q` still
  green (the new model registers in `create_all`); a focused repository test proves
  workspace scoping — a row created in workspace A is invisible to a
  `list_by_workspace(B)` call — and that the same name can exist in two workspaces
  while a duplicate inside one workspace is rejected.
- **Allowed edit surfaces**: `backend/src/storico/domain/**`,
  `backend/src/storico/infrastructure/database/**`,
  `backend/tests/test_repositories/**`

### T-002 — Backend: providers API endpoints

- **Status**: pending
- **Files to create**:
  - `backend/src/storico/api/schemas/custom_provider.py`
  - `backend/tests/test_api/test_workspace_settings_providers.py`
- **Files to modify**:
  - `backend/src/storico/api/routes/workspace_settings.py`
- **What**:
  - `GET /api/v1/workspaces/{workspace_id}/settings/providers` → `list[CustomProviderResponse]`
    for the workspace, ordered by `name`. Admin only.
  - `POST .../providers` → create. Body `{name}`. `409` when the name collides
    with a known provider (D5) or with an existing row in the same workspace.
    `422` when the name fails the pattern/length rule.
  - `PATCH .../providers/{provider_id}` → rename. Body `{name}`. `404` when the id
    is not in **this** workspace (never leak another workspace's row), `409` on
    collision. On success, if `workspace_llm_configs.provider` equals the old name,
    rewrite it to the new name via the existing
    `SQLAlchemyWorkspaceLLMConfigRepository` (D6).
  - The name rule and the known-provider guard live in one place each, so create
    and rename cannot drift.
- **Acceptance**: tests cover — list is empty for a fresh workspace; create then
  list returns the row; admin-only (`403` for a member); duplicate name in the same
  workspace `409`; same name in two workspaces succeeds; known-provider name `409`;
  invalid name `422`; rename returns the new name; rename of a non-member workspace
  `404`; and D6 — renaming the selected provider rewrites
  `GET .../settings/llm`'s `provider`, while renaming a *different* provider leaves
  the LLM config untouched.
- **Depends on**: T-001
- **Allowed edit surfaces**: `backend/src/storico/api/**`,
  `backend/tests/test_api/**`

### T-003 — Frontend: custom providers data layer and i18n

- **Status**: pending
- **Files to create**:
  - `frontend/src/lib/custom-providers-api.ts`
- **Files to modify**:
  - `frontend/src/types/workspace.ts`
  - `frontend/src/schemas/workspace.ts`
  - `frontend/src/schemas/index.ts`
  - `frontend/src/i18n/en.json`
  - `frontend/src/i18n/es.json`
- **What**:
  - `CustomProvider` interface (`id`, `workspaceId`, `name`, `createdAt`, `updatedAt`)
    plus the select's option shape if one is needed.
  - `listCustomProviders(wsId)`, `createCustomProvider(wsId, { name })`,
    `renameCustomProvider(wsId, providerId, { name })` via `api` +
    `toCamelCase`, mirroring `llm-config-api.ts`.
  - A zod schema for the name rule so the frontend rejects a bad name before the
    round trip, while the backend stays authoritative (D5).
  - i18n keys in **both** `en.json` and `es.json`, same key set: the add-option
    label, the dialog title/description/label/placeholder/confirm/cancel, and the
    error strings for invalid, duplicate, and known-name collisions. Spanish copy
    is neutral international Spanish (tú register), never voseo — enforced by
    `frontend/src/i18n/__tests__/neutral-spanish.test.ts`. Reuse
    `workspace.llmAddCustomProvider` for the select option instead of adding a
    duplicate key.
- **Acceptance**: `pnpm exec tsc --noEmit` clean; `pnpm vitest run` green including
  the neutral-Spanish and key-parity tests; new client functions covered by unit
  tests asserting the URL, body, and camelCase mapping.
- **Allowed edit surfaces**: `frontend/src/lib/**`, `frontend/src/types/**`,
  `frontend/src/schemas/**`, `frontend/src/i18n/**`

### T-004 — Frontend: provider select with add option and rename pencil

- **Status**: pending
- **Files to create**:
  - `frontend/src/components/react/CustomProviderDialog.tsx`
- **Files to modify**:
  - `frontend/src/components/react/LLMConfigEditor.tsx`
  - `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`
- **What**:
  - Delete `isCustomProvider`, `customProviderName`, the free-text provider
    `<Input>`, and the `+`/`Pencil` mode-toggle button. `isCustomProvider` becomes
    `!isKnownProvider(llmConfig.provider)`.
  - Render the provider `<Select>` unconditionally. Options: the four known
    providers, a separator, then one item per custom provider from
    `listCustomProviders`, then a separator and the `Add custom provider…` item.
    If the persisted `provider` is not in that list, append it as an implicit
    option so the select never renders an empty value (D9 robustness).
  - Choosing the sentinel add-option opens the dialog, closes the popup via the
    controlled `open` state, and **does not** change `llmConfig.provider`.
  - The pencil button occupies the `+`'s slot and renders only when the selected
    provider is custom; it opens the same dialog in rename mode.
  - `CustomProviderDialog`: one component, `mode: create | rename`, name input,
    inline error, disabled confirm while the name is unchanged or invalid, spinner
    while in flight. Create → POST, then select the new provider and clear
    `model`/`apiKey`/`baseUrl` (a brand-new provider has no values yet). Rename →
    PATCH, then re-point the selection to the new name **keeping** `model`,
    `apiKey`, and `baseUrl` untouched.
  - On any provider-list failure, keep the select usable (known providers plus the
    implicit current one) and surface the error through the existing `toast`.
- **Acceptance**: `pnpm exec tsc --noEmit` and `pnpm vitest run` pass. Tests cover —
  the provider field is never a text input; the add option opens the dialog and
  leaves the selection unchanged; create adds the provider to the list and selects
  it; create clears model/key/base-url; the pencil is absent for a known provider
  and present for a custom one; rename keeps model/key/base-url; duplicate name
  shows the error and does not close the dialog; a custom workspace still issues no
  automatic model probe.
- **Depends on**: T-002, T-003
- **Allowed edit surfaces**: `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/components/react/CustomProviderDialog.tsx`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`

### T-005 — Docs: API and database reference

- **Status**: pending
- **Files to modify**:
  - `docs/api.md`
  - `docs/database.md`
- **What**: add the three `settings/providers` endpoints to the workspace-scoped
  API table, and the `custom_providers` table (columns, constraints, `UNIQUE
  (workspace_id, name)`, the 1:N relation and its CASCADE) plus the ERD line
  `workspaces ──1:N── custom_providers`.
- **Acceptance**: docs match the shipped routes and columns, verified by reading the
  route decorators and the migration back, not from memory.
- **Depends on**: T-001, T-002
- **Allowed edit surfaces**: `docs/api.md`, `docs/database.md`

### T-006 — Verification gate

- **Status**: pending
- **What**: run the full CI-equivalent gate on the final tree and record the outcome.
- **Commands**:
  - `cd backend && .venv/bin/ruff check src tests`
  - `cd backend && .venv/bin/ruff format --check src tests`
  - `cd backend && .venv/bin/pytest -q`
  - `cd frontend && pnpm exec tsc --noEmit`
  - `cd frontend && pnpm vitest run`
  - `cd frontend && pnpm run build`
- **Acceptance**: every command passes; any failure is reported as a blocker, never
  as a done task. A previously failing command that is reproduced from a
  byte-identical file is recorded as pre-existing, not candidate-caused.
- **Depends on**: T-001..T-005

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rename leaves `workspace_llm_configs.provider` pointing at the old name | The select shows a name that no longer exists and extraction calls a stale provider slug | D6 cascade in the same request; covered by a T-002 test |
| Two commits on one request (provider row, then LLM config) | A failure between them leaves a renamed row and a stale selection | Rename the row first; the LLM config keeps a still-valid OpenAI-compatible name, and the UI's implicit-current-provider option keeps the select usable. Accepted over adding cross-table transaction plumbing |
| Sentinel option in a controlled base-ui `Select` leaves the popup open | The user picks "Add custom provider…" and nothing visibly happens | The Select's `open` state is controlled and closed explicitly on the sentinel branch; pinned by a T-004 test |
| A legacy custom provider has no `custom_providers` row | The select would render empty and the value would look lost | D7 backfill in the migration, plus the T-004 implicit-current-provider option |
| The 50-char DB bound drifts between `provider` and `custom_providers.name` | A row could be created that the select cannot select | Both are 50 chars; the name rule caps at 50 including the first character |
| Deleting the `+` toggle silently removes a capability | A custom provider that was never registered in the table can no longer be typed in | Accepted: D2/D3 replace typing with create-then-select, and D7 backfills the one case that could have been stranded |
| New table only registered in the model module, not in the migration | Tests pass, production deploy fails on a missing table | T-001 ships both, and T-006 runs the full backend suite against `create_all` |
| The backfill runs only on deploy, where no test reaches it | A filtering bug silently registers wrong rows or none | T-001 tests the revision directly against a scratch database, DDL and backfill included |
| The revision's SQLite-based test cannot prove Postgres-only DDL behaviour | A Postgres-specific failure reaches deploy | Accepted: Docker is unavailable here. The assertions are limited to the declarative shape, which SQLite reflects faithfully, and the residual gap is stated in the test module's docstring |
| pi-lens' pyright probe cannot resolve modules created during the same session | New files appear as unresolved imports, obscuring real findings | Proven tooling state, not candidate-caused: a throwaway module containing only `PROBE = 1` was equally unresolvable while a pre-existing module in the same package resolved; pyright also analysed `custom_provider.py` as clean while reporting the module missing. The repo's own gate (`ruff` + `pytest`) resolves and exercises every module |

## Evidence log

_(each completed task records its commit identity here)_

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `7d5429c` | `custom_providers` (id UUID PK from `uuid7`, `workspace_id` FK → `workspaces.id` ON DELETE CASCADE indexed, `name` String(50), timestamps, `UniqueConstraint(workspace_id, name)`), the `CustomProvider` entity, the five-method port, the SQLAlchemy repository, and revision `0021` with a verbatim backfill of every config whose `provider` is not one of the four known names. 25 new tests: 12 on repository workspace scoping (including that the same name is allowed in two workspaces while a duplicate inside one is rejected, and that a constraint violation surfaces as `RepositoryError`) and 13 on the revision itself — the real DDL runs, the backfill's filter branches (known, blank, whitespace, verbatim, cross-workspace) are exercised, and the migrated table is compared against the ORM model for columns, nullability, primary key, unique constraint, index and the cascading foreign key. Verified: `ruff check` clean, `ruff format --check` clean, full backend suite 485 passed / 1 skipped. Two environment notes: the test database is in-memory SQLite, so the cascade is asserted on declared metadata rather than by deleting a workspace (SQLite ignores `ON DELETE CASCADE` without `PRAGMA foreign_keys=ON`), and the `RuntimeWarning: coroutine 'Connection._cancel' was never awaited` seen in full-suite runs was reproduced on a stashed base tree, so it is pre-existing and its attribution simply moves with GC timing. |
