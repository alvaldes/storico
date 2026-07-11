# Proposal: Account Linking

## Intent

`users` has `auth_provider`/`auth_id` as direct columns + `UNIQUE(email)`. Google login (`a@b.com`) then GitHub with the same email → `IntegrityError`. User is stuck with no way to link accounts. Fix that.

## Scope

### In Scope
- `user_accounts` table: `(user_id, provider, provider_id, created_at)`
- Migration: create table, migrate existing data, drop columns from `users`
- `UserAccount` entity. `User` loses `auth_provider`/`auth_id`
- `link_account()` on repo; `find_by_auth()` queries `user_accounts`
- `/auth/sync` rewrite: find-by-provider → fallback-by-email → link or create
- `UserResponse` derives provider from current session's account
- Tests for new linking scenarios

### Out of Scope
- Frontend "link another provider" UI
- Unlinking or primary account management
- Multi-provider-unique constraints (one row per provider pair)

## Capabilities

### New
- `account-linking`: Email-based OAuth merging — same email, different provider creates `user_account` row instead of erroring.

### Modified
- `user-auth`: `/auth/sync` now tries provider → email fallback → link or create.

## Approach

1. `user_accounts` table with FK to `users.id`, unique on `(provider, provider_id)`
2. Migration: `INSERT INTO user_accounts SELECT ... FROM users`, drop old columns
3. Sync: (a) `find_by_auth` → update profile; (b) `find_by_email` → link; (c) neither → create + link
4. `UserResponse` populates provider from session account, not entity

## Affected Areas

| Area | Impact |
|------|--------|
| `domain/entities/user.py` | Remove `auth_provider`/`auth_id` |
| `domain/entities/user_account.py` | New entity |
| `domain/ports/user_repository.py` | Add `link_account()` |
| `infra/database/models/user.py` | Drop columns |
| `infra/database/models/user_account.py` | New ORM model |
| `infra/database/repositories/user_repository.py` | Rewrite `save`, `find_by_auth` |
| `infra/database/alembic/versions/0003...py` | New migration |
| `api/routes/auth.py` | Rewrite sync |
| `tests/` | Update + new auth integration tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Orphan `user_accounts` rows | Low | CASCADE on FK |
| Existing sessions break | Low | JWT has `user.id` — preserved by migration |
| Concurrent sync race | Low | UNIQUE constraint + retry |

## Rollback Plan

`alembic downgrade -1` drops `user_accounts`, restores columns. Data in `user_accounts` lost — backup first.

## Success Criteria

- [ ] Google user can link GitHub with same email without error
- [ ] Existing users work without re-auth
- [ ] `UserResponse` reflects current session provider
- [ ] Existing tests pass (except those testing removed columns)
