# Canonical error envelope: every user-facing API error carries one machine-readable code

Feature: `api-error-code-envelope`. Started 2026-09-28. Owner decision: **option C** —
translate backend errors by code, on the frontend, into *specific* copy (not just a generic
headline). The user chose **backend first** and **unify the contract to a single field**.

## Problem

The API returns English prose in `detail`, and the frontend renders that prose verbatim, so a
Spanish user gets an untranslated error no matter how complete `es.json` is (PR #25 hid this in
one surface instead of fixing it). The backend already emits machine-readable codes in most
real failures, but under **two different field names** at **two different nesting levels**, and
the frontend reads exactly one of them.

## Established facts (measured on `main` @ `556a25e`, 2026-09-28)

- **38 `raise HTTPException` sites** in `backend/src/storico/`. Only **6** carry a code; **32**
  are bare English prose (string or f-string). `users.py`, `auth.py`, `settings.py`, `health.py`
  have zero raise sites.
- **`api/errors.py` exists** and wires **13 domain-exception handlers** (`api/app.py:143-160`).
  It emits the code as **`type`, not `error_code`**, with 12 lowercase-slug values
  (`entity_not_found`, `duplicate_entity`, `repository_error`, `internal_error`,
  `llm_connection_error`, `llm_model_not_found`, `llm_response_error`, `parse_error`,
  `insufficient_role`, `owner_transfer_error`, `last_admin_error`, `cannot_remove_owner`).
  The **cipher handler is the exception**: it emits **top-level `error_code`** with
  **SCREAMING_SNAKE** values (`ENCRYPTION_KEY_MISSING`, `CREDENTIAL_UNDECRYPTABLE`) *and* `type`.
- **57 raises of those domain exceptions** in the tree (19 `EntityNotFound`, 16 `RepositoryError`,
  9 `LLMError`, 8 `LLMResponseError`, 4 `LLMConnectionError`, 3 `DuplicateEntity`,
  3 `OwnerTransferError`, 3 `LLMModelNotFoundError`, 2 `CredentialUndecryptable`). These already
  reach a client with a code; nothing reads it.
- **The frontend reads exactly one location**: `detail.error_code`, and only when `detail` is an
  object (`api.ts:60-66`). It never touches `type` or top-level `error_code`. `ApiRequestError`
  already has an `errorCode` field and `toErrorInfo()` already forwards it — the plumbing exists,
  the wiring is missing.
- **No backend localization at all**: zero matches for `Accept-Language|locale|lang|i18n|gettext|babel`
  in `backend/src/`. Locale lives only in the Astro route param and reaches React islands as a
  prop. No persisted language preference (`user_preferences.py` is `{user_id, preferences}`).
- **No code→message table exists anywhere.** The two keys that mirror backend prose
  (`stories.create_duplicate_error`, `settings.llmModelsFetchError`) are hand-maintained copies
  on specific paths — exactly the pattern this feature replaces.
- **Unconsumed envelope**: `docs/api.md` documents **two shapes** — top-level `type`
  (`api.md:262-273`, with a table of 4 codes) and nested `detail.error_code` for import errors
  (`api.md:92-99,113-117`) and `LLM_CONFIG_INCOMPLETE` (`api.md:187,321`).
- **Blast radius of unifying the field**: **9** backend assertions pin `["type"]`
  (`test_stories.py:333,396`; `test_extractions.py:338`; `test_projects.py:275,330,378`;
  `test_tasks.py:141,441,584`), all against the single value `entity_not_found`.
  ~9 more pin nested `detail["error_code"]` (`test_stories_import.py:160,215,327,342,352,373,454`;
  `test_extraction.py:663,697`). **No test compares the full key set of an error body**, and
  `tests/contract/test_api_schemas.py` pins success schemas only — nothing pins the error envelope.
- ~14 backend assertions pin English `detail` **prose** (`test_stories.py:68-72,101-103,440,451`,
  `test_story_access.py:39,238`, `test_tasks.py:96,124`, `test_projects.py:447-493`,
  `test_extraction.py:537-538`). Adding a field leaves these valid; **changing prose breaks them.**
- `ErrorDisplay.tsx:161-166` renders the raw code as visible chrome: `HTTP 403 • INVALID_STATE_TRANSITION`.

## Decisions

- **D1 — The fix is a code, not a translation layer in the backend.** The backend stays
  English-speaking (its prose is the operator-facing language of record, and it has no locale
  concept). It guarantees a stable code; the frontend owns the user's words. Confirmed by the
  user as option C.
- **D2 — Canonical field: top-level `error_code`.** Chosen by measurement, not taste: `type`
  collides with FastAPI's own 422 `detail[].type`; `errorCode`/`error_code` is already the
  frontend property name, already top-level in the cipher handler, and already SCREAMING there.
  The user explicitly accepted unifying to one field (`docs/api.md` currently documents two).
- **D3 — Canonical values: `SCREAMING_SNAKE`.** The 12 lowercase `type` values are read by
  **nobody** (verified by grep over `frontend/src/`), while the frontend branches on
  `INVALID_STATE_TRANSITION`, `IMPORT_*` and `LLM_CONFIG_INCOMPLETE`. Lowercasing instead would
  break ~10 live frontend comparisons. So this costs 9 test assertions and zero frontend logic.
- **D4 — `detail` keeps its current English text.** Breaking ~14 prose assertions buys nothing;
  the code is the contract, the prose is the human-readable fallback and the raw-panel content.
- **D5 — `HTTPException` cannot carry a top-level code, so a dedicated exception is required.**
  `HTTPException` exposes only `status_code` and `detail` — nesting a code inside `detail` *is*
  the inconsistency being removed. `ApiError(status_code, error_code, detail)` + one handler is
  the only way to reach the 32 bare-prose sites without a per-route body shape.
- **D6 — Sequence: backend envelope first, frontend map after.** The user chose this knowing it
  defers user-visible benefit by one slice. Consequence accepted: between the two slices the app
  shows a translated headline with the server's English sentence beneath it (PR #25 behaviour).
- **D7 — Release-slot warning.** `.cz.toml` sets `major_version_zero = true`; commitizen's
  `BUMP_MAP_MAJOR_VERSION_ZERO` (`defaults.py:139-147`) maps both `BREAKING CHANGE` and `!` to
  **MINOR**, and `feat` also maps to MINOR. At `0.8.0` that means a `feat`/breaking commit here
  **consumes the `0.9.0` reserved for extraction versioning**. To keep the reservation this work
  must land as `fix`/`refactor` (→ `0.8.x`). Surfaced for the owner, not silently decided.

## Tasks

- [x] **WU1 — Canonical envelope on the 13 handlers.** `api/errors.py`: emit top-level
  `error_code` with SCREAMING values, drop `type`. Update the 9 `["type"]` assertions. Add a
  **permanent guard test** pinning the envelope shape (every handler body has `error_code`, no
  `type`) — the repo already sets this precedent with the i18n duplicate-key guard. Update
  `docs/api.md` to one shape. ~40 source lines + tests + docs.
- [x] **WU2 — `ApiError` exception + handler.** Mechanism that lets a raise site produce a
  top-level code. Covers FastAPI's own 422 `RequestValidationError` and the 404/405 defaults,
  which today emit no app code at all.
- [ ] **WU3 — Migrate the 32 bare-prose raises.** `dependencies.py` first (9, all access control
  — the most frequently seen English in the app), then `workspace_settings.py` (8), `stories.py`
  (5), `workspaces.py`/`projects.py` (4), `export.py`/`extractions.py`/`tasks.py`/`extraction.py` (4).
  Split by file across PRs if the diff exceeds the review budget.
- [ ] **WU4 — The 6 nested `detail.error_code` sites → top-level.** Backend and frontend move
  together (`stories-api.ts` `readImportFailure`, `taskStore.ts:113`, `KanbanBoard.tsx:168`,
  `api.ts:61-63`), with the frontend tolerating both shapes during the deploy window (backend
  deploys on the Oracle VM, frontend on Vercel — they are not atomic).
- [x] **WU5 — Frontend translation: `error_code` → i18n key.** One map, both locales, specific
  copy per code family. `ErrorDisplay.tsx` keeps the code in the header as diagnostics and stops
  using server prose as the headline. This is the slice the user sees.

## WU3 taxonomy — 20 codes for 32 sites (proposed, reviewed as one list)

Derived by reading every raise site's `status_code` + `detail` on `main` @ `414c829`, not by
inventing names per file. **Fewer codes than sites is the point**: the same English sentence
appears in several places, so one code covers them and the frontend needs one translation each.

| Code | HTTP | Covers | Source prose |
| --- | --- | ---: | --- |
| `AUTH_TOKEN_INVALID` | 401 | 4 | "Invalid or missing authentication token" (`dependencies.py:88,102,118,126`) |
| `NOT_A_WORKSPACE_MEMBER` | 403 | 7 | "Not a member of this workspace" (`dependencies.py:221,292`; `tasks.py:165`; `extractions.py:108`; `stories.py:84,152,166`) |
| `ADMIN_ACCESS_REQUIRED` | 403 | 1 | "Admin access required" (`dependencies.py:239`) |
| `OWNER_ACCESS_REQUIRED` | 403 | 1 | "Only the workspace owner can perform this action" (`dependencies.py:257`) |
| `WORKSPACE_NOT_FOUND` | 404 | 1 | `f"Workspace with id '{id}' not found"` (`dependencies.py:214`) |
| `WORKSPACE_SLUG_TAKEN` | 409 | 1 | `f"Workspace with slug '{slug}' already exists"` (`workspaces.py:175`) |
| `OWNER_ROLE_IMMUTABLE` | 400 | 1 | "The workspace owner's role cannot be changed. Transfer ownership first." (`workspaces.py:262`) |
| `PROJECT_NOT_IN_WORKSPACE` | 403 | 2 | "This project does not belong to the specified workspace" (`projects.py:99`; `stories.py:351`) |
| `PROJECT_ENDPOINT_REMOVED` | 410 | 1 | 410 prose (`projects.py:51`) |
| `STORY_NOT_IN_WORKSPACE` | 403 | 1 | "This user story does not belong to the specified workspace" (`extraction.py:137`) |
| `EXTRACTION_NOT_FOUND` | 404 | 1 | `f"Extraction '{id}' not found"` (`extraction.py:278`) |
| `EXTRACTION_ENDPOINT_REMOVED` | 410 | 1 | 410 prose (`extraction.py:75`) |
| `DUPLICATE_USER_STORY` | 409 | 1 | `f"User story with the same actor… Existing story ID: {id}"` (`stories.py:94`) |
| `UNSUPPORTED_EXPORT_FORMAT` | 400 | 1 | `f"Unsupported format '{f}'. Supported formats: json, markdown"` (`export.py:90`) |
| `CUSTOM_PROVIDER_NOT_FOUND` | 404 | 2 | "Custom provider not found" (`workspace_settings.py:362,392`) |
| `PROVIDER_NOT_IN_WORKSPACE` | 403 | 1 | "This custom provider does not belong to the specified workspace" (`workspace_settings.py:367`) |
| `PROVIDER_DUPLICATE_NAME` | 409 | 2 | `f"Custom provider '{name}' already exists in this workspace"` (`workspace_settings.py:330,385`) |
| `PROVIDER_NAME_BUILTIN` | 409 | 1 | `f"'{name}' is a built-in provider and cannot be registered as a custom one"` (`workspace_settings.py:268`) |
| `PROVIDER_NAME_RESERVED` | 409 | 1 | `f"'{name}' is reserved by the provider selector"` (`workspace_settings.py:273`) |
| `PROVIDER_MODELS_UNREACHABLE` | 502 | 1 | `f"Failed to fetch models from {provider}: {reason}"` (`workspace_settings.py:695`) |

Notes for whoever reviews the list:

- **403/401 dominate: 14 of 32 sites are access control.** That is the English a real user hits
  most, which is why WU3 starts with `dependencies.py`.
- `PROVIDER_NAME_BUILTIN` vs `PROVIDER_NAME_RESERVED` are separate because the remediation differs
  (pick another name vs. never register a built-in). Collapsing them would give the frontend one
  sentence for two different mistakes.
- The two 410s get distinct codes: one merged `ENDPOINT_REMOVED` would not say *which* endpoint is
  gone, and the whole purpose of the 410 is to point a stale client at its replacement.
- Interpolation stays in `detail`, never in a code (`f"Workspace with id '{id}' not found"` keeps
  its id). Codes are a closed set; prose is open-ended.
- The 6 already-coded sites are **not** in this table — `INVALID_STATE_TRANSITION`,
  `LLM_CONFIG_INCOMPLETE` and the three `IMPORT_*` keep their names and move level in WU4.

## Non-goals

- No backend localization, no `Accept-Language` negotiation, no persisted language preference.
- No change to `detail` prose wording.
- No HTTP status-code changes.
- Not in this feature: the two hand-maintained mirrors (`create_duplicate_error`,
  `llmModelsFetchError`) get folded into the map only if WU5 makes that mechanical.

## Risks

- **Two deploys, one contract.** Backend and frontend ship independently, so WU4 must be
  frontend-tolerant of both shapes or there is a broken window. WU1-WU3 are additive for the
  frontend (it ignores `type` today), so they are safe to ship alone.
- **Code-name sprawl.** 32 new codes invented by whoever edits each file drifts. Mitigation: a
  single `api/error_codes.py` registry, grep-able, reviewed as one list.
- **A breaking contract on a thesis-facing public API.** `docs/api.md` is public. WU1 should say
  plainly in the PR body that `type` is gone.
- **Envelope guard drift.** Without a permanent test, a future handler re-adds `type`. WU1's guard
  test is what makes D2 self-enforcing.

## Evidence log

- `556a25e` `fix(error-display): show a translated headline for save failures (#25)` — the
  predecessor slice; its follow-up section is where this feature was announced.
- Measurement in "Established facts" is from a read-only audit (`gentle-ai-explore`, 2026-09-28)
  plus direct re-verification in this session of: the 9 `["type"]` assertions, the 57 domain
  exception raises, the absence of full-key-set assertions, the zero frontend consumers of
  lowercase codes, and commitizen's bump maps.

## Verification

**WU1 — run and verified on this tree (2026-09-28).**

- `pytest -q -m unit` → **236 passed** (baseline at `HEAD` measured in a throwaway worktree: 221;
  the +15 is the new guard).
- `pytest -q` — the command CI actually runs (`.github/workflows/ci.yml:44`) → **990 passed, 21 skipped**.
- `ruff check src tests` → passed. `ruff format --check src tests` → 245 files already formatted.
- **Mutation check of the guard**: re-adding `"type"` to one handler by hand → 1 failed, 14 passed.
- **Mutation check of the 9 integration-surface assertions**: reverting `ENTITY_NOT_FOUND` to
  `"type": "entity_not_found"` → **exactly 9 failed, 63 passed** across the four files, one per
  assertion site predicted by the audit. This is what proves the updated assertions execute and bite.

### WU2 — run and verified on this tree (2026-09-28)

`error_codes.py` registry (16 constants), `ApiError` + `api_error_handler`, and
`request_validation_error_handler` registered in `app.py`.

- `pytest -q -m unit` → **244 passed** (236 after WU1 + 8: 7 unit-handler tests + 1 route test).
- `pytest -q` (CI's command) → **998 passed, 21 skipped** (baseline 990 + 8).
- `ruff check src tests` and `ruff format --check` → clean (247 files formatted).
- **422 fidelity verified by experiment, not by trusting the handler's comment.** A minimal FastAPI
  app (0.139.0) with the same invalid body was hit twice, without and with a handler using
  `jsonable_encoder(exc.errors())`: the two `detail` lists are **deep-equal**, and this version
  emits no `url` key — which contradicts what "FastAPI adds `url` since 0.102" would predict, so
  the observation replaced the recollection. Default body measured:
  `[{"type": "missing", "loc": ["body", "name"], "msg": "Field required", "input": {...}}, …]`.
- **Constraint honored, checked by grep, not by report**: `grep -n "StarletteHTTPException\|add_exception_handler(40[45]" app.py`
  matches only the comment explaining why it is *not* registered. No `HTTPException` call site moved.
- Teeth: pointing `ApiError`'s handler at the old nested shape fails 3 tests — exactly the 3
  `ApiError` parametrised cases. `ApiError` has **no production caller yet**, by design: WU3 gives it 32.
- Cleanup the parent did after the handoff: the RED-phase `print("CURRENT 422 BODY: …")` and its
  `import json` were removed from the route test; the observed body now lives in a comment next to
  the assertions that justify them.

### Two claims in this doc that were wrong, and what replaced them

- I wrote that the 9 assertions "cannot be run — Docker is off". **False.** The `integration`
  marker lives only in `tests/test_integration/`; nothing in `tests/test_api/` carries it, so
  those tests run in the default suite against the in-process app, no daemon required. They ran.
  The mutation check above replaced the assumption with evidence.
- The handoff baseline of "264 unit tests" does not reproduce. Measured at `HEAD`: **221 marked
  `unit`**, **990 collected and run by bare `pytest -q`**. `AGENTS.md` still advertises "264 unit
  tests and 356 integration tests" and says bare `pytest -q` "requires Docker" — both stale.
  Logged as a follow-up, not fixed here: it is documentation drift, not this feature.
- Process note: the guard shipped **without `@pytest.mark.unit`**, so it was silently deselected by
  the `-m unit` gate and would have looked like +0 tests. Caught only because the baseline was
  measured rather than assumed. A test that no gate selects is a test that does not exist.

### WU5 — run and verified on this tree (2026-09-28)

Shipped **before** WU3/WU4, against the owner's original "backend first" order, because WU2 changed
the arithmetic: the backend already codes 57 domain raises + the 422, so the missing piece was the
map, not more codes. Surfaced and re-approved rather than silently reordered.

- **The chokepoint is real, and measured before writing:** `grep -rn "friendlyMessage="` → 7
  consumers, 4 of them passing server prose (`*.message`) and 3 passing translated copy.
  No consumer was edited; the headline priority lives in `ErrorDisplay.tsx:155`.
- **Copy corrected in review, twice, for the same reason this thread exists.** The grouping produced
  `LLM_MODEL_NOT_FOUND` → "refresh the page" (the missing thing is the model; the fix is in the
  settings) and `PARSE_ERROR` → "the model failed to respond" (it responded; the reply was
  unreadable). Both rewritten in both locales, reusing the file's established "Configuración" and
  lowercase "settings" instead of coining synonyms.
- **21 keys, not the 22 the parent asked for**: the 6 nested sites carry 5 distinct codes
  (`IMPORT_FILE_TOO_LARGE` covers `stories.py:370` and `:382`). Corrected by the worker and verified.
- `npm test -- --run` → **52 files / 591 tests** (baseline 50/575), key-parity and neutral-Spanish
  guards included. `tsc --noEmit` → clean. `npm run build` → Complete.
- **Three independent mutation checks, all run by the parent, not reported by the worker:**
  dropping the headline priority fails 2 `ErrorDisplay` tests; dropping the top-level `error_code`
  read fails 4 transport tests; **adding a code to `error_codes.py` with no translation fails the
  mirror** with a message naming both numbers to update. The first attempt at mutation 1 was a
  no-op — the parent's `replace` string did not match the real source — and "23 passed" was the
  tell that the *test of the test* had failed, not that the code was safe.

## Follow-ups

- **`AGENTS.md` test-surface drift**: "264 unit / 356 integration" and "bare `pytest -q` … requires
  Docker" are both contradicted by measurement (236/221 marked `unit`; 990 run without Docker;
  `integration` only in `tests/test_integration/`). Same defect class as the copy overclaims this
  whole thread started from — a doc asserting more than the repo does.
- **Every new test must carry `@pytest.mark.unit`**, or bare `pytest -q` runs it while `-m unit`
  does not, and the local gate under-reports. Worth enforcing mechanically, not by memory.
- **Mirror guard is the WU3 contract.** `error-codes.test.ts` pins `EXPECTED_REGISTRY_COUNT = 16`
  and a 21-key map: WU3 must update the registry, the map and those two numbers in one change, or
  CI fails. That is deliberate friction on the silent-degradation path.
- Worker handoff quality note: it reported `frontend/src/lib/error-codes.test.ts` as changed when
  the file is at `src/lib/__tests__/error-codes.test.ts`. The path was wrong, the placement was
  right — a reminder to check `git status` rather than trust a file list. Its `git checkout --`
  during mutation testing also discarded its own GREEN implementation and re-applied it by hand,
  which is why the source was read back before being believed.
- 422 bodies: `RequestValidationError` default detail is a list of `{type, loc, msg, input}` —
  WU2 decides whether to give it an app code (`REQUEST_VALIDATION_FAILED`) or leave it.
- 404/405 from Starlette have no app code at all.
- `InsufficientRole` has a handler but is **never raised** anywhere in `backend/src/` — dead code,
  and its `type` value is in the list WU1 renames. Decide: delete or wire it up.
- Sentry (reserved for `1.0.0`) will want these codes; keeping them in one registry is the
  precondition.
