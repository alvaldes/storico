# ODD Feature: retire-vercel-api-project

> **Status**: closed on `chore/retire-vercel-api-project` — WU1 (`5d77239`), WU2a (`700c4bb`), WU2b
> (`2ef043a`) and WU2c (this commit) landed. **Receipt-driven development is off in this clone**
> (decided by clone_local on 2026-09-24; global is on), so native review is not part of this batch.
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `chore/retire-vercel-api-project` (off `main` @ `7fe8f01`).

## Problem

Six tracked artifacts are the build configuration of a backend deployment that does not exist:

| Artifact | What it configures |
| --- | --- |
| `backend/vercel.json` | rewrites every path to `/api/index.py` |
| `backend/api/index.py` | the Mangum ASGI→HTTP entrypoint (`handler = Mangum(app)`) |
| `backend/api/__init__.py` | empty package marker that exists only for the file above |
| `backend/entrypoint.sh` | a shell entrypoint no Dockerfile references |
| `backend/requirements.txt` | its entire content is `-e .` with a comment saying Vercel installs it |
| `mangum` + `[tool.vercel]` in `backend/pyproject.toml` | the dependency and the entrypoint table |

`odd/tasks/prod-honesty-followups.md` recorded them as **D5** and deliberately **deferred** them, with
the reason written down: *"nobody has verified whether a Vercel project still points at `backend/`"*.
Deferring was the right call, because there was one, and it was live.

## The measurement that unblocked D5 (2026-09-25)

Every number below was read from the authenticated Vercel CLI or from the production endpoints, not
from prose. The operator supplied the one figure that only the dashboard shows.

| Measurement | Value |
| --- | --- |
| Team Functions Storage | **7.92 GB / 10 GB**, and `storico-api` was **6.94 GB** of it |
| Is it the endpoint? | No — `https://storico-api.vercel.app/` answers **404** |
| Where does production point? | The frontend's production `API_URL` is `https://storico-api.163.192.150.75.sslip.io`, and `/api/v1/health/ready` answers **200** |
| Why it grew | `vercel projects ls` showed it "Updated 29m" after the last merge, and `vercel alias ls` showed `storico-api-git-<branch>-…vercel.app` aliases for many branches: it deployed on every push to every branch |
| Commit pressure | ~99 commits touched `backend/**` between 2026-09-13 and 2026-09-25 |
| Secrets inside | 9 variables in Production **and** Preview, including production's `STORICO_DATABASE_URL` |
| Custom domain attached? | No — the team's only domain, `alvaldes.online`, has no nameservers and no project |
| Required check broken? | No — `main` has no branch protection |

Functions Storage is the function bundle **retained with each deployment**, and the quota is the
**team's**: exhausting it blocks deploys for every project, the production frontend included. That is
what turned a cosmetic leftover into a blocker.

**The project was deleted on 2026-09-25** with `vercel project rm storico-api`. Verified afterwards:
it is gone from `vercel projects ls`, and production still answers (frontend `302`, VM API `200`).
Nothing was lost but redundancy: `STORICO_DATABASE_URL` and `STORICO_AUTH_JWT_SECRET` also live in
the VM's `.env`, `STORICO_AUTH_JWT_SECRET` equals the surviving frontend's `AUTH_SECRET`, and
`STORICO_ENCRYPTION_KEY` was never in that project at all.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Delete the artifacts or keep them | **Delete.** The premise D5 deferred on is resolved: the project existed, and it is gone. With nothing pointing at `backend/`, the artifacts configure nothing. |
| D2 | How the records are corrected | **Dated notes, never rewritten bodies** — the same norm as D3 of `prod-honesty-followups`: a `Status` header and a present-tense claim are navigation and get corrected; the body that records what was true at the time stays as written. |
| D3 | `backend/fly.toml` and `railway.json` | **Out of scope.** Both are untracked and gitignored (`.gitignore:68`, `:69`), so they are the operator's local leftovers, not repository debt. Recorded here so the next reader does not re-litigate them. |
| D4 | The review path | **None available.** RDD is off in this clone; independent verification of the diff is the substitute, and that is stated rather than implied. |

## Work units

| # | Unit | Commit | Files |
| --- | --- | --- | --- |
| WU1 | Delete the dead Vercel configuration | `5d77239` | the five files above, plus `backend/pyproject.toml` |
| WU2a | Correct the repository documents | `700c4bb` | `AGENTS.md`, `prod.todo.md`, `docs/security.md`, `docs/api.md`, `docs/README.md` |
| WU2b | Correct the ODD records | `2ef043a` | `prod-honesty-followups.md`, `production-state-and-domain-decision.md`, `schema-drift-gate.md`, `provider-literal-and-copy-drift.md` |
| WU2c | `frontend/.env.example` | _this commit_ | the production comment line; the harness safety policy refuses `.env*` paths, so the owner authorized it explicitly and the edit was applied by shell |

## What lands

- `backend/vercel.json`, `backend/api/index.py`, `backend/api/__init__.py`, `backend/entrypoint.sh`
  and `backend/requirements.txt` deleted.
- `backend/pyproject.toml` without the `mangum` dependency and without the `[tool.vercel]` table.
- The records that claimed a live project: corrected with a date, not silently.
- `frontend/.env.example`: the production comment no longer names the deleted project. The harness
  safety policy refuses `.env*` paths, so this one line waited for an explicit owner authorization
  and was applied through a shell edit rather than the file tools.

## Deliberately not done

- **`.env.prod.local` was not touched.** It is the operator's local, gitignored file, and it is
  missing backend names the backend actually reads (`STORICO_AUTH_JWT_SECRET`,
  `STORICO_ENCRYPTION_KEY`, `STORICO_OLLAMA_HOST`, `STORICO_GOOGLE_API_KEY`,
  `STORICO_OPENAI_API_KEY`). Recorded in the operator's vault note of the same date; the file is
  fixed separately.
- **Nothing was pushed.** `main` was already 11 commits ahead of `origin/main` when this branch was
  cut; pushing is the operator's decision.
- **The VM's disk hygiene is a separate feature** (`vm-disk-hygiene`), because it changes the
  production deploy path and deserves its own review.

## Verification

| Claim | Command | Result |
| --- | --- | --- |
| The files are gone | `git ls-files backend/api backend/vercel.json backend/entrypoint.sh backend/requirements.txt` | empty after the commit |
| CI lint is green | `ruff check src tests` (from `backend/`) | `All checks passed!` |
| CI format is green | `ruff format --check src tests` | `237 files already formatted` |
| Unit suite is green | `pytest -q -m unit` | `131 passed, 739 deselected` |
| A parked debt closes | `ruff check .` (from the repository root) | **green** — it was red on exactly one error, the `I001` in `backend/api/index.py` that `provider-literal-and-copy-drift.md:159` recorded as unreachable by CI |
| Formatting is green repo-wide too | `ruff format --check .` (from the repository root) | `237 files already formatted` |
| Production is untouched | `curl` frontend + VM `/health/ready` | `302` and `200` |
