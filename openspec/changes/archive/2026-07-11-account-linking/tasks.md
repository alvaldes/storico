# Tasks: Account Linking

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~300 (additions + deletions) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-always |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full account-linking backend | PR 1 | Single PR — under 400 lines, all files interdependent |

---

## Phase 1: Foundation — New Entity & ORM

- [x] **T-001** — Create `UserAccount` domain entity (`domain/entities/user_account.py`) and export from `domain/entities/__init__.py`
  - Deps: None
  - AC: Frozen dataclass with `user_id`, `provider`, `provider_id`, `id`, `created_at`. Importable via `from storico.domain.entities import UserAccount`.
  - Effort: S

- [x] **T-002** — Create `UserAccountModel` ORM (`infra/database/models/user_account.py`) and register in `infra/database/models/__init__.py`
  - Deps: T-001 (entity exists for reference pattern)
  - AC: Model has `id` (UUID PK), `user_id` (FK→users.id CASCADE), `provider`, `provider_id`, `created_at`, `UNIQUE(provider, provider_id)`, `user` relationship. Alembic `Base.metadata` sees it.
  - Effort: S

- [x] **T-003** — Create Alembic migration `XXXX_account_linking.py` (revision depends on `3fefad99b84d`)
  - Deps: T-002 (model registry must include UserAccountModel)
  - AC: Upgrade creates `user_accounts`, inserts `auth_provider`/`auth_id` from users, adds FK + UNIQUE, drops old columns + constraint. Downgrade restores columns and drops table. Full transactional rollback.
  - Effort: M

## Phase 2: Core Implementation

- [x] **T-004** — Remove `auth_provider`/`auth_id` from `User` entity and `UserModel` ORM; add `accounts` relationship to `UserModel`
  - Deps: T-003 (migration exists so schema is consistent)
  - AC: `User` entity has 6 fields (removed 2). `UserModel` drops 2 columns, adds `accounts: Mapped[list[UserAccountModel]]`. `__table_args__` drops `uq_users_auth_provider_auth_id`.
  - Effort: S

- [x] **T-005** — Update `UserRepository` port (add `link_account()`) and rewrite `SQLAlchemyUserRepository` (3 changes: remove auth fields from `save`/`_to_domain`/`_to_orm_kwargs`, rewrite `find_by_auth` with JOIN, implement `link_account`)
  - Deps: T-001 (UserAccount entity), T-004 (User entity without auth fields)
  - AC: `save()` accepts `User` without auth fields. `_to_domain()` constructs `User` without auth fields. `find_by_auth(provider, provider_id)` JOINs `user_accounts` → returns `User`. `link_account(user_id, provider, provider_id)` inserts row → returns `UserAccount`; raises `DuplicateEntity` on UNIQUE violation.
  - Effort: M

- [x] **T-006** — Rewrite `POST /auth/sync` endpoint with 3-step flow; update `UserResponse` schema (keep `auth_provider`/`auth_id`, now route-populated); update `GET /users/me` to build `UserResponse` without entity auth fields
  - Deps: T-005 (needs `link_account` and updated `find_by_auth`)
  - AC: Step (a) `find_by_auth` → update profile → `UserResponse` from payload. Step (b) `find_by_email` → `link_account` → respond. Step (c) create user + `link_account` → respond. `UserResponse` fields `auth_provider`/`auth_id` present and populated. `GET /users/me` constructs `UserResponse` without referencing `User.auth_provider`.
  - Effort: M

## Phase 3: Testing

- [x] **T-007** — Update repository tests: remove auth fields from `User()` construction in existing tests; add `test_link_account_success` and `test_link_account_duplicate`
  - Deps: T-005 (repo implementation ready)
  - AC: All existing tests pass. New tests verify: `link_account` creates `UserAccount` row; duplicate `(provider, provider_id)` raises `DuplicateEntity`. `find_by_auth` returns `User` from JOIN.
  - Effort: M

- [x] **T-008** — Update and add auth endpoint integration tests: update existing payloads (implicit — `UserResponse` checks still pass); add scenarios for step (a) returning user, step (b) email link, step (c) new user
  - Deps: T-006 (sync endpoint rewritten)
  - AC: All existing auth tests pass with the same payloads. New tests: "same email different provider links accounts", "new provider creates user_account", "profile update via find_by_auth".
  - Effort: M

## Phase 4: Verification

- [x] **T-009** — Run full test suite, fix any failures; run migration forward + rollback in dev to verify data integrity
  - Deps: T-007, T-008 (tests written and passing)
  - AC: `pytest` passes with 0 failures. `alembic upgrade head` and `alembic downgrade -1` succeed without data loss.
  - Effort: S

---

## Dependency Graph

```
T-001 (UserAccount entity)
  └── T-002 (UserAccountModel ORM)
        └── T-003 (Alembic migration)
              └── T-004 (User entity + Model cleanup)
                    └── T-005 (Repository rewrite)
                          └── T-006 (API sync rewrite + schemas)
                                └── T-008 (API integration tests)
                    └── T-007 (Repository tests)
                          └── T-009 (Verification)
```

Parallelism: T-007 and T-008 can proceed after T-006 completes. T-001 through T-006 must be strictly sequential.

---

## Review Workload Summary

- **Estimated total**: ~300 lines (additions + deletions)
- **Per-task**:
  - T-001: ~20 lines (new entity)
  - T-002: ~35 lines (new ORM)
  - T-003: ~65 lines (migration)
  - T-004: ~15 lines (modify entity + model)
  - T-005: ~45 lines (repo rewrite)
  - T-006: ~50 lines (sync + schema updates)
  - T-007: ~40 lines (repo tests)
  - T-008: ~40 lines (API tests)
  - T-009: ~0 lines (verification only)
- **Budget risk**: Low — comfortably under 400 lines
- **Recommendation**: Single PR. All changes are tightly coupled and share a single migration.
