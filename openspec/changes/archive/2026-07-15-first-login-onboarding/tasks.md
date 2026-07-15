# Tasks: First Login Onboarding Flow

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 600-850 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 = Backend (Phases 1-2), PR 2 = Frontend (Phases 3-4), PR 3 = Tests (Phase 5) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend: domain + ORM + schemas + endpoint + rename UC | PR 1 | Base boundary: main; tests included |
| 2 | Frontend: store + API + modal + i18n | PR 2 | Base boundary: main; depends on PATCH endpoint existing |
| 3 | Tests: backend + frontend coverage | PR 3 | Base boundary: main; per-file tests, can be distributed |

## Phase 1: Backend Foundation (Domain + ORM + Schema + Use Case)

- [x] 1.1 Add `is_first_login: bool = False` field to `domain/entities/user.py` (frozen dataclass, uses `replace()` for updates)
- [x] 1.2 Add `is_first_login` column (`Boolean`, default `False`) to `infrastructure/database/models/user.py`
- [x] 1.3 Map `is_first_login` in `_to_domain()` / `_to_orm_kwargs()` of `infrastructure/database/repositories/user_repository.py`
- [x] 1.4 Add `is_first_login: bool` to `UserResponse` and create `OnboardingRequest` schema in `api/schemas/user.py`
- [x] 1.5 Create `application/workspaces/rename_workspace.py` — `RenameWorkspaceUseCase` reusing `generate_slug` from `create_workspace.py`

## Phase 2: Backend Endpoints (Auth Sync + PATCH)

- [x] 2.1 Update `api/routes/auth.py` step (c) response to return `is_first_login=True`; steps (a/b) return `False`
- [x] 2.2 Create `PATCH /api/v1/users/me/onboarding` in `api/routes/users.py` — sets `is_first_login=False`, optionally renames workspace, returns `{ success: true }`

## Phase 3: Frontend Core (API Client + Store + User API)

- [x] 3.1 Add `patch<T>(path, body?)` method to `frontend/src/lib/api.ts` ApiClient class
- [x] 3.2 Add `isFirstLogin: boolean` to `authStore` state + `setOnboardingDone()` action in `frontend/src/stores/authStore.ts`
- [x] 3.3 Add `completeOnboarding(workspaceName?: string)` to `frontend/src/lib/user-api.ts` calling `PATCH /api/v1/users/me/onboarding`

## Phase 4: Frontend UI (Modal + Dashboard + i18n)

- [x] 4.1 Create `frontend/src/components/react/OnboardingModal.tsx` — 3-step modal (rename workspace, tutorial cards, optional LLM config) with progress bar, skip/X on every step, "Get Started" final action
- [x] 4.2 Update `frontend/src/components/react/Dashboard.tsx` — import `useAuthStore`, conditionally render `<OnboardingModal>` when `isFirstLogin === true`
- [x] 4.3 Add `onboarding.*` translation keys to `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`

## Phase 5: Tests

- [x] 5.1 Backend: add `is_first_login` assertions to existing auth sync tests (step (c) = true, steps (a/b) = false)
- [x] 5.2 Backend: integration tests for `PATCH /api/v1/users/me/onboarding` — authenticated call sets flag false, optional rename, idempotency
- [x] 5.3 Frontend: unit test — `authStore.setOnboardingDone()` sets `isFirstLogin` to false
- [x] 5.4 Frontend: component test — `OnboardingModal` renders with 3 steps and skip behavior
- [x] 5.5 Frontend: component test — Dashboard renders modal conditionally on `isFirstLogin`
