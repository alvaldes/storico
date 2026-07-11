# Design: Account Linking

## Technical Approach

Separate provider credentials from `users` into a `user_accounts` table. Rewrite `/auth/sync` as a 3-step flow: find-by-provider → fallback-by-email → link-or-create. `UserResponse` derives provider from the current session, not the entity. Single migration with transactional rollback.

Maps to proposal's approach and specs FR-001 through FR-005, NFR-001 through NFR-003.

---

## Architecture Decisions

### Decision: UserAccount entity without domain service

| Option | Tradeoff | Decision |
|--------|----------|----------|
| New `AccountLinkingService` in domain | Cleaner separation but extra abstraction for CRUD | Not chosen |
| `UserAccount` entity + methods on `UserRepository` | Follows existing pattern (entity + repo) | **Chosen** — aligns with how `Project`, `Task` work in current codebase |

Repository owns the linking — `link_account()` is a single-table INSERT. No domain logic beyond "create a row."

### Decision: find_by_auth queries user_accounts with JOIN

| Option | Tradeoff | Decision |
|--------|----------|----------|
| New `UserAccountRepository` | More files, more DI wiring | Not chosen |
| Methods on `UserRepository` | Only place that returns `User` entities, keeps finder API stable | **Chosen** — `find_by_auth(provider, provider_id)` now does `SELECT users JOIN user_accounts` |

### Decision: UserResponse provider from route param

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Derive from `get_current_user` lookup | `get_current_user` returns `User` (no accounts), would need another query | Not chosen |
| Route receives provider from `AuthSyncRequest` | Explicit, no extra query, sync already has the data | **Chosen** — sync endpoint already has `auth_provider`/`auth_provider_id` in payload, uses them in response |

---

## Data Flow

```
POST /auth/sync (provider=P, id=I, email=E)
  │
  ├─ (a) find_by_auth(P, I) ──→ user_accounts JOIN users ──→ found → update profile → respond
  │
  ├─ (b) not found → find_by_email(E) ──→ found → link_account(user.id, P, I) → respond
  │
  └─ (c) neither → create_user(E) → link_account(new.id, P, I) → respond
```

---

## Data Model Changes

### New: `user_accounts` table

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, default uuid4 |
| `user_id` | UUID | FK → users(id) ON DELETE CASCADE, NOT NULL |
| `provider` | VARCHAR(50) | NOT NULL |
| `provider_id` | VARCHAR(255) | NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| | | UNIQUE(provider, provider_id) |

### Modified: `users` table (dropped columns)

- Remove `auth_provider` (VARCHAR 50, NOT NULL)
- Remove `auth_id` (VARCHAR 255, NOT NULL)
- Remove `uq_users_auth_provider_auth_id` unique constraint
- `email` UNIQUE constraint stays

### New entity: `UserAccount`

```python
@dataclass(frozen=True, slots=True)
class UserAccount:
    user_id: UUID
    provider: str
    provider_id: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### Modified entity: `User`

Remove `auth_provider: str` and `auth_id: str` fields.

### New ORM: `UserAccountModel`

```python
class UserAccountModel(Base):
    __tablename__ = "user_accounts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_user_accounts_provider_provider_id"),
    )

    user: Mapped["UserModel"] = relationship(back_populates="accounts")
```

### Modified ORM: `UserModel`

- Remove `auth_provider`, `auth_id` columns
- Remove `uq_users_auth_provider_auth_id` from `__table_args__`
- Add `accounts: Mapped[list["UserAccountModel"]] = relationship(back_populates="user", lazy="selectin")`

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `domain/entities/user_account.py` | Create | `UserAccount` dataclass |
| `domain/entities/user.py` | Modify | Remove `auth_provider`, `auth_id` |
| `domain/entities/__init__.py` | Modify | Export `UserAccount` |
| `infra/database/models/user_account.py` | Create | `UserAccountModel` ORM |
| `infra/database/models/user.py` | Modify | Drop columns + `auth_provider`/`auth_id`, add `accounts` relationship |
| `infra/database/models/__init__.py` | Modify | Export `UserAccountModel` |
| `infra/database/repositories/user_repository.py` | Modify | `save()` drops auth fields, `find_by_auth()` JOINs `user_accounts`, add `link_account()` |
| `infra/database/alembic/versions/0004_account_linking.py` | Create | Migration: create `user_accounts`, migrate data, drop old columns |
| `api/routes/auth.py` | Modify | 3-step sync flow, `UserResponse` derives provider from payload |
| `api/schemas/user.py` | Modify | `UserResponse` keeps `auth_provider`/`auth_id` as response fields (populated from session) |
| `tests/test_api/test_auth.py` | Modify | Update existing tests, add linking scenario tests |
| `tests/test_repositories/test_user_repo.py` | Modify | Update `save()` tests without auth fields, add `link_account()` tests |

---

## Interfaces / Contracts

### Modified: `UserRepository`

```python
class UserRepository(ABC):
    @abstractmethod
    async def save(self, user: User) -> User:
        """Persist a user. `User` no longer has auth fields."""

    @abstractmethod
    async def find_by_auth(self, provider: str, provider_id: str) -> User | None:
        """Find by querying user_accounts JOIN users."""

    @abstractmethod
    async def link_account(self, user_id: UUID, provider: str, provider_id: str) -> UserAccount:
        """Create a user_account row. Raises DuplicateEntity on (provider, provider_id) conflict."""
```

### Modified: `UserResponse`

```python
class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    auth_provider: str      # from session, not entity
    auth_id: str            # from session, not entity
    avatar_url: str | None = None
    created_at: datetime
```

### Sync endpoint response contract

```python
# Returns different status codes:
# - 200: existing user found by provider (update) or by email (link)
# - 201: new user created

class SyncResult(BaseModel):
    status: Literal["existing", "linked", "created"]
    user: UserResponse
```

---

## Sync Endpoint Flow (Detailed)

### `POST /auth/sync`

```
1.  existing = repo.find_by_auth(payload.provider, payload.provider_id)
2.  if existing:
        # Step (a) — returning user
        user = User(id=existing.id, email=..., name=..., avatar_url=...)
        repo.save(user)   # update profile only
        return UserResponse(auth_provider=payload.provider, auth_id=payload.provider_id, ...)

3.  email_user = repo.find_by_email(payload.email)
4.  if email_user:
        # Step (b) — same email, different provider → link
        repo.link_account(email_user.id, payload.provider, payload.provider_id)
        user = User(id=email_user.id, email=..., name=..., avatar_url=...)
        repo.save(user)
        return UserResponse(...)

5.  # Step (c) — new user
    user = User(email=payload.email, name=..., avatar_url=...)
    repo.save(user)
    repo.link_account(user.id, payload.provider, payload.provider_id)
    return UserResponse(...)
```

### Error Handling

| Condition | Mechanism | Behavior |
|-----------|-----------|----------|
| Race: concurrent link_account for same (provider, provider_id) | UNIQUE constraint + IntegrityError catch | `link_account` catches `IntegrityError`, falls back to `find_by_auth`, retries once |
| Race: concurrent user creation for same email | `uq_users_email` constraint + existing `save()` behavior | `DuplicateEntity` propagates — caller retries the full sync |
| DB connection failure | Existing `RepositoryError` in `save()` | Propagates as 500 |

---

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (repo) | `link_account` creates row, returns `UserAccount` | Direct `db_session` fixture |
| Unit (repo) | `link_account` raises `DuplicateEntity` on duplicate (provider, provider_id) | Insert same pair twice |
| Unit (repo) | `find_by_auth` queries `user_accounts JOIN users`, returns `User` | Insert user + account, then find |
| Unit (repo) | `save` without auth fields | Create `User` without `auth_provider`/`auth_id` |
| Integration (API) | Step (a): returning user updates profile | Create user+account, sync same provider, assert profile update |
| Integration (API) | Step (b): same email links accounts | Create user+account via Google, sync via GitHub with same email, assert linked |
| Integration (API) | Step (c): new user created | Sync with fresh provider+email, assert user+account created |
| Integration (API) | Existing JWT works post-migration | Create user, migrate schema in test, call `/users/me` with same `user.id` |
| Migration | Forward + rollback | In test: run upgrade, verify data in `user_accounts`, run downgrade, verify columns restored |

---

## Migration Plan

Single revision `0004` (depends on `3fefad99b84d`):

```python
def upgrade():
    # 1. Create user_accounts table
    op.create_table("user_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. Migrate existing data
    op.execute("""
        INSERT INTO user_accounts (id, user_id, provider, provider_id, created_at)
        SELECT gen_random_uuid(), id, auth_provider, auth_id, created_at
        FROM users
        WHERE auth_provider IS NOT NULL AND auth_id IS NOT NULL
    """)

    # 3. Add FK + UNIQUE after data is in place
    op.create_foreign_key(
        "fk_user_accounts_user_id_users",
        "user_accounts", "users",
        ["user_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_user_accounts_provider_provider_id",
        "user_accounts", ["provider", "provider_id"],
    )

    # 4. Drop old columns and constraints
    op.drop_constraint("uq_users_auth_provider_auth_id", "users", type_="unique")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "auth_id")


def downgrade():
    op.add_column("users", sa.Column("auth_provider", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("auth_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_auth_provider_auth_id", "users", ["auth_provider", "auth_id"])

    # Restore data (best-effort — user_ids are preserved)
    op.execute("""
        UPDATE users SET
            auth_provider = ua.provider,
            auth_id = ua.provider_id
        FROM user_accounts ua
        WHERE ua.user_id = users.id
    """)

    # Make columns NOT NULL after data restored
    op.execute("ALTER TABLE users ALTER COLUMN auth_provider SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN auth_id SET NOT NULL")

    op.drop_constraint("uq_user_accounts_provider_provider_id", "user_accounts", type_="unique")
    op.drop_constraint("fk_user_accounts_user_id_users", "user_accounts", type_="foreignkey")
    op.drop_table("user_accounts")
```

**Data integrity**: `NOT VALID` not needed — the INSERT before FK creation guarantees referential integrity. Migration is atomic within Alembic's transaction.

**Rollback**: `alembic downgrade -1`. Data in `user_accounts` is lost — back up before downgrading.

---

## Implementation Order

1. Create `UserAccount` entity → `UserAccountModel` ORM → register in `__init__.py` files
2. Create Alembic migration `0004_account_linking.py`
3. Modify `User` entity (remove auth fields) → update `UserModel` (drop columns + `accounts` rel)
4. Rewrite `SQLAlchemyUserRepository`:
   - `save()`: remove auth field mapping from `_to_orm_kwargs`
   - `_to_domain()`: remove auth fields from `User()` constructor
   - `find_by_auth()`: JOIN `user_accounts` table
   - Add `link_account()` method
5. Rewrite `POST /auth/sync` with 3-step flow
6. Update `UserResponse` schema (keep `auth_provider`/`auth_id`, now route-populated)
7. Run migration forward + verify test suite
8. Update tests:
   - Repo tests: remove auth fields from `User()` construction, add `link_account` tests
   - Auth tests: update payloads, add linking scenario tests

---

## Open Questions

- [ ] Should `/sync` return 201 for new users (step c) vs 200 for existing? Proposal mentions 201 but current endpoint always returns 200. Decision: keep 200 for backward compat — differentiate via a `status` field in response body.
- [ ] `gen_random_uuid()` in migration works on PostgreSQL — SQLite tests use `Base.metadata.create_all`, not migrations. No conflict.
