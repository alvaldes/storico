# ODD Feature: dev-reset-0028

> **Status**: in progress — authorised 2026-09-30 by the owner in one breath: *"la db de supabase está en la
> versión 0027, vamos a actualizarla, pero antes vamos a hacer limpieza de todo para empezar desde cero"*.
> **Created**: 2026-09-30
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone → ordinary repository policy decides delivery.
> **Target**: the **development** database only. Production (Neon) is already at `0028` and is not touched
> by this record.

## Why the wipe is not cosmetic

`0028_extraction_versioning.py:36-47` runs a guard before any DDL:

```python
extractions_count = bind.execute(sa.text("SELECT count(*) FROM extractions")).scalar_one()
tasks_count = bind.execute(sa.text("SELECT count(*) FROM tasks")).scalar_one()
if extractions_count or tasks_count:
    raise RuntimeError("0028 refuses to run: this migration does not backfill (D11). ...")
```

Dev measured `extractions = 38` and `tasks = 230`, so `alembic upgrade head` **fails as it stands**. The
data wipe is a hard prerequisite of the upgrade, not a housekeeping extra — and it is deliberately a
separate destructive operation with its own confirmation, never an Alembic step (the revision docstring
says so).

The upgrade itself is one revision: the chain `0027 → 0028` is linear and `0028` is the **sole head**
(parsed from all 28 revision files in this session: `n revisions: 28`, `heads: ['0028']`).

## Inventory — measured read-only before any mutation (2026-09-30)

This section is the witness. It exists so the destruction is provable against a number recorded before it,
which is the discipline D-a-3 left behind. Written to this file **before** the purge ran.

Connection: `postgresql+asyncpg` → `aws-0-us-east-1.pooler.supabase.com:5432`, project
`snpuizfjuaultjgkjhfs`, database `postgres`. Measured from `/Users/alvaldes/Developer/storico/.env` (the
dev env file, gitignored), through `asyncpg` — there is no `psql`, `pg_dump` or Docker on this machine.

| fact | value |
| --- | --- |
| `alembic_version` | **0027** |
| server version | Postgres **17.6** |
| `current_user` / `session_user` | `postgres` / `postgres` |
| RLS on every `public` table | `relrowsecurity = false` (13 tables) |
| schemas present | `public` + `auth`, `extensions`, `graphql`, `graphql_public`, `realtime`, `storage`, `vault` (all Supabase-managed, **out of scope**) |

Row counts, `public`, table by table:

| table | rows |
| --- | --- |
| `alembic_version` | 1 *(not purged — it is the migration pointer)* |
| `custom_providers` | 1 |
| `extractions` | **38** |
| `projects` | 17 |
| `tasks` | **230** |
| `user_accounts` | 3 |
| `user_preferences` | 0 |
| `user_stories` | **76** |
| `users` | 3 |
| `workspace_llm_configs` | 12 |
| `workspace_members` | 14 |
| `workspace_prompts` | 14 |
| `workspaces` | 14 |
| **total, 12 business tables** | **422** |

*(Corregido después de escribir esta fila: ponía 423, que es el total INCLUDING la una fila de
`alembic_version`. El script de purga reimprime 422 y esa es la cifra de las doce tablas de negocio.)*

### Shape of the interesting tables

- `users` — 3 rows: `Angel Valdés`, `Test`, `Dayana Reyes`. OAuth side in `user_accounts`: **1 `github` + 2
  `google`**. Only `users.email` (unique) and `user_accounts(provider, provider_id)` identify an account;
  deleting them is survivable because the first login re-bootstraps (see below).
- `custom_providers` — 1 row, name **`NaN`**. Legitimate: the table itself (`revision 0021`, feature not
  bug) stores a 3-character free-form provider name. Confirmed against `models/custom_provider.py`.
- `workspace_llm_configs` — 12 rows. **Exactly one carries an `api_key`**: `provider = 'NaN'`,
  `model = 'gemma4'`, `base_url = 'https://api.nan.builders/v1/'`. The other eleven are `ollama`
  (`llama3.1:8b`, `http://localhost:11434`, no key) and one empty `gemini` row.
- `workspace_prompts` — 14 rows, all defaults written by the first-login bootstrap, not authored by hand.

### The one irreversible item, and the owner's decision

`key_recoverability.py`'s method re-run against **dev**: decrypt `workspace_llm_configs.api_key` in memory
and compare against every candidate secret on this machine — `.env`, `.env.prod.local`, and process
environment variables matching `NAN|GOOGLE|GEMINI|API|KEY|TOKEN|SECRET`.

```
candidates compared: 46
rows with api_key: 1
NaN/gemma4: len=25  recoverable_from=NOWHERE on this machine
```

So `0028`-unblocking wipe destroys the **only copy** of one `nan.builders` API key, same failure mode as
the production purge but bounded to a single credential. Presented to the owner before execution; decision
recorded: **discard it without displaying it**. Consequence accepted on the record: it must be re-issued at
nan.builders and re-entered in Configuración before anything extracts.

Nothing else in the 422 rows is irreducible: `custom_providers.name`, `workspace_llm_configs` values,
`workspace_prompts` values and every identity in `users` are re-derivable from a login plus a few clicks.

### Already clean — nothing to destroy on the vector side

Qdrant cluster `525f1fa2-…us-east-2-0.aws.cloud.qdrant.io` (the same cluster dev and prod share, separated
by collection name only — documented debt):

| collection | points | status |
| --- | --- | --- |
| `storico_extractions` (legacy) | **0** | green |
| `storico_extractions_dev` (dev's, from `.env`) | **0** | green |
| `storico_extractions_prod` | **0** | green |

The D-a-3 vector wipe already emptied all three and nothing has written since. **No vector step in this
runbook.**

## Functional state after the reset (said before doing it, not after)

- **Extraction will not work on dev until an LLM config is created.** With `workspace_llm_configs` empty,
  `resolve_llm_config` (`api/routes/workspace_settings.py:121-129`) falls back to `provider = "ollama"` +
  `settings.ollama_host`, and Ollama is **not running on this machine** — measured:
  `curl http://localhost:11434/api/tags` → `000` (no response). So dev lands in exactly the state
  production landed in on 2026-09-30: schema current, zero data, zero credentials, nothing extractable.
- **Logging back in is enough to get an admin workspace.** `api/routes/auth.py:119-126` auto-creates user +
  personal workspace + `admin` membership + a `workspace_prompts` row on the first OAuth login. It does
  **not** create `workspace_llm_configs` or `custom_providers`.
- No deploy and no downtime: this is `alembic upgrade head` run locally against dev. The dev API was not
  even listening (`curl 127.0.0.1:8000/api/v1/health` → `000`).
- Dev and prod schema converge: both end at `0028`.

## Decisions taken by the owner before execution

| # | question | answer |
| --- | --- | --- |
| 1 | Wipe scope | **All 12 business tables** — a true start-from-zero, including the 3 user accounts, the 14 workspaces, the 12 LLM configs and the `NaN` custom provider. Not the minimal `extractions` + `tasks` that `0028` alone would need. |
| 2 | The `NaN/gemma4` key | **Discard it, without displaying it.** Re-issue at nan.builders later. |
| 3 | Backup | **None.** Same call as D-a-3: schema is reproducible from Alembic, data is dev data. |

## Safety rails actually used

1. **Do not reuse `~/storico-ops/d_a_3_purge.py`.** Its interlock pins `EXPECTED_ALEMBIC = "0027"` **and
   the eleven production counts** (17 extractions, 42 tasks). Pointed at dev it would abort on the counts —
   which is the design working, not a bug — but inheriting someone else's expectations is exactly what a
   purge must never do. A dev-scoped script re-measures and pins dev's numbers from this session.
2. **Interlock before destruction**: re-read `alembic_version` and all 12 counts in the same connection,
   compare against the inventory above, and refuse to emit a single `DELETE`/`TRUNCATE` if anything differs.
3. **One transaction, `RESTART IDENTITY CASCADE`**, then verify by counting again.
4. **`alembic_version` is never touched** by the purge. The upgrade moves it, nothing else does.
5. Supabase-side notes checked and dismissed: RLS is off on all `public` tables and the app connects as
   `postgres`, so `TRUNCATE` needs no policy work; the pooler port in use is **5432 (session mode)**, which
   is the DDL-safe one — transaction mode (6543) is not used here; `auth`, `storage`, `realtime`,
   `graphql*`, `extensions` and `vault` schemas are Supabase-managed and out of scope.

## Tasks

| # | task | status | evidence |
| --- | --- | --- | --- |
| 1 | Record the pre-purge inventory in this file, before destroying | **done** | the tables above, measured read-only in this session |
| 2 | Write the dev purge script with a freshly measured interlock | **done** | `~/storico-ops/dev_purge_0028.py` — three rails, dry-run by default |
| 3 | Run the purge; confirm 12 tables at 0 and `alembic_version` still `0027` | **done** | 422 rows destroyed in one transaction; re-counted from a separate process: 12 tables at 0, `alembic_version` still `0027` |
| 4 | `alembic upgrade head` against dev | **done** | `Running upgrade 0027 -> 0028`; `alembic current` → **`0028 (head)`** |
| 5 | Verify `0028` exists in dev as written (FK actions, CHECKs, uniques, `NOT NULL`) | **done** | 29/29 checks in `~/storico-ops/dev_verify_0028.py`, plus the delegated independent pass below |
| 6 | Record the outcome and commit as one work unit | **done** | `95507b9` (this file + `docs/deployment.md` + `odd/tasks/board-debt-closure.md`), second commit for the `AGENTS.md` pointer and the ADR-005 drift finding |

## Result — measured, not assumed

### The purge

`~/storico-ops/dev_purge_0028.py` ran its three rails clean, then executed under `--confirm-wipe`:

```
Identity rail: dev Supabase project 'snpuizfjuaultjgkjhfs' at aws-0-us-east-1.pooler.supabase.com:5432
Identity rail ok: current_user=postgres, server_version=17.6 (session-mode pooler, port 5432, DDL-safe)
Interlock clean: 12 tables, 422 rows, alembic_version=0027.
Containment rail ok: no table outside the twelve references them.
TRUNCATE executed inside one transaction.
CONFIRMED EMPTY: 12 tables at 0, alembic_version still 0027 (must be 0027). Ready for 0028.
```

Re-counted from a separate process: the 12 business tables at 0, `alembic_version` the only surviving row.

### The upgrade

`python -m alembic upgrade head` → `Running upgrade 0027 -> 0028`, one revision, no error. The D11 guard was
satisfied because of the purge, which is the whole point of doing it in that order: **had the wipe not
happened, this command would have raised `RuntimeError` on `extractions = 38` / `tasks = 230`.**
`alembic current` now returns `0028 (head)`.

### Shape verification — 29/29, delegated and independent

`~/storico-ops/dev_verify_0028.py` asserts every object the revision writes against
`pg_get_constraintdef()` output, not against the migration's prose. Highlights: `tasks.extraction_id`
NOT NULL with `ON DELETE CASCADE`; `fk_task_invalidations_revoked_by_users` as
`ON DELETE RESTRICT` and `marked_by` as `ON DELETE SET NULL`; `uq_extractions_story_version`;
the partial unique `uq_task_invalidations_active_task … WHERE (revoked_at IS NULL)`; both CHECKs.

A `gentle-ai-verify` child re-derived the expected object list from the revision file independently and
compared it to the live database: **18/18 objects present, nothing extra, `alembic check` → "No new upgrade
operations detected", and the three ORM models match their tables 1:1 with zero column or nullability
mismatch.** Its caveat, kept because it is true: `alembic check` does not compare CHECK constraints, so
those two are covered only by the direct `pg_get_constraintdef` reads.

**One FAIL came back and it was a bug in my verifier, not in the schema.** I had hand-written the expected
string of `ck_task_invalidations_reason_not_blank` as
`CHECK ((length(trim((reason)::text)) > 0))`; Postgres renders the same semantics as
`CHECK ((length(TRIM(BOTH FROM reason)) > 0))` — it canonicalises `trim(x)` to `TRIM(BOTH FROM x)` and
drops the no-op `varchar→text` cast. The expected string is now the measured one, with a comment saying so.
**Lesson for writing constraint assertions: copy them out of `pg_get_constraintdef`, never from the
migration source.**

**`auth.users` is 0 rows and that is not evidence of a breach.** Supabase's own schemas were never targets
here. The containment rail proved no table outside the twelve holds a foreign key into them, so
`TRUNCATE … CASCADE` could not reach `auth.users`; the app authenticates through Auth.js against
`public.users`, and this dev project never used Supabase Auth. What is genuinely missing is a pre-purge
baseline for `auth.*` — recorded above — so "never had rows" cannot be distinguished from "rows removed out
of band" by current data alone; the mechanism, not the count, is what proves it.

### The ORM can drive the new schema

`ExtractionModel` maps `version_number`, `provider`, `temperature`, `prompt_rendered`; `TaskModel` maps
`extraction_id`; `TaskInvalidationModel` maps all seven columns. Four `SELECT count(*)` through
`async_sessionmaker` against dev return `0` for `extractions`, `tasks`, `task_invalidations` and `users`
without a single error — the app layer reads `0028` as written.

## Two things this reset did NOT cause, and one it did

- **Not a cause: dev stopped extracting.** It could not extract before either. Eleven of the twelve
  `workspace_llm_configs` rows were `ollama / llama3.1:8b` pointed at `http://localhost:11434`, and **Ollama
  is not running on this machine** (`curl` → exit `000`). The twelfth was the `gemini` row with no key at
  all. The one row with a live credential was `NaN/gemma4`, and that is the credential the owner chose to
  discard.
- **A consequence, and it needs saying:** dev now has *no* LLM config rows, so `resolve_llm_config` falls
  back to `provider = "ollama"` (`api/routes/workspace_settings.py:121-129`) — a provider that is not
  reachable here either. Before any extraction works on dev: start Ollama **or** create a workspace LLM
  config with a real key. Then log in again; the first-login bootstrap recreates user, workspace, admin
  membership and `workspace_prompts`, but **not** `workspace_llm_configs` and **not** `custom_providers`, so
  the `NaN` provider has to be re-created by hand.

## Both environments now, stated together

| | dev (Supabase) | prod (Neon) |
| --- | --- | --- |
| `alembic_version` | **0028** | **0028** |
| business tables | 12 at **0** | 11 at **0** |
| LLM config rows | **0** | **0** |
| can extract? | no — no config, and no Ollama on this machine | no — no config, and no Ollama on the VM |

The schema is converged; neither environment has data or credentials. Both are waiting on the same human
step — create the workspace LLM config in Configuración.

## Deliberately not done

- **The ADR-005 documentation drift is reported, not repaired.** `AGENTS.md` §4 ("Contenedores"), ADR-005
  and feature row 40 all say development runs on **Docker Compose with a PostgreSQL container**. Measured
  here: `docker` is not installed, `docker-compose.yml` defines `postgres:16-alpine` with its own internal
  `STORICO_DATABASE_URL`, and this environment's `.env` connects to the **Supabase pooler** instead. So the
  dev path three documents describe is not the one this reset used. I cannot prove nobody runs it on another
  machine, which is exactly why this stays a finding for the owner rather than a correction I make on my own:
  changing what three documents assert about the architecture is an owner decision.
- **`user_preferences` is in the twelve.** The D-a-3 production list was eleven tables and omitted it (it had
  no rows there either). For a genuine start-from-zero it belongs in the set, so dev's scope is twelve.
  Nothing else differs between the two purges.
- **No application-level smoke test was run** (no login, no extraction attempt). It would fail for reasons
  unrelated to the migration — no LLM config, no Ollama — so it would prove nothing about `0028` while
  looking like it did. The ORM read-path check above is the honest substitute.
- **No `git push`, no pull request, no merge.** Branch `chore/dev-reset-0028` is local; delivery is the
  owner's call, and these are `docs`-only commits, so nothing triggers a deploy.

## Session handoff

Nothing here authorises touching production. If this file is resumed with `alembic_version` already `0028`
on dev, tasks 2–5 are done. `dev_purge_0028.py`'s `EXPECTED` block is a snapshot of the pre-purge world and
the script now aborts on it by design — **do not edit it to make it pass.** Any future wipe re-measures,
writes a new inventory section in this file, and gets re-authorised.
