# ODD Feature: deploy-migration-window

> **Status**: in progress. Branch `feat/deploy-migration-window` off `main` @ `4410dea`.
> **Created**: 2026-09-21
> **Workflow**: Organic Driven Development (ODD)

## Problem

The deploy has never run an Alembic migration. On 2026-09-20 that cost a day of production: the
container restarted with new code while the schema stayed at `0021`, and extraction failed 56 times
with `column extractions.completed_at does not exist`. A readiness gate now catches the mismatch and
fails the deploy — but it fails *after* `docker run`, so it detects rather than prevents, and the
migration still had to be applied by hand twice (`0022`/`0023`/`0024` on 2026-09-20, `0025`/`0026` on
2026-09-21).

`prod.todo.md` carried that row open. It also carried the reason it stayed open: **there is no fixed
position in the workflow that is correct for every revision.**

## Why no position works — the measured argument

The three most recent order-dependent revisions disagree, and the disagreement is structural rather
than stylistic:

| Revision | Its own instruction | The hazard it names |
|---|---|---|
| `0022` (`:13`) | *"Run it after the release that refuses the key is deployed."* | The **previous** release re-stores the block the new schema rejects, and the revision will not run a second time to clean it up. |
| `0023` (`:19`) | *"Run this before deploying the release that reads the column."* | The **new** release selects `completed_at` on every load. This is the 2026-09-20 incident. |
| `0024` (`:8`) | *"Run this after the release that encrypts and decrypts is deployed."* | The **previous** release hands the ciphertext to a provider as if it were an API key. |

`0022` and `0023` are **adjacent** (`0023.down_revision == "0022"`), so a single `alembic upgrade head`
crossing that pair cannot satisfy both orders relative to one container swap. `0024` says so itself:
*"Revision 0022 asks for the same order; revision 0023 asks for the opposite."* `0025` and `0026` are
explicitly order-agnostic; `0021` carries no ordering sentence at all.

**The observation that resolves it:** every hazard above requires **a live release on the wrong side**
of the change. One is an old release meeting the new schema; the other is a new release meeting the old
one. A window in which **no release is live** removes both classes at once, which is why the position
is an argument rather than a preference — and why the step cannot be moved above the `docker stop`.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The mechanism | **Operator-selected: the maintenance window.** `docker stop` → `alembic upgrade head` → `docker run`. It satisfies every revision in the chain, needs no per-revision machinery, and was chosen over "migrate before the swap with an expand/contract convention" and over "declared phase per revision". |
| D2 | What it costs | **Downtime during the migration, and fail-closed on failure.** A failed migration leaves the API down instead of serving against a schema the code does not match. Accepted deliberately: the alternative is the incident this exists to prevent. |
| D3 | Recoverability | **Forward by default, with an optional way back.** The deploy tags the previous image as `storico-api:previous` before overwriting the tag, because today there is no way back at all: the build replaces the only tag the previous release had. Rolling the code back is only safe while the schema is still compatible with it; with a half-applied migration the path is forward, and the record says so rather than implying a clean undo. |
| D4 | Concurrency | **Serialised deploys.** Two at once would race on the swap *and* on the migration, so the workflow gets a `concurrency` group with `cancel-in-progress: false` — cancelling a deploy mid-migration is worse than waiting for it. |
| D5 | Where the migration runs | **From the image just built**, with the same `--env-file` the app uses. The revision being applied is the one in the commit, and sharing the env file means the migration cannot reach a different database than the container. |

## What was measured before writing

**The image cannot run the CLI today, and the reason is the config, not the CLI.** The image already
carries the migration scripts (`Dockerfile:20 COPY src/`) and the `alembic` console script (`alembic` is
a main dependency, `pyproject.toml:32`), but never `alembic.ini` — so `alembic` fails before `env.py` is
imported. And even with the file present, `script_location` was a bare relative path: Alembic only
rewrites it against the ini's own directory when `%(here)s` is used, so it resolved against the process
working directory. Measured as a before/after pair on this machine:

| Command | Result |
|---|---|
| `alembic heads` from `backend/` (cwd happens to be right) | `0026 (head)` |
| `alembic -c /abs/path/backend/alembic.ini heads` from `/tmp` | `FAILED: Path doesn't exist: src/storico/infrastructure/database/alembic.` |

**Which change is load-bearing for what.** The `COPY` is what lets the container run the CLI at all — without a
config file present, Alembic fails before `env.py` is imported. The `%(here)s` token is not what unblocks the
container: inside the image the working directory is `/app` and the bare relative path happened to resolve
from there. It is what makes the command independent of the caller, which is the other path this batch has
to make usable — an operator running the same command by hand from whatever directory they are in — and it
removes a coupling that would have bitten the first time anyone invoked the CLI from somewhere else.
Stated separately because the measurement above only proves the second half, and collapsing the two would be
the kind of claim this repository keeps having to correct.

**No Docker daemon on this machine**, so nothing here proves what happens inside a container: the image
build and the migration container are verified in CI and on the VM, and this record says so instead of
implying a local end-to-end run.

**What was checked and is not a dependency of this design:** `env.py` honours an explicitly supplied URL
through `config.attributes`, but the CLI cannot populate it (the `-x` flag reaches
`get_x_argument()`, not `attributes`; only a programmatic caller writes it). A shell `alembic upgrade
head` therefore always takes the `Settings.load()` branch, which normalises `sslmode` to `ssl`. So the
`R3-supplied-url-verbatim` advisory **does not apply** here: this design never supplies a URL.

**`STORICO_ENCRYPTION_KEY` is mandatory** for any upgrade crossing `0024` (`0024:69-84` refuses loudly
without it), and every database behind head crosses it. The container's env file already carries it, and
the migration container uses the same file.

## What lands

- `backend/Dockerfile` — `COPY alembic.ini ./alembic.ini`.
- `backend/alembic.ini` — `%(here)s` on `script_location` and `prepend_sys_path`, with the reason in a
  comment so it is not "simplified" back.
- `.github/workflows/deploy-backend.yml` — the `previous` rollback tag, the migration step inside the
  window, the serialising `concurrency` group, and the rewritten failure message (the old one says this
  step "only detects and does not migrate", which stops being true here).
- `docs/deployment.md` — the Migraciones section, rewritten: the window and why, the exact commands, the
  downtime and fail-closed consequences, and the recovery path.
- `docs/database.md` — the header figures and the revision table, which stopped at `0024`.
- `prod.todo.md` — the row closes.
- `AGENTS.md` — ADR-005's Consecuencias sentence, which says the deploy runs no migrations.
- `odd/tasks/schema-drift-gate.md` — dated corrections for two rows this change and `de884f5` invalidate.

## Gates

Backend and frontend tests are not this candidate's surface: no Python and no frontend file changes. The
surface is a Dockerfile, an ini, one workflow and documents, so the evidence is the ini measurement
above, a YAML parse, and a shell syntax check of the workflow's remote script.
