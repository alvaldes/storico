# ODD Feature: ci-postgres-integration-test

> **Status**: done — green CI run `35362462180` (backend + frontend success, 527 passed). Commits `2e729ae`, `0dc0e89`, `70be4bc`, `757ab72`, `65a8a3f`, `65ff243`, `a318ccf`, `6004f55` on `main`, pushed.
> **Superseded (import path only)**: the `testcontainers.postgres` import-path decision in D3 is
> superseded by `prod-checklist-honesty` (WU6), which moved the declared floor to
> `testcontainers>=4.15.0` and switched the import to `testcontainers.community.postgres`.
> **Created**: 2026-09-18
> **Workflow**: Organic Driven Development (ODD)

## Problem

The `backend` CI job went red on the first remote run of
`.github/workflows/ci.yml` (commit `77fe818`, which introduced
`pip install -e ".[dev]"` + `pytest -q`). Everything passes except the setup of
one test:

```
ERROR tests/test_integration/test_projects_integration.py::test_list_projects_with_counts_latency_under_500ms
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here.
526 passed, 1 error in 30.47s
```

The traceback runs through the *container readiness probe*, not through the
assertion:

```
generic.py:55: in start()      -> self._connect()
generic.py:33: in _connect()   -> engine.connect()
... MissingGreenlet
```

## Root cause (sourced, not inferred)

`pg_engine` hands the container an **async driver**:

```python
with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
```

`PostgresContainer` inherits `DbContainer._connect`, which probes readiness with
a **synchronous** SQLAlchemy engine built from that same URL:

```python
# testcontainers/core/generic.py
@wait_container_is_ready(*ADDITIONAL_TRANSIENT_ERRORS)
def _connect(self):
    import sqlalchemy
    engine = sqlalchemy.create_engine(self.get_connection_url())
    engine.connect()
```

With `driver="asyncpg"` the URL is `postgresql+asyncpg://…`, so the probe is a
sync `Engine` over an async dialect:

```
$ python -c "import sqlalchemy; e = sqlalchemy.create_engine('postgresql+asyncpg://u:p@127.0.0.1:5432/db'); print(type(e), type(e.dialect), e.dialect.is_async); e.connect()"
<class 'sqlalchemy.engine.base.Engine'> PGDialect_asyncpg True
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; ...
```

`create_engine()` does **not** reject an async dialect — it builds a sync Engine
over it, and the first `connect()` calls `await_only()` outside a greenlet. The
container itself starts fine; the probe is what explodes.

**Why it never failed locally.** `_docker_reachable()` (`test_projects_integration.py:47-67`)
returns False without a Docker socket, so the module skips on a laptop. GitHub
runners do have `/var/run/docker.sock`, so CI is the first place the fixture ever
ran. Commit `77fe818` predicted this in its own message.

**Two aggravating facts.**

1. `backend/pyproject.toml` asked for the abandoned split-package name:
   `"testcontainers-postgres>=0.0.1rc1"`. Verified in a clean venv, that resolves
   to `testcontainers-postgres 0.0.1rc1` **plus** `testcontainers-core 0.0.1rc1`
   — the 2022 layout, not the maintained `testcontainers` (4.15.0). The CI
   traceback line numbers match that legacy `generic.py` exactly
   (`container.py:77`, `generic.py:55`, `generic.py:33`, `waiting_utils.py:49`).
2. Updating the package alone would **not** have been enough on its own for the
   probe behaviour we wanted to be version-independent, and the abandoned shim
   also drags `psycopg2-binary` in as a hidden requirement.

**The second failure hiding behind the first.** `pytest-asyncio>=0.24.0`
resolves to 1.4.0 in CI, where a `scope="module"` async fixture gets its own
module event loop while every function-scoped fixture and test gets a fresh
one. Reproduced locally:

```
AssertionError: session loop differs from module loop
```

With asyncpg that is `attached to a different loop` / a pool awaiting on a dead
loop. Fixing only the probe would have moved the red line, not removed it.

## Decisions (user-approved 2026-09-18)

| # | Decision | Choice |
|---|----------|--------|
| D1 | CI policy | **Fix the test so it runs in CI** (chosen over excluding `integration` from CI). GitHub runners have Docker; this is the only real-Postgres coverage in the suite — the other 526 tests run on `sqlite+aiosqlite`. The `<500ms` assertion is accepted as a shared-runner risk, not treated as free. |
| D2 | Probe vs driver | The container keeps its **sync** driver and the test swaps the URL to `postgresql+asyncpg` itself, so the probe and the test engine never share a driver. Chosen over `driver="asyncpg"` (which relies on newer `testcontainers` probing with `psql` instead of SQLAlchemy — true since 4.9, but a version-dependent accident). |
| D3 | Dependency | Replace the abandoned `testcontainers-postgres` 0.0.1rc1 shim with `testcontainers>=4.9.0` (floor = the release whose Postgres probe is `psql`-based, so no hidden sync DBAPI is required). Import path stays `testcontainers.postgres`, which exists across 4.x — **superseded by `prod-checklist-honesty` (WU6):** the floor is now `testcontainers>=4.15.0` and the import is `testcontainers.community.postgres`. |
| D4 | Loop scope | Explicit `loop_scope="module"` on both fixtures and on the test marker. Verified working on pytest-asyncio 0.24.0 (the declared floor) and 1.4.0 (what CI installs). |

## Non-goals

- No change to `_docker_reachable()`'s silent skip. It is the reason the bug hid
  locally, but making it fail instead of skip changes behaviour for every
  machine without Docker — a separate decision.
- No change to the `<500ms` threshold, no benchmark harness, no baseline ratio.
- No `[tool.pytest.ini_options]`/`pytest.ini` global loop-scope default.
- No pin of an upper bound on `testcontainers`, no lockfile.

## Established facts (verified in code)

- `pyproject.toml` dev extra: `testcontainers-postgres>=0.0.1rc1`; `pytest-asyncio>=0.24.0`,
  resolver gives 1.4.0.
- This is the **only** module-scoped async fixture in `backend/tests/`
  (`grep -rn 'scope="module"' tests/` → 1 hit).
- `pytest.ini` has `asyncio_mode = auto` and no `filterwarnings`, so the
  `testcontainers.postgres` deprecation shim on 4.15+ cannot fail the suite.
- Modern `PostgresContainer._connect` is `psql`-based since **4.9.0**
  (`testcontainers/postgres/__init__.py:91`, `ExecWaitStrategy`/`self.exec`); 4.8.0
  waited on logs. The `[postgres]` extra is empty in both 4.9 and 4.15.
- `testcontainers.community.postgres` does not exist below **4.15.0**, so the import had to stay
  `testcontainers.postgres` under the old 4.9.0 floor. Measured by direct wheel inspection:
  `4.13.3` and `4.14.2` ship only `testcontainers/postgres/__init__.py` and no `community` package;
  `4.15.0` ships both it and a shim `testcontainers/postgres.py`. The decision it supported is
  **superseded by `prod-checklist-honesty` (WU6)**, which moved the floor to 4.15.0.
- `SQLAlchemy 2.0.52`: `make_url(...).set(drivername="postgresql+asyncpg")` →
  `create_async_engine(url)` yields `AsyncEngine` + `PGDialect_asyncpg`.
- `ruff.toml`: `select = ["E", "F", "I", "UP"]`, line-length 100, so the new
  import must be isort-ordered by `ruff check`.
- No Docker daemon on the authoring machine (`~/.docker/run/docker.sock` and
  `/var/run/docker.sock` both absent) → the container path cannot be executed
  locally, only its probe logic.

## Tasks

### T-001 — Make the integration fixture driver-safe and loop-safe

- **Status**: done (commit `2e729ae`)
- **Files to modify**:
  - `backend/tests/test_integration/test_projects_integration.py`
  - `docs/testing.md`
- **What**:
  - `pg_engine`: keep the container on its sync driver, rewrite the URL with
    `make_url(pg.get_connection_url()).set(drivername="postgresql+asyncpg")` for
    the app engine; annotate the generator correctly
    (`AsyncGenerator[AsyncEngine, None]`).
  - `pg_engine` + `pg_session` get `loop_scope="module"`; the test marker gets
    `loop_scope="module"`.
  - Correct the module docstring: the test runs in CI (Docker present) and skips
    locally without a daemon.
  - `docs/testing.md`: document the integration test's requirements (Docker) and
    the module-loop convention for module-scoped async fixtures.
- **Evidence**: `ruff check` + `ruff format --check` clean on the file; full
  `pytest -q` → 526 passed, 1 skipped, 1 warning, byte-identical to the stashed
  pre-change tree (the warning is pre-existing). Probe simulation: the old URL
  still raises `MissingGreenlet`, the sync URL builds a `PGDialect_psycopg2` sync
  engine, the rewritten URL builds the asyncpg `AsyncEngine`.

### T-002 — Replace the abandoned testcontainers dependency

- **Status**: done (commit `0dc0e89`)
- **Files to modify**:
  - `backend/pyproject.toml`
- **What**: drop `"testcontainers-postgres>=0.0.1rc1"` in favour of
  `"testcontainers>=4.9.0"` with a one-line comment naming the floor's reason.
- **Evidence**: clean-venv resolution shows the legacy pair is gone; in the
  project venv `pip install -e ".[dev]"` leaves `testcontainers 4.15.0` and
  `from testcontainers.postgres import PostgresContainer` resolves to
  `testcontainers/community/postgres/__init__.py`; `PostgresContainer._connect`
  contains `psql`. Suite unchanged (526 passed, 1 skipped).
- **Operational note (found while verifying)**: installing the new package over
  an env that still has the legacy pair does **not** remove it, and the legacy
  `testcontainers/postgres/__init__.py` **directory shadows** the new
  `testcontainers/postgres.py` module, so the old probe keeps winning. Existing
  venvs need `pip uninstall testcontainers-postgres testcontainers-core` first;
  CI builds a fresh venv and is unaffected.

### T-004 — Create the PG enum types before `create_all`

- **Status**: done (commit `757ab72`)
- **Files to modify**:
  - `backend/tests/test_integration/test_projects_integration.py`
- **What**: `_create_pg_enum_types(connection)` walks `Base.metadata.tables`,
  creates every named `ENUM` column type with `checkfirst=True` and runs before
  `Base.metadata.create_all` inside the same transaction.
- **Why**: the models declare `PGEnum(..., create_type=False)` because Alembic
  0016/0017 own the `CREATE TYPE` statements, so `create_all` never emits them.
  SQLite does not care; real Postgres fails with `type "..." does not exist`.
- **Evidence**: mock-engine dump against the Postgres dialect — `create_all`
  alone → 12 CREATE TABLE / **0 CREATE TYPE**; helper → **3 CREATE TYPE** with
  the migration's exact labels (`extraction_status_new`, `user_story_status_new`,
  `task_status_new`).

### T-005 — Freeze the clock on both sides of the cache TTL test

- **Status**: done (commit `65a8a3f`)
- **Files to modify**:
  - `backend/tests/test_unit/test_user_cache.py`
- **What**: `test_cache_survives_within_ttl_window` patches `monotonic` for the
  write as well as the read.
- **Why**: the write stamped the *real* clock and the read was patched to `290`,
  so the assertion held only while the host's uptime exceeded 260s. GitHub
  runners boot fresh; laptops do not.
- **Evidence**: the old shape returns `None` against a simulated 200s uptime (the
  CI failure reproduced deterministically); the new shape returns the cached user.
  Sibling tests read at `10**9 + 31` and were immune — that asymmetry is why only
  this one failed.

### T-007 — Seed the workspace owner so Postgres accepts the insert

- **Status**: done (commit `a318ccf`)
- **Files to modify**:
  - `backend/tests/test_integration/test_projects_integration.py`
  - `docs/testing.md`
- **What**: the test saves a real `User` first and uses `owner.id` for both
  `workspaces.owner_id` and `workspace_members.user_id`.
- **Why**: those two columns are real foreign keys into `users`, and SQLite does
  not enforce foreign keys by default. Postgres rejected the insert with
  `fk_workspaces_owner_id_users`.
- **Evidence**: replaying the same insert against `sqlite+aiosqlite://` with
  `PRAGMA foreign_keys=ON` makes the old shape fail with `RepositoryError` caused
  by `FOREIGN KEY constraint failed` (the CI failure, reproduced locally) while
  the real test body passes unchanged.

## Risks

- The `<500ms` assertion can fail on a slow shared runner. Pre-existing and out
  of scope (Non-goals); if it flakes, D1 is the decision to revisit.
- Neither work unit can be executed end to end without Docker. The container
  path's real proof is the next CI run; that limit is recorded, not smoothed
  over.

## Evidence log

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `2e729ae` | Container keeps its sync driver; app engine gets asyncpg via `make_url().set()`. Both fixtures and the marker declare `loop_scope="module"`. `docs/testing.md` documents the module's CI-vs-laptop behaviour and both conventions. `ruff` clean; `pytest -q` → **526 passed, 1 skipped, 1 warning**, identical to the stashed pre-change tree. Probe simulation reproduces the CI error on the old URL and shows a sync `PGDialect_psycopg2` engine on the new one. |
| T-002 | `0dc0e89` | `testcontainers>=4.9.0` replaces `testcontainers-postgres>=0.0.1rc1`. Clean venv: only `testcontainers 4.15.0`, import resolves to `community.postgres`, `_connect` is `psql`-based. In a psycopg2-free venv the URL rewrite still builds the asyncpg engine, so no sync DBAPI is required. |
| T-003 | `70be4bc` | Evidence log, verification limits and follow-ups recorded. Post-change LSP check on the touched file: **0 diagnostics** after restarting the language server (it had cached import search paths from before the dependency was installed). |
| T-006 | merge + push | Merged into `main` by fast-forward and pushed (`6515308..70be4bc`); deploy workflow succeeded. First real CI run of the integration test: the `MissingGreenlet` error is **gone** — the fixture starts the container, passes the probe, connects with asyncpg and reaches the DDL. That confirms the T-001 diagnosis. CI then reported two new causes, which became T-004 and T-005. |
| T-004 | `757ab72` | `create_all` now runs after the three enum types exist. Offline Postgres-dialect DDL dump is the evidence: 0 CREATE TYPE before, 3 after. |
| T-005 | `65a8a3f` | The cache TTL test no longer depends on host uptime; the old shape's failure is reproduced against a simulated 200s uptime. `ruff` clean; `pytest -q` → 526 passed, 1 skipped, 1 warning on both work units. |
| T-007 | `a318ccf` | Second CI run (`35362039719`): the enum and cache fixes held — **526 passed**, the container test ran and reached its body — and it stopped on `fk_workspaces_owner_id_users`. Fixed by seeding the owner row. Local proof via SQLite with `PRAGMA foreign_keys=ON`: old shape fails, real test body passes. |
| T-008 | CI `35362462180` | **Green.** Backend and frontend both success; the backend reports **527 passed, 1 warning, 0 skipped** — 527 and not 526 because the integration test executed for real instead of erroring at setup, and no skip because the runner has a Docker daemon. The `<500ms` assertion held. |

Two verification limits, stated rather than smoothed over:

1. **The container path was never executed.** There is no Docker daemon on this
   machine (`~/.docker/run/docker.sock` and `/var/run/docker.sock` both absent),
   so the module skips exactly as it does on any laptop. Everything above is
   static or unit-level proof of the failure mode; the real proof is the next CI
   run pulling `postgres:16-alpine`. The pre-change tree could not be run against
   a container either — the bug was only ever observable in CI.
2. **The `_docker_reachable()` silent skip is untouched (see Non-goals).** It is
   why a broken fixture could sit green locally, and it will keep hiding this
   class of failure on any machine that loses Docker.

## Outcome

Round 1 (merged and pushed): the readiness probe no longer sees an async driver,
and the module-scoped fixtures share the loop that owns the engine. CI confirmed
both — the integration test executed for the first time instead of erroring at
setup, then failed at the DDL, which is a genuine finding the test exists to make.

Round 2 (merged and pushed): `create_all` now runs after the enum types exist,
and the cache test no longer depends on the host clock. CI confirmed both (526
passed) and then reported the last layer this file was hiding: the seeded owner
was not a real user row, and Postgres enforces the foreign key that SQLite
ignores.

Round 3 (merged and pushed): the owner is a real row. CI is green —
`35362462180`, backend and frontend success, **527 passed, 0 skipped**, with the
integration test executing against a real Postgres container and its `<500ms`
assertion holding.

One integration test surfaced three Postgres-only traps that SQLite had hidden
the whole time: an async driver handed to a sync readiness probe, enum types only
Alembic creates, and a foreign key SQLite never enforced. That is the argument
for keeping this test in CI instead of skipping it — and, in the other direction,
for distrusting a green local suite as evidence about Postgres.

The residual cost is honest and small: the backend job now pulls
`postgres:16-alpine` and takes ~33s instead of ~18s.

## Follow-ups (not part of this fix)

- Consider making the skip CI-aware (`skip outside CI, fail inside it`) so a
  missing Docker daemon on a runner surfaces as a failure instead of as green.
- `psycopg2-binary` may remain as an orphan in venvs that previously installed
  the legacy shim. Harmless, `pip uninstall psycopg2-binary` if you want it gone.
- The LSP reported `reportMissingImports` for `testcontainers.postgres` until the
  language server was restarted: `pyright-langserver` freezes its import search
  paths at startup, and it had started before the package existed in the
  interpreter it resolved against. After the restart the same file reports **0
  diagnostics**, so the message was stale tooling state, not a repo defect. Same
  class of trap as the silent Docker skip: green or red, verify the instrument.
