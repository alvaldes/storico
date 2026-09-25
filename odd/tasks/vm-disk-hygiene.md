# ODD Feature: vm-disk-hygiene

> **Status**: in progress on `chore/vm-disk-hygiene` (cut after `retire-vercel-api-project` lands).
> **Receipt-driven development is off in this clone** (decided by clone_local on 2026-09-24).
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
| WU1 | Bounded cleanup in the deploy + its contract test + the doc line | _pending_ | `.github/workflows/deploy-backend.yml`, `backend/tests/test_unit/test_deploy_workflow_contract.py`, `docs/deployment.md` |

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

## Verification

| Claim | How |
| --- | --- |
| The cleanups are bounded exactly as decided | `pytest -q -m unit backend/tests/test_unit/test_deploy_workflow_contract.py` |
| The workflow script is still valid shell | extract the `script:` block and run `bash -n` on it |
| The commands do what they claim | run the same two prunes on the VM and compare `df -h /` and `docker system df` before and after |
| The rollback survives the cleanup | `docker images storico-api` still lists `:previous` after the image prune |
