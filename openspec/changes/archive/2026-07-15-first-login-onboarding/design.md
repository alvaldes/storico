# Design: First Login Onboarding Flow

## Technical Approach

Hybrid backend+frontend. Backend adds `is_first_login` flag to `User` entity + ORM + schema, returns it on auth sync step (c), and exposes a `PATCH /api/v1/users/me/onboarding` endpoint. Frontend stores the flag in `authStore`, conditionally renders an `<OnboardingModal>` React island in `Dashboard.tsx`. Modal has 3 steps (rename workspace, tutorial cards, optional LLM config), all skippable.

No data migration needed — new column, default `false`.

## Architecture Decisions

### Decision: Flag storage

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Add `is_first_login` to `User` entity + ORM | Adds 1 field to domain entity; entity is `frozen` so `replace()` needed for updates | ✅ Adopted |
| Keep flag only at ORM/schema level | Bypasses domain layer; breaks hexagonal consistency | ❌ Rejected |
| Separate `UserOnboarding` table | Over-engineered for a single boolean updated once | ❌ Rejected |

### Decision: Onboarding endpoint

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `PATCH /api/v1/users/me/onboarding` | Dedicated, clear scope; keeps workspace CRUD separate | ✅ Adopted |
| Reuse `PUT /workspaces/{id}` + separate user flag endpoint | Two calls from modal; more surface area | ❌ Rejected |

### Decision: Workspace rename in PATCH

| Option | Tradeoff | Decision |
|--------|----------|----------|
| In the PATCH body as optional `workspace_name` | Single call to mark complete + rename; modal calls it once | ✅ Adopted |
| Separate API call from modal | Requires two sequential API calls; more error states | ❌ Rejected |

### Decision: Frontend rendering

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Modal in `Dashboard.tsx` checked via `authStore.isFirstLogin` | One conditional, no route guards needed | ✅ Adopted |
| Route-level guard redirecting to `/onboarding` | More routing complexity; breaks skip workflow | ❌ Rejected |

## Data Flow

```
Auth login
  → Auth.js JWT callback → POST /api/v1/auth/sync (step c)
  → User created with is_first_login=True in DB
  → Response: { ..., is_first_login: true }
  → Frontend stores in authStore.isFirstLogin

Dashboard mounts
  → authStore.isFirstLogin === true
  → <OnboardingModal> renders as overlay (3 steps)

User completes or skips
  → PATCH /api/v1/users/me/onboarding { workspace_name?: string }
  → Backend: set is_first_login=False, optionally rename workspace
  → Response: { success: true }
  → Frontend: authStore.setOnboardingDone()
  → Modal closes, dashboard content visible

Returning user (steps a/b)
  → is_first_login=False in DB
  → Response: { ..., is_first_login: false }
  → Frontend: never renders modal
```

## File Changes

### Backend (Python)

| File | Action | Description |
|------|--------|-------------|
| `domain/entities/user.py` | Modify | Add `is_first_login: bool = False` field |
| `infrastructure/database/models/user.py` | Modify | Add `is_first_login` column (Boolean, default False) |
| `infrastructure/database/repositories/user_repository.py` | Modify | Map field in `_to_entity()` / `_to_model()` |
| `api/schemas/user.py` | Modify | Add `is_first_login: bool` to `UserResponse`, add `OnboardingRequest` schema |
| `api/routes/auth.py` | Modify | Step (c) response includes `is_first_login=True`; steps (a/b) include `False` |
| `api/routes/users.py` | Modify | Add `PATCH /me/onboarding` endpoint |
| `application/workspaces/rename_workspace.py` | Create | New use case: rename workspace by user+workspace (reuses slug logic from `create_workspace.py`) |

### Frontend (TypeScript/React)

| File | Action | Description |
|------|--------|-------------|
| `stores/authStore.ts` | Modify | Add `isFirstLogin: boolean` to state + `setOnboardingDone()` action |
| `lib/user-api.ts` | Modify | Add `completeOnboarding()` function calling `PATCH /me/onboarding` |
| `components/react/Dashboard.tsx` | Modify | Import `useAuthStore`, render `<OnboardingModal>` conditionally |
| `components/react/OnboardingModal.tsx` | Create | 3-step modal: rename workspace, tutorial cards, optional LLM config |
| `i18n/en.json` | Modify | Add `onboarding.*` keys |
| `i18n/es.json` | Modify | Add `onboarding.*` keys |

## Interfaces / Contracts

### Backend — new schema

```python
# api/schemas/user.py
class OnboardingRequest(BaseModel):
    workspace_name: str | None = None  # optional rename

class UserResponse(BaseModel):
    # ... existing fields ...
    is_first_login: bool
```

### Backend — new endpoint

```
PATCH /api/v1/users/me/onboarding
Content-Type: application/json

{ "workspace_name": "My Team" }  # optional

→ 200 { "success": true }
→ 401 Unauthorized (no session)
```

### Frontend — authStore update

```typescript
interface AuthState {
  user: AuthUser | null
  loading: boolean
  isFirstLogin: boolean          // new
  setUser: (user: AuthUser | null) => void
  setOnboardingDone: () => void  // new
  setLoading: (loading: boolean) => void
  clear: () => void
}
```

### Frontend — API client

```typescript
// lib/user-api.ts
export async function completeOnboarding(workspaceName?: string): Promise<void> {
  await api.patch('/api/v1/users/me/onboarding',
    workspaceName ? { workspace_name: workspaceName } : undefined
  );
}
```

Note: `api.patch()` does not exist yet — add it to `ApiClient` class.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit — entity | `User(is_first_login=True)` creates correctly | pytest |
| Unit — schema | `OnboardingRequest` accepts/omits `workspace_name` | pytest |
| Integration — PATCH | Authenticated call sets `is_first_login=False` | pytest + test client |
| Integration — PATCH | Optional workspace rename updates workspace name | pytest + test client |
| Integration — PATCH | Idempotency — second call returns 200, no error | pytest + test client |
| Integration — auth sync | Step (c) returns `is_first_login=True` | pytest + test client |
| Integration — auth sync | Steps (a/b) return `is_first_login=False` | pytest + test client |
| Unit — frontend | `authStore.setOnboardingDone()` sets flag to false | vitest |
| Component — frontend | `OnboardingModal` renders/steps/skip behavior | vitest + RTL |
| Component — frontend | Dashboard renders modal conditionally on `isFirstLogin` | vitest + RTL |

## Migration / Rollout

No migration needed. New column `is_first_login` with SQL default `FALSE`. Existing users automatically get `false` on first read (no migration script required). Rollback: revert all file changes, remove column via Alembic downgrade.

## Open Questions

None.
