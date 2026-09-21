# ODD Feature: schema-drift-gate

> **Status**: **PR 1 (WU1 + WU2) committed, independently verified, and native-reviewed — approved and
> burned. Awaiting the operator's landing decision.** Branch `feat/schema-drift-gate` off `main` @
> `305b5da`. PR 2 is the pair that makes the migration chain prove itself — WU3 and WU4.
> **Created**: 2026-09-21
> **Workflow**: Organic Driven Development (ODD)

## Problem

On 2026-09-20 production broke for a day. The schema sat at Alembic revision `0021` while the deployed
code was at head `0024`, so `extractions.completed_at` did not exist and 56 extractions failed with
`column ... does not exist`. The proximate cause is that `.github/workflows/deploy-backend.yml` runs no
migration at all. The real cause is one layer up: **nothing in this system can detect that the code and
the schema disagree**, so the mismatch had to express itself as failed extractions before anyone knew.

### Why the mismatch is invisible today

| # | Mechanism | Where |
|---|-----------|-------|
| 1 | The probe is `SELECT 1` and nothing else. It passes against any schema. | `api/routes/health.py:32-40` |
| 2 | `version` in the health body is a **literal** `"0.1.0"` — not the package version (`pyproject.toml` says `0.3.0`), and certainly not the schema revision. | `api/routes/health.py:104-110` |
| 3 | Nothing reads `alembic_version`. Grep over `backend/src/` finds it only in prose inside `0015`'s docstring. | — |
| 4 | Startup cannot catch it: `get_engine()` is lazy and probes nothing, and `recover_stuck_extractions()` — whose queries select `completed_at` — is wrapped in a broad `except Exception: logger.exception(...)`, with a second swallow inside the function itself. A missing column therefore **silently disables startup recovery** while the container reports healthy. | `api/app.py:62-74`, `infrastructure/tasks/extraction_task.py:177-181`, `models/extraction.py:56` |
| 5 | No test can notice a missing migration: the fixture builds the schema from the **models** with `create_all`, not from the migration chain. | `tests/conftest.py:97` |
| 6 | The deploy's own verification **cannot fail the job**: `curl … && echo " — OK" \|\| echo " — FAILED"` guarded by `set -e`, so a deploy that leaves production down exits 0. | `.github/workflows/deploy-backend.yml:44-46` |

### The ordering problem is two-directional, and no fixed position solves it

This is the finding that shapes every decision here. The three most recent revisions record their
required deploy order in their own docstrings, and they **contradict each other on purpose**:

| Revision | Required order | Why |
|----------|----------------|-----|
| `0022` | code first, then migration | The previous release still accepts and persists the `llm` block; the revision does not run twice, so the residue is invisible (`0022_drop_user_preference_llm.py:17-21`) |
| `0023` | migration first, then code | The new ORM selects `completed_at` on every load; this is the 2026-09-20 incident (`0023_add_completed_at_to_extractions.py:17-22`) |
| `0024` | code first, then migration | Run early, the old release reads the ciphertext and **sends it to a provider as an API key** (`0024_encrypt_workspace_api_keys.py:17-24`) |

`0024`'s docstring names the contradiction itself: *"Revision 0022 asks for the same order; revision
0023 asks for the opposite. Each is right for its own change."*

**Two documents in this repository therefore contradict each other today:**

- `prod.todo.md:18` says the migration step *"va después del `git reset` y antes de arrancar el
  contenedor nuevo"* — a fixed position that satisfies `0023` and **violates `0022` and `0024`**.
- `odd/tasks/prod-checklist-honesty.md` (Non-goals) warns that exactly this is wrong: a blanket
  "migrate before the swap" is right for a `0023`-shaped revision and *"wrong for a `0024`-shaped one"*.

A second, subtler refutation worth recording: a blanket pre-swap `alembic upgrade head` would be
**harmless today** (every contract/data revision in the chain is already applied) and a blanket
post-swap one would be equally harmless today. Both fail on the *next* revision someone writes. The
policy cannot be a position; it has to be a property of each revision.

### Constraints that bound what a fix can be

| Constraint | Where |
|---|---|
| `alembic.ini` is **not** in the image; only `src/` is copied. The `versions/` directory **is** in the image, and the `alembic` CLI is installed (`alembic` is a main dependency). | `backend/Dockerfile:6-24`, `backend/pyproject.toml:32` |
| `env.py` **unconditionally overwrites** `sqlalchemy.url` from `Settings.load()`, so an externally supplied URL cannot be honored. | `alembic/env.py:24` |
| `--sql` offline mode **cannot run the chain**: five revisions call `op.get_bind()` (`0016`, `0018`, `0021`, `0022`, `0024`). | those files |
| `0022` and `0024` call `session.commit()` **mid-revision**, ending Alembic's transaction; only their idempotence guards make a crash between the two survivable. | `0022:104`, `0024:120,158` |
| No `CREATE INDEX CONCURRENTLY` / `AUTOCOMMIT` anywhere, so every index build is inside the migration transaction. | `0001`, `0016`, `0021` |
| `env.py` does **not** apply `_add_statement_cache_size` (the pgbouncer fix) while the application engine does. | `alembic/env.py:24` vs `infrastructure/database/base.py:80-81` |
| The migration chain and the models are **not proven equal**: `conftest` uses `create_all`, and the integration test hand-creates enum types with a shim *"solely to paper over the models/migrations gap"*. | `tests/conftest.py:97`, `tests/test_integration/test_projects_integration.py:91-113` |

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | What to adopt now | **Phase 0: detection only.** Operator-selected on 2026-09-21 over "expand/contract convention" and "per-revision declared order". Automating migration execution is deferred; none of the other options is trustworthy until a mismatch is loud. |
| D2 | Split the work | **Two PRs.** The pair that makes production loud (health + deploy gate) and the pair that makes the chain prove itself (CI chain/drift + the stale claims) have different blast radii: the first touches the deploy path, the second does not. |
| D3 | What the unauthenticated endpoint may reveal | **A status, never a revision value.** The health routes are deliberately opaque about errors because they are unauthenticated (`health.py:51-58`). A public endpoint therefore reports `ok` / `drift` / `unknown` and nothing more; the actual revision strings go to the **log**, so diagnosis is `docker logs`, not HTTP. |
| D4 | Liveness vs readiness | **Keep `/health` as liveness and add `/api/v1/health/ready`.** The machine gate needs an HTTP status code so the deploy can use `curl -sf` with `set -e`, without parsing JSON inside a shell script on the VM. `/health` keeps its current semantics and gains an informational `schema.status`. |
| D5 | `unknown` must not read as healthy | A schema query that fails, or an absent `alembic_version`, is **`unknown` and not `ok`**, and readiness answers 503 for it. Fail closed: a fresh database nobody migrated must not look ready. |
| D6 | Supersede the contradiction explicitly | `prod.todo.md:17-18` is edited in WU2. The Non-goals entry in `prod-checklist-honesty.md` was **not** edited, and this row first claimed it was — refuted by this lot's own `git diff`, which never contains that file. Reading it again, it already states the two-directional problem correctly, so the contradiction was one-sided and only `prod.todo.md` needed to move. |
| D7 | The stale claims found while exploring | **Included.** `docs/database.md` says "11 migraciones aplicadas" where there are 24, with its table stopping at `0011`; `todo.md:220` says "50 archivos de alembic" and that no test covers migrations (four per-revision tests do). Same class as the batch that just closed. |
| D8 | The `version` field | **Fix it in WU1.** `/health` returns a hardcoded `"0.1.0"` while `backend/pyproject.toml:6` declares `0.3.0` — a false claim on the very endpoint this lot is making honest, and one line to correct. |

### What readiness means, and what a red deploy means with it

`/api/v1/health/ready` answers **200 only when the database is reachable and `alembic_version` equals
the code's expected head**, and 503 otherwise. That is a deliberately strict definition, and its
consequence has to be stated rather than discovered:

- For a **`0023`-shaped** revision (migration first), this is exactly the gate that would have caught
the 2026-09-20 incident: the new code is live, the column is missing, readiness is 503, the deploy go
red instead of reporting success over a broken release.
- For a **`0022`/`0024`-shaped** revision (code first), the operator deploys the code and the
  **readiness gate goes red on purpose** until the pending migration is applied by hand. That red is the
  handoff, not a false alarm: the system genuinely is in an intermediate state. The runbook for a
  schema-changing deploy therefore becomes *deploy → read the readiness failure → run the pending
  revision → re-check*, and the workflow's failure message must say so.
- A **direction-aware** gate — one that could tell "the schema is behind the code" (dangerous) from
  "the code is behind the schema" (the code-first case) — needs a declared order per revision, which is
  the option deliberately deferred. It is the first thing to revisit in Phase 1, and this strict form is
  what makes the case for it.

## Design of the detection

- **Expected head** is computed from the migration scripts in code, once and cached: a `Config` whose
  `script_location` points at the package's own `alembic/` directory, read through
  `ScriptDirectory.get_current_head()`. No `alembic.ini` is required, which matters because the image
  does not contain one. Reading and parsing the scripts per health request would be disk I/O on a hot
  path, so it is computed once.
- **Actual revision** is one small read-only query against `alembic_version`, treated as absent if the
  table or the row is missing.
- Three outcomes only: `ok` (equal), `drift` (different), `unknown` (could not tell).
- The deploy's verify step stops swallowing its own failure, asserts readiness, and also checks that the
  container is actually running — because `docker run` succeeding is not the same as the app being up.
- Whether `deploy-backend.yml`'s `set -e` actually fails the GitHub job depends on the action's own
  error propagation. **Measured in WU2**: the action's `script_stop` input does not exist at `v1` (gone
  from `v1.2.1`; `v1.2.0` still declares it), its README says to use `set -e` instead, and drone-ssh
  exits non-zero when the remote script does. The suppression was the `|| echo`, not a missing option.

## Work units

### PR 1 — the pair that makes production loud (WU1, WU2)

| WU | Files | Change |
|----|-------|--------|
| WU1 | `infrastructure/database/schema_status.py` (new), `api/routes/health.py`, tests | The `ok`/`drift`/`unknown` probe, cached expected head, `schema.status` in `/health`, the new `/api/v1/health/ready`, revision values logged and never returned, and the `version` field stops being the hardcoded literal. The probe lives in the infrastructure layer because it needs Alembic and SQLAlchemy, and `health.py` imports it directly — which is the pattern that file already uses for `get_engine`. **Not a port**: an earlier draft of this row said the probe should be a port "so the health route does not depend on the database layer directly", which the file itself refutes. |
| WU2 | `.github/workflows/deploy-backend.yml` | The verify step fails the job: assert readiness with `curl -sf`, assert the container is running, and make the action propagate the failure. Plus the `prod.todo.md:17-18` correction that replaces the fixed-position policy. |

### PR 2 — the chain proves itself (WU3, WU4)

| WU | Files | Change |
|----|-------|--------|
| WU3 | `alembic/env.py`, a new integration test, `conftest` if needed | Let `env.py` honor an externally supplied URL, then add the test that runs the whole chain against a real Postgres and compares the result to the models. **Measure the drift first**: if autogenerate reports differences on day one, the gate cannot land red — either the drift is fixed or the gate is scoped to "the chain runs and reaches head". |
| WU4 | `docs/database.md`, `todo.md`, `docs/testing.md`, and the stale references inside `odd/tasks/prod-checklist-honesty.md` | The stale claims in D7, **plus the ones the verifier found that D7 did not list**: `todo.md:211` ("418"), `docs/testing.md:98` ("526 tests"), and two `testcontainers>=4.9.0` references inside `prod-checklist-honesty.md` that the same file's own WU6 superseded — along with a duplicated "PR 2 — not started" / "committed and awaiting native review" pair that this session's edits to that record left behind. Scope widened by measurement, not by preference. |

## Non-goals

- **Automating migration execution in the deploy.** That is the next decision, and it is not Phase 0's.
- **The expand/contract convention and per-revision declared ordering.** Both were offered and
  deliberately not chosen yet; they are the natural Phase 1 candidates once drift is loud.
- **Versioned image tags, and rollback.** The workflow tags every build `storico-api` and has no
  rollback step; that is a separate deficiency with its own decision.
- **`backend/entrypoint.sh` is dead code** (never copied, no `ENTRYPOINT`), so it is not the place to put
  a pre-flight check. Recorded, not fixed.
- **The `env.py` statement-cache asymmetry** versus the application engine. Recorded as an unverified
  risk; whether production even connects through Neon's pooler is not known from the repository.
- **Incidental drift found while classifying**: `0016` creates `idx_tasks_user_story_id` while `0001`
  already created `ix_tasks_user_story_id` for the same column; `0018` creates an enum type that no
  revision ever uses as a column type; `test_projects_integration.py`'s docstring attributes
  `extraction_status_new` to `0017` when `0018` creates it.
- **Idempotence/re-entrancy of `0022` and `0024`.** Real, survivable today, and not this lot's.

## Tasks

- [x] WU1 — schema status probe + `/health` field + `/api/v1/health/ready`, with tests that fail without
      it. The probe is **not** a port: this line first said to introduce one "so the health route does not
      depend on the database layer directly", which `health.py`'s own `get_engine` import refutes. Landed
      as `aee59ff`.
- [x] WU2 — `deploy-backend.yml` fails when production is not ready; the action's error propagation was
      measured rather than assumed; `prod.todo.md` corrected. Landed as `68b9781`.
- [x] Gates for PR 1: backend `ruff check src tests`, `ruff format --check src tests`, `pytest -q`
      (728 passed, 1 skipped, 1 pre-existing warning); frontend untouched. Re-run independently.
- [ ] Native review of PR 1, then land it.
- [ ] WU3 — `env.py` honors an explicit URL; integration test runs the chain against Postgres and
      compares the result to the models; measure the drift before choosing the gate's shape.
- [ ] WU4 — the stale-claims sweep, scope widened by measurement (see the work-unit row above).
- [ ] Gates for PR 2, commit, native review, land PR 2.

## Evidence

### WU1 — the probe and readiness (commit `aee59ff`, 5 files)

`schema_status.py` reads the code's head from the packaged migration scripts through a `Config` whose
`script_location` resolves from the module's own path (never the working directory, never `alembic.ini`,
which the production image does not contain) and caches it, because ``None`` is a real cached value and
the cache needs its own empty flag. The database's revision is one declared `Table` select against
`alembic_version`; a failed statement is rolled back before re-raising, so an aborted Postgres
transaction is not handed back to the pool. `ok` / `drift` / `unknown`, and `unknown` never collapses
into `ok`. `health.py` gains `_check_schema()` shaped like `_check_database()`, a `schema` block in
`/health` (liveness semantics unchanged) and in `/health/services`, and the new
`/api/v1/health/ready` which answers 503 unless the database is reachable **and** the schema is `ok`.
No route publishes a revision; both go to the log. `version` stopped being the hardcoded `0.1.0`.

**The TDD red the writing agent returned was a collection `ImportError` — a valid red for "the module
does not exist", and worthless as evidence that the assertions can fail.** The parent re-derived it by
mutation, which is the only method that answers that question:

| Mutation | Result |
|---|---|
| A — readiness ignores the schema (`ready = db ok`) | `test_readiness_follows_the_schema` and `test_readiness_answers_the_same_body_whatever_the_status_code` fail |
| B — `unknown` collapses into `ok` | **8** tests: 5 unit, `test_a_schema_that_cannot_be_read_is_unknown_and_never_ok` (both parameters), and **`test_readiness_follows_the_schema`** — which this table first omitted. The verifier measured the undercount. |
| C — a revision leaks **only** on `/health/ready` | **all 15 tests passed.** The guarantee was tested on `/health` alone while three unauthenticated routes publish bodies |

Mutation C is the finding: it was found by breaking the code, not by reading it. A parametrized
`test_no_route_publishes_a_revision` now scans all three routes with `_strings_in`, which walks the
whole document rather than one top-level key, and it was verified to fail on the same mutation and pass
without it. The route's own docstring already promised that property, so the gap was a claim with no
check behind it.

**Live measurement, unmocked, against the local `.env` database** — the strongest evidence in this
work unit, because it is the incident's exact condition detected in advance rather than reconstructed:

| request | HTTP | database | schema |
|---|---|---|---|
| `GET /api/v1/health` | **200** | `ok` | `drift` |
| `GET /api/v1/health/ready` | **503** | `ok` | `drift` |

and the route logged `Schema status is drift: the code expects revision 0024, the database holds 0021`.
That local database sits at `0021` against a head of `0024`, which is precisely the state production
was in on 2026-09-20. Liveness and readiness split as designed: only the schema accounts for the 503.
No migration was run.

Gates: `ruff check` clean, `ruff format --check` clean (`227 files`), `pytest -q` **728 passed, 1
skipped, 1 warning** — the warning is the pre-existing `RuntimeWarning` already recorded in
`todo.md:213-215` and in the previous batch's record.

**Two process notes, because both cost a round trip.** First, this brief contradicted itself: it told
the writing agent to update anything asserting the old `version` literal while listing four allowed
paths, and two such assertions live in `backend/tests/test_health.py`. The agent refused to widen its
own surface and stopped for a decision, which is the right behaviour; the parent authorized exactly
those two assertions and nothing else. Second, `backend/src/storico/api/app.py:86` still passes
`version="0.1.0"` as the FastAPI/OpenAPI metadata — the same stale-literal class. It is **not** fixed
here: D8 scoped the version to the health field, and the OpenAPI surface is a different promise to a
different reader. Recorded as a follow-up rather than silently fixed or silently left.

### WU2 — the deploy gate (commit `68b9781`, 2 files)

The deploy's sequence — worktree reset, image rebuild, stop, remove, run — is untouched. Only the
verification block was replaced: it now requires the `storico-api` container to actually be **running**
(`docker inspect -f '{{.State.Running}}'`) **and** `GET /api/v1/health/ready` to answer 2xx, polling a
bounded 120-second window instead of a single `sleep 3`, and reporting how long it took. On failure it
prints the container state, the HTTP status, the response body, the `Schema status is …` line and the
last 20 container log lines, names the runbook, and exits non-zero.

**The mechanism is not what this record's brief assumed.** The brief said to verify the action's
`script_stop` input and set it. That input does not exist at the pinned major: it was **present through
`v1.2.0` and removed in `v1.2.1`**. This paragraph first said "present up to `v1.1.0` and removed in
`v1.2.0`", which measurement refuted on both halves — `v1.2.0`'s `action.yml` still declares the input
twice, `v1.2.1`'s declares it zero times, and the same wrong version sits in the workflow's own comment.
Measured, not assumed — `raw.githubusercontent.com/appleboy/ssh-action/v1/action.yml`
is 6452 bytes and contains no occurrence of `stop`, and the v1 README says in as many words: *"To mimic
the removed `script_stop` option, add `set -e` at the top of your shell script."* The writing agent
verified instead of adding an inert `with:` key, which would have been ignored with an
"Unexpected input(s)" warning — the right call, and it stopped for the parent rather than guessing.

The propagation chain, also read from source rather than assumed: `easyssh.Stream` → `session.Wait()`
returns `*ssh.ExitError` for a non-zero remote exit → `plugin.exec` → `Plugin.Exec()` → `log.Fatal`.
With `ScriptStop=false`, drone-ssh joins the whole script into one `session.Start(...)`, so `set -e`
**is** the mechanism — and it was already there. What actually suppressed the failure was the `|| echo`,
which made the compound command's status the `echo`'s. So the fix was to remove the suppression and
assert something real, not to add an option.

The verifier measured the propagation against the real binary the action downloads (`drone-ssh 1.8.2`,
run over a local sshd rather than reasoned about): a remote `exit 3` makes drone-ssh exit **1**, not 3,
because it reports through `log.Fatal` — and the old `false && echo OK || echo FAILED` reproduces the
defect as exit 0. Non-zero propagation holds, but "returns the remote exit code as its own" was
inaccurate wording; the workflow comment now says "exits non-zero".

**Two suspects the verifier recorded rather than fixed, both about the completeness of a claim.**
First, `prod.todo.md`'s "ya no reporta éxito sobre una release rota" is only true for the schema/database
class of broken: readiness answers 200 with a missing `STORICO_ENCRYPTION_KEY` or any other unset
environment variable, which is the silent-failure class ADR-005 warns about. Second, the gate fires
**after** `docker run`, so a red deploy leaves the new container live with no rollback — the gate
reports, it does not prevent. Both are true of the design and neither is a defect in it.

**Stale claims the verifier found standing outside this candidate** (all recorded for WU4's widened
sweep rather than fixed here): `docs/testing.md:98` claims the suite is 526 tests where it is 728;
`todo.md:211` still says the expected total is 418; and `odd/tasks/prod-checklist-honesty.md` carries
two `testcontainers>=4.9.0` references its own WU6 superseded, plus a duplicated "PR 2 — not started" /
"committed and awaiting native review" pair left behind by this session's edits to that record. One
pre-existing code trap came up while chasing the live check and is noted only because it cost a run:
`_normalize_db_url` in `infrastructure/database/base.py` rewrites **any** URL scheme to
`postgresql+asyncpg`, so a `sqlite+…` URL silently becomes a postgres URL on `localhost:5432`.

**Verification, all of it observed.** The YAML parses; `bash -n` is clean on the extracted remote script
(95 lines) and on the block alone (74 lines); a grep for the `alembic` subcommands finds **no**
invoction; every line is ≤ 80 characters. The readiness branch was exercised with a throwaway harness
under `/tmp` — never inside the repository — that stubs `docker`, `curl` and `sleep`: exit **0** for a
running container whose readiness answers 2xx at the first poll and again when it answers only after
retries, and exit **1** for readiness 503 and for a stopped container. The parent re-ran all four cases
and reproduced those exit codes.

**What is not verified, and cannot be from here**: an end-to-end run. This workflow executes only on a
push to `main`, so the gate's behaviour on the VM is unproven until the next backend deploy. That is
stated rather than implied, and it is the reason the gate is exercised with stubs instead of trusted.

One correction landed with this work unit that is not about the gate: `prod.todo.md`'s
integration-suite row carried two facts the **previous** batch had made stale — `testcontainers>=4.9.0`
and the deprecation as outstanding debt — because that batch bumped the floor and swapped the import
without updating this file. Both are corrected. The "Orden de las migraciones" row stated one order as
if one order existed; it now records that this was the order of those three revisions and not a rule.

### PR 1 review

Native review `review-2eb84c2a08108260`, target
`sha256:1d798b8112525b507e9cd0c0f608df57357a0f76895cda62d842793ea109c12c`: `state: approved`,
`risk_tier: **high**` — not `medium` like the previous two candidates, because this one contains shell
source: `risk_reasons: [{"code": "shell_source", "signal": "shell_process", "path":
".github/workflows/deploy-backend.yml"}]`. All four lenses were required and all four ran (`review-risk`,
`review-resilience`, `review-readability`, `review-reliability`), 8 files,
`original_changed_lines: 1153`, `correction_budget: 200`. The group forecast was four model runs over
`pi_host_relay`; all four were prepared and submitted (prompt ≈ 86 kB each; results 5121 / 4481 / 3341 /
5148 bytes). Acknowledgement burned the authority: `authority: burned`,
`burn_evidence: gentle-ai.review-acknowledged/v1`, `delivery: ordinary-repository-policy`.

**Thirteen advisory findings, none of which opened a correction.** Eleven are `SUGGESTION`; two are
`WARNING`, and both are the *same design point* seen from two lenses:

| Finding | Lens | Where |
|---|---|---|
| `R3-latched-unknown` | reliability | `schema_status.py:104-116` |
| `R4-cached-unknown-head` | resilience | `schema_status.py:92-104` |

They flag that the **failed** expected-head read is cached, so one failure latches `unknown` for the life
of the process and readiness stays 503 with no self-healing. That behaviour is not the writing agent's
invention — this record's brief asked for it in as many words ("a failed read is cached too, so an
unreadable script directory does not re-parse on every request"). The reviewers are right that **caching
success while not caching failure** is the better shape: the cheap path stays cheap, and a transient
failure heals instead of pinning the instance out of rotation. It is **not** applied here, because
editing the tree after approval would deliver something other than what was approved. It is the first
follow-up.

The other eleven, named so a follow-up can open them instead of re-deriving them:
`R1-info-readiness-leak`, `R2-duplicated-alembic-table-decl`, `R2-inconsistent-version-failure-mode`,
`R2-timeout-name-conflates-attempts-and-seconds`, `R3-drift-direction-blind`, `R3-gate-after-swap`,
`R3-gate-unproven-e2e`, `R3-liveness-latency`, `R3-version-assert-literal`,
`R4-gate-after-swap-no-rollback`, `R4-sequential-probe-latency`. The closure envelope carries ids,
lenses, locations and severities only, so this record does not paraphrase their content.

Worth noting that three of them **confirm what this record already states rather than contradict it**:
`R3-drift-direction-blind` is the direction-blindness recorded under "What readiness means", and
`R3-gate-after-swap` with `R4-gate-after-swap-no-rollback` is the "the gate reports, it does not prevent"
qualification. Reviewers landing on the same limits the record declares is corroboration.

**A harness quirk worth recording, because it has now cost time twice.** The first START minted a consent
envelope whose binding **expired after 10 minutes unanswered**, and the provider's prescribed
continuation was `restart-for-fresh-consent` — never a resend of the dead binding. Every rejection on
that path was pre-authority (`lineage_created: false`, `mutation_performed: false`), so nothing was
created and nothing was lost. The second START created the lineage, and an eligible interactive host
resolved the consent envelope before it reached the model — host-owned permission, not something this
record grants.

This section, like the ones above it, was written **after** the approval in a commit the approved
candidate did not contain. The reviewed artifact is the target identity named here, not the branch tip.

_(PR 2's per-work-unit records land below as WU3 and WU4 close.)_
