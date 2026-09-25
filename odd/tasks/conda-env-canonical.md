# ODD Feature: conda-env-canonical

> **Status**: **complete** — verified 2026-09-24. Six work units landed, full suite green
> (`779 passed, 21 skipped, 2 pre-existing warnings`, 28.91s), `ruff check` clean and
> `ruff format --check` clean over 232 files. `backend/.venv` deleted. No commits: the tree
> already carried another session's uncommitted work and the owner did not ask for one.
> **Created**: 2026-09-24
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `main` (dirty from another session: `docs/deployment.md`, `docs/security.md`,
> `prod.todo.md` — untouched by this batch)
> **Receipt-driven development**: off in this clone
> **TDD**: not configured in this project. Runner: `conda run -n storico python -m pytest`.

## Problem

Two backend environments coexist in the working tree: an untracked `backend/.venv`
(297 MB, Python 3.12.14, created by the Makefile and by README/CONTRIBUTING) and the conda
environment `storico` (Python 3.12.13) that the owner actually uses. Every documented command
and both Makefile targets point at `.venv`, so:

- The owner's `pytest`, `ruff` and `uvicorn` are not the ones the docs name.
- CI (`pip install -e ".[dev]"`, bare `pytest -q`, `ruff check`) proves a third form that no
  document mentions.
- A `conda` user who follows the docs silently builds a second, parallel environment.

The owner asked to remove `backend/.venv` and to document the conda environment as canonical.

## Measured state BEFORE the repair (2026-09-24, `conda run -n storico`)

Repaired in this batch at the owner's explicit instruction; see "Resolution" below.

| Fact | Value |
| --- | --- |
| Python | 3.12.13 |
| Editable install | `__editable__.storico_backend-0.3.0.pth` → `backend/src` |
| Installed metadata version | 0.3.0 — stale; `backend/pyproject.toml` is 0.5.1 |
| `cryptography` | 49.0.0 — `pyproject.toml` requires `>=50.0.1` |
| `testcontainers` | **missing** — declared in the `dev` extra, needed by `tests/test_integration/test_projects_integration.py` |
| `mypy` / `pyright` | missing (unchanged truth of `docs/known-issues.md`) |
| `ruff` | present as a module (`python -m ruff` → 0.15.15); no `bin/ruff` console script |
| `pytest` | 9.1.1 |

## Decisions

1. **`conda` env `storico` is canonical. No `.venv` in this repository.**
2. **Commands stay environment-agnostic and CI-shaped**: `python -m pytest`, `python -m ruff`,
   `python -m uvicorn`. CI runs `pip install -e ".[dev]"` + bare `pytest`/`ruff`; copying that form
   is what keeps local and CI honest. The Makefile must not hardcode `conda`.
3. **`.gitignore` and `.dockerignore` keep their `.venv` entries.** They are ignore rules, not
   instructions: they exist so a future accidental `python -m venv` never gets committed or
   COPYied into the image. Documented as intentional.
4. **Historical `odd/tasks/*.md` files are not rewritten.** They record commands that were actually
   run at the time; editing them would falsify evidence. Only live instructions change.
5. **The `fastapi dev` diagnosis was corrected mid-flight.** The first statement of it was too
   strong: only the *path-argument* form is broken, not `fastapi dev` as a whole. Measured:
   `fastapi dev backend/src/storico/api/app.py` fails (`fastapi-cli` discovers with `dir(mod)`
   before `getattr`; `--app app` fails on the same guard; no `--factory` flag exists), and
   `fastapi dev` with no path fails from `backend/` because `get_default_path()` only tries
   `main.py` / `app.py` / `api.py` / `app/*.py` relative to the working directory. But
   `fastapi dev --entrypoint storico.api.app:create_app` **works** — verified end-to-end with a
   live request (`/openapi.json` 200 with the real schema, `/docs` 200, `/api/v1/health` 200).
   `--entrypoint` bypasses `get_app_name` entirely, and uvicorn's `Config.load()` then calls the
   loaded object with no arguments and infers "factory" when that succeeds.

   The residual argument for uvicorn is therefore not "it does not work" but "it does not fail
   loudly". `uvicorn/config.py` `load()` swallows `TypeError`: with `--factory` it logs and
   `sys.exit(STARTUP_FAILURE)`; without it, a `TypeError` raised inside `create_app()` is
   discarded and the bare function stays as the ASGI app, yielding a broken server with no
   startup error. Documented that way in `AGENTS.md`, with `--entrypoint` named as a working
   alternative that costs the explicit factory guarantee. fastapi-cli also does **not** load
   `.env` (no dotenv or `--env-file` anywhere in the package) — `Settings.load()` is what reads
   configuration, and the docs must not imply otherwise.

## Work units

| WU | Change | Surfaces |
| --- | --- | --- |
| WU1 | Env-agnostic Makefile (`PYTHON ?= python`); `setup` stops creating a venv | `Makefile` |
| WU2 | Canonical environment section for agents and humans | `AGENTS.md`, `README.md`, `CONTRIBUTING.md` |
| WU3 | Fix every live command that names `.venv` | `docs/testing.md`, `docs/deployment.md`, `docs/known-issues.md`, `backend/tests/test_integration/test_ollama_chat_live.py`, `backend/tests/test_integration/test_few_shot_rag_qdrant.py` |
| WU4 | Delete `backend/.venv` (297 MB, untracked, gitignored, no secrets inside) | — |
| WU5 | Independent verification of the frozen claims | — |

## Acceptance

| Claim | Result |
| --- | --- |
| No live `.venv` command survives | `grep -rn '\.venv'` over `Makefile AGENTS.md README.md CONTRIBUTING.md docs backend/tests` returns only 5 lines, all statements of absence (`AGENTS.md:52,55,56,101`, `README.md:130`). A repo-wide sweep outside `odd/tasks/` (frozen evidence) and the three ignore files returns nothing. |
| `make test-backend` runs `python -m pytest` and passes | `779 passed, 21 skipped, 2 warnings in 28.91s` via `make test-backend PYTHON="conda run -n storico python"`; the warning traceback paths confirm the `storico` environment |
| Canonical launcher works | `python -m uvicorn storico.api.app:create_app --factory --port 8013` → `/api/v1/health` **200**, `{"status":"ok","version":"0.5.1",...}` |
| `AGENTS.md` states the canonical environment | Subsection added before `### Reglas duras para agentes` (lines 52-103); stack-table row `FastAPI (Python 3.9+)` corrected to `(Python 3.12)` against `requires-python = ">=3.12"` |
| `backend/.venv` gone | `[ -e backend/.venv ]` → false; 297 MB reclaimed |
| Lint gates | `ruff check src tests` → "All checks passed!" ; `ruff format --check src tests` → "232 files already formatted" |

## Resolution of the environment drift

The owner chose to repair in place. `cd backend && conda run -n storico python -m pip install -e ".[dev]"`:

| Package | Before | After |
| --- | --- | --- |
| `cryptography` | 49.0.0 | **50.0.1** |
| `testcontainers` | missing | **4.15.0** |
| install metadata | `storico_backend-0.3.0` | **`storico_backend-0.5.1`** |

The `/api/v1/health` body independently confirms the metadata repair: it reports `"version":"0.5.1"`.

A **third** environment could also satisfy `import storico`: conda `base` carried its own stale editable
`storico-backend 0.3.0`, pointing at the same live source tree. The owner authorized its removal, so
`conda run -n base python -m pip uninstall -y storico-backend` was run. That removed exactly two
artifacts — `__editable__.storico_backend-0.3.0.pth` and `storico_backend-0.3.0.dist-info/` — with no
console scripts or `bin/` entries to clean up (`backend/pyproject.toml` declares no
`[project.scripts]`). `localllm_dataforge-0.2.0` in the same `site-packages` belongs to a different
project and was left alone; base's own `pytest 9.0.0`, `pip 24.2` and Python 3.12.2 are intact.

Note on what was actually stale: because the `.pth` pointed at the live source tree, base was running
*current* code. The staleness was the version metadata (0.3.0 against 0.5.1) and the dependency set
from the 0.3.0 era — not the code itself.

## Resolved: `sqlite3` was broken in conda `base`, and it was not a macOS quirk

`base`'s `_sqlite3.cpython-312-darwin.so` declares rpath `@loader_path/../../` (resolving to
`base/lib/`) and links `@rpath/libsqlite3.0.dylib`. That file did not exist in `base/lib/` — the
`sqlite3.40.0` entry there is an unrelated TCL extension directory, not a dylib — so the loader fell
through to `/usr/lib/libsqlite3.dylib`, the macOS system SQLite, which does not export
`_sqlite3_enable_load_extension`.

**The first diagnosis of the cause was wrong and is corrected here.** `sqlite` and `libsqlite` are
two separate conda-forge packages. The installed `sqlite-3.46.0-h5838104_0` ships **no `lib/` at all**
(only `bin/` and `info/`) and declares `libsqlite 3.46.0 hfb93653_0` as a dependency. The control that
pins it: the **`storico` env has the working chain** `libsqlite3.0.dylib -> libsqlite3.3.53.3.dylib`
plus `libsqlite3.dylib`, and its `aiosqlite`-based suite passes. So the missing artifact was not a
clobbered `sqlite` package but a `libsqlite` install whose files had been deleted from the prefix
while `conda-meta/libsqlite-3.46.0-hfb93653_0.json` still claimed all 5 of them.

### What did not work

```bash
conda install -n base --force-reinstall --no-deps "libsqlite=3.46.0=hfb93653_0"
# Verifying transaction: failed
# RemoveError: 'truststore' is a dependency of conda and cannot be removed from
# conda's operating environment.
```

`--force-reinstall` re-solves the base environment, and conda's own guard refuses any transaction that
would remove a conda dependency. This is a known block on force-reinstalling in `base`, not a symptom
of the missing files. Confirmed harmless: verification failed before execution — the 5 files were
still missing afterwards, `truststore` was intact, and a `conda list -n base` snapshot taken before
the attempt diffed **identical**.

### What fixed it

The package was already in the local cache with all 5 declared files, so the repair is a pure file
restore from verified local bytes — no network, no solve, nothing else in the environment touched:

```bash
B=/opt/homebrew/Caskroom/miniconda/base
C=$B/pkgs/libsqlite-3.46.0-hfb93653_0
mkdir -p $B/include $B/lib/pkgconfig
cp -a $C/include/sqlite3.h $C/include/sqlite3ext.h $B/include/
cp -a $C/lib/libsqlite3.0.dylib $C/lib/libsqlite3.dylib $B/lib/
cp -a $C/lib/pkgconfig/sqlite3.pc $B/lib/pkgconfig/
```

`cp -a` preserves the relative `libsqlite3.dylib -> libsqlite3.0.dylib` symlink instead of flattening
it into a second copy. Copying rather than hard-linking costs ~1.6 MB and is otherwise identical to
what conda's link step does; the prefix now matches what `conda-meta` already declared, so no metadata
update is needed or wanted.

### Verification

| Check | Result |
| --- | --- |
| All 5 files declared by `conda-meta/libsqlite-3.46.0-hfb93653_0.json` present | missing: **0** |
| Symlink preserved as a symlink | `libsqlite3.dylib -> libsqlite3.0.dylib` (18 bytes, `lrwxr-xr-x`) |
| The actual failure gone | `conda run -n base python -c "import sqlite3"` → `sqlite3 OK, version 3.46.0` |
| Nothing else in `base` moved | `conda list -n base` diffed against the pre-change snapshot: **identical** |

### Honest correction on the stakes

Earlier reasoning in this batch claimed a broken SQLite in `base` "can degrade conda's own
operations". That was not demonstrated: every `conda` command used throughout this work — `conda list`,
`conda install`, `conda env list`, `conda run` — functioned normally while SQLite was broken. The
verified consequence was confined to Python code that imports `sqlite3`. The correction is recorded
here rather than quietly dropped, because the wrong version was persuasive.

### Trap status

With `base` no longer carrying `storico-backend`, the env-agnostic Makefile's failure mode without an
activated environment is now unambiguous instead of misleading. Verified:

```
ImportError while loading conftest '.../backend/tests/conftest.py'.
    from storico.api.app import create_app
E   ModuleNotFoundError: No module named 'storico'
```

Previously the same command produced a SQLite `ImportError` from an unrelated environment, which
pointed away from the real cause. `AGENTS.md` documents the `conda activate storico` / `PYTHON=`
override for the headless case.
