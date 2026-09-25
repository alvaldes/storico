# ODD Feature: vm-disk-hygiene

> **Status**: closed on `chore/vm-disk-hygiene` — WU1 (`9134e78`) and WU2 (this commit) landed, and the
> cleanup was measured on the production host before this record was closed. **Receipt-driven
> development is off in this clone** (decided by clone_local on 2026-09-24).
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)

## Problem

The production VM's disk is 45 GB and was **69 % full** (31 GB used, 15 GB free). Almost none of that
is the application. Measured on 2026-09-25 with `df`, `docker system df` and `docker buildx du`:

| What | Size | Reclaimable |
| --- | --- | --- |
| Build cache (207 records) | 25.71 GB | **25.71 GB** |
| Images (10) | 3.82 GB | 2.26 GB |
| Containers (1) | 5.2 MB | 0 |
| Volumes | 0 | 0 |

Two mechanisms feed it, and **nothing removes either**:

1. **Build cache.** Every `docker build` in `deploy-backend.yml` leaves its cache records. 25.71 GB of
   them on a 45 GB disk.
2. **Dangling images.** The workflow tags the running image as `storico-api:previous` before
   rebuilding, so the image from two releases back loses its tag and stays on disk. There are **8** of
   them, ~652 MB nominal each. They share layers with the live images, so the honest reclaimable
   figure is `system df`'s 2.26 GB, not the 5.2 GB their sizes add up to.

Verified there is no cleanup anywhere:

- no `/etc/docker/daemon.json`, so the daemon does not garbage-collect;
- `crontab -l` for `ubuntu` is empty;
- the only relevant timer is `fstrim.timer` (TRIM), which deletes nothing;
- and the repository contains **zero** occurrences of `docker image prune`, `docker system prune` or
  `docker builder prune`.

This is the same defect class the repository spent three batches removing — a system that silently
accumulates work nobody looks at — with one difference worth recording: the failure mode here is
benign. `docker build` runs **before** `docker stop`, so a full disk fails a deploy with the live
release still up.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | What to prune | **Bounded, not everything.** `docker builder prune --filter until=168h` keeps a week of cache and drops the rest. The cache is what avoids rebuilding the dependency layer from scratch on every deploy, so deleting all of it trades a permanent cost for a one-time gain. `-af` stays written down as the alternative. |
| D2 | The image prune | `docker image prune -f`, **never `-a`**. Without `-a` only untagged images are removed, so `storico-api:previous` survives by construction rather than by luck. This is the invariant the contract test pins. |
| D3 | Where in the deploy it runs | **After the readiness gate.** `set -e` then aborts before the cleanup when a deploy fails, so the recovery re-run keeps the cache it needs. Pruning first would make a failed deploy slower to retry, which is exactly backwards. |
| D4 | Guard against regression | **A contract test**, because nothing else reads the workflow. It parses with `re` + `pathlib` like `test_env_contract.py` does: `pyyaml` is not a declared dependency of this project. |
| D5 | Does this belong with `retire-vercel-api-project` | **No.** That batch deletes dead configuration; this one changes the production deploy path. Separate branches, separate reviews. |

## Work units

| # | Unit | Commit | Files |
| --- | --- | --- | --- |
| WU1 | Bounded cleanup in the deploy + its contract test + the doc line | `9134e78` | `.github/workflows/deploy-backend.yml`, `backend/tests/test_unit/test_deploy_workflow_contract.py`, `docs/deployment.md` |
| WU2 | The measured cleanup on the host, recorded | _this commit_ | this record, updated with the measurement |

## What lands

- `deploy-backend.yml`: after the readiness gate succeeds, prune untagged images and build-cache
  records older than a week, then report the disk it freed.
- `backend/tests/test_unit/test_deploy_workflow_contract.py`: the ordering and the dangling-only flag,
  both read from the workflow text.
- `docs/deployment.md`: the maintenance note next to the rollback paragraph it protects.

## Deliberately not done

- **No `docker system prune -a`.** It would delete `storico-api:previous`, which is the only rollback
  the deploy leaves.
- **No change to the Dockerfile.** It installs `.[dev]`, so the production image carries pytest, ruff
  and testcontainers. That is a real finding — a fat image rather than a growing one — but it is a
  different problem from disk accumulation, and it belongs to its own batch with its own measurement.
- **No change to the retention of anything outside the VM.** The frontend still deploys a preview per
  branch on Vercel; its bundles are small, and after `retire-vercel-api-project` the team's Functions
  Storage sits near 1 GB of 10 GB.

## Measured result (2026-09-25, production host)

Run by hand with the exact commands WU1 puts in the workflow, so the deploy path is not the first
place they execute:

| | Before | After |
| --- | --- | --- |
| Filesystem | 31 GB used, 15 GB free, **69 %** | 17 GB used, 28 GB free, **38 %** |
| Images | 10 (3.82 GB) | **2** — `storico-api:latest` and `storico-api:previous` |
| Build cache | 25.71 GB | 13.55 GB |

`docker builder prune -f --filter until=168h` reported **`Total: 12.16GB`** reclaimed, and the image
prune took the 8 untagged images. Two things the numbers say that the policy should be read against:

- **The rollback survived**, which is the invariant D2 is about: `docker images` still lists
  `storico-api:previous` after both prunes, and the container was never touched (`Up 14 hours`
  throughout).
- **13.55 GB of cache is the floor of a week.** Most of the cache came from the 2026-09-20..24 commit
  burst, so the ~20 builds of the last seven days are what remains. That is the price of the fast
  rebuild, and it is the reason this window is a decision rather than a default: `docker builder
  prune -af` would take that 13.55 GB too, and the next deploy would rebuild the dependency layer
  from scratch.

Production was verified from outside with the cleanup already done: `/api/v1/health` 200,
`/api/v1/health/ready` 200, frontend 302.

## Verification

| Claim | How | Result |
| --- | --- | --- |
| The cleanups are bounded exactly as decided, and ordered after the gate | `pytest -q -m unit tests/test_unit/test_deploy_workflow_contract.py` | **8 passed** |
| The workflow is still valid YAML and the script survives parsing | `js-yaml` over the file, then reading `steps[1].with.script` back | parses; its tail is the two prunes, the `echo` and the `df` |
| The script is still valid shell | `bash -n` over the extracted 195-line body | clean |
| The commands do what they claim | the two prunes on the VM, before/after | **14 GB freed**, table above |
| The rollback survives the cleanup | `docker images` after the image prune | `storico-api:previous` still there |
| The deploy path is untouched | full suite, lint, format | `857 passed, 21 skipped`; `ruff check`/`format --check` green |
