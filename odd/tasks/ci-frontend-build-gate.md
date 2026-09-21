# ODD Feature: ci-frontend-build-gate

> **Status**: landed on `main` @ `10d8904` (one commit, ff-merge). Native review
> `review-21fb528e97bf7055`: approved and burned, no correction; eight non-blocking advisories, listed
> below. First CI run of the gate: **success** (`8. Build (astro build)`, run `35653955533`).
> **Created**: 2026-09-21
> **Workflow**: Organic Driven Development (ODD)

## Problem

`prod.todo.md` carried one row: `.github/workflows/ci.yml` runs `tsc` and `vitest`, never
`astro build`. The gate already existed as a **convention** — prior verifications ran
`pnpm run build` by hand and recorded the result (`custom-model-picker.md`,
`llm-model-probe-selection.md`, `custom-provider-model-discovery.md`,
`custom-model-list-visibility.md`) — but as automation it did not exist. So a pull request could
merge with a frontend that Vercel would refuse to deploy, and the repository's own pipeline would
report success over it.

`drop-stale-build-artifacts.md` had recorded this as an explicit follow-up **with the trade named**:
"Adding a build job is a real cost on every pull request, so it is proposed rather than bundled: the
trade is minutes-per-PR against the class of failure that shipped a retracted sentence." This feature
closes that follow-up with the cost measured rather than assumed.

## Measured before writing the step, because a gate that is red on arrival is not a gate

The risk was never the build. It was the environment:

- `frontend/src/lib/config.ts` says of itself that it "throws immediately at import time" on a
  missing variable, and it requires `API_URL` and `AUTH_SECRET`.
- Three routes import it: `pages/[locale]/api.astro`, `pages/[locale]/status.astro` and
  `pages/api/v1/[...path].ts`.
- CI has no `.env`. If that module were evaluated during the build, the new step would fail on every
  pull request.

Four measurements. The first two are recorded because **they were wrong**, and because one of them is
the kind of wrong that looks like evidence:

| # | What was run | Result | Verdict |
|---|---|---|---|
| 1 | `pnpm build` in the worktree | exit 0, `Server built in 8.55s`, `.vercel/output/` written | **Contaminated.** `frontend/.env` is a symlink to the repository-root `.env` (`ls -la`), so the build read real values. It proves the build works, not that it works in CI. |
| 2 | `pnpm build` in a `/tmp` copy with `node_modules` symlinked and `.env` excluded | exit 1 | **Invalid.** The failure was Vite's compile-metadata cache in the linked store — `No cached compile metadata found for … ClientRouter.astro… The main Astro module … should have compiled and filled the metadata first` — an artifact of the isolation method, not a missing variable. It says nothing about CI. |
| 3 | `pnpm build` in the worktree with Vite's `envDir` pointed at an empty directory, through a temporary `--config` | **exit 0**, `Server built in 8.92s` | The build does not evaluate the config module. |
| 4 | The same, with `env -i PATH HOME` for a stripped environment — no `.env` values and no ambient variables | **exit 0**, `Server built in 8.45s` | This is the CI condition, reproduced. |

What that means: the routes importing `config.ts` are server-rendered, so the module is evaluated
**per request at runtime**, not while the build runs. The step is safe to add, and the honest
statement of that fact is measurement 4, not measurement 1.

## What lands

- **`.github/workflows/ci.yml`** — a `Build (astro build)` step in the `frontend` job, after
  `vitest`, running the package's own `pnpm build` rather than a hand-written command, so the CI
  path and the local path cannot drift.
- **`docs/deployment.md`** — the "Artefactos de build del frontend" note said CI runs only `tsc` and
  `vitest`, and that "el frontend no se construye en CI". Both become false with the step, so both are
  corrected in the same commit that makes them false.
- **`prod.todo.md`** — the row moves to ✅, with what the gate covers and what it does not.
- **`odd/tasks/drop-stale-build-artifacts.md`** — its follow-up 1 is marked closed with the pointer
  here, because a record that proposes work should say when the work arrives.

## What the gate covers, and what it does not

It catches a **broken build before merge**, which is the failure that previously depended on a person
noticing. It does **not** catch a **stale artifact reused by a manual deploy** — that is the other
half, and it is the deployment note's job. Two different protections for two different failures;
neither replaces the other.

## Cost

Measured on this machine, warm `node_modules`:

| Gate | Result |
|---|---|
| `pnpm exec tsc --noEmit` | exit 0 |
| `pnpm vitest run` | 36 files, 421 tests passed, 13.31 s |
| `pnpm build` | complete, `Server built in 11.59s`, `real 13.13` s |

So the marginal cost on a pull request is the build step only — the job already installs, type-checks
and tests. Seconds, not minutes, which settles the trade the earlier record left open.

## Gates

Backend is untouched by this candidate (one workflow file and three documents; no file under
`backend/`), so its gates are informational here. The frontend gates above are the candidate's own
surface and all three are green.

## Review

Native review of the single commit, lineage `review-21fb528e97bf7055`: **approved and burned**, no
correction, four reviewers prepared and four submitted.

The tier came back **`high` with four lenses** again, and again for a reason that names the file rather
than the change:

```
risk_reasons: [
  {code: process_boundary, signal: shell_process, path: .github/workflows/ci.yml},
  {code: shell_source, signal: shell_process, path: .github/workflows/ci.yml}
]
```

So **any workflow file is a hot path**: three lines of `run:` in a job that starts processes are classed
as process-boundary and shell code. Same family as `docs/security.md` in the previous batch, and as the
extension-keyed `process_boundary` recorded in `release-versioning.md`. Three candidates in a row, all of
them documentation or CI configuration, all `high` with four lenses — worth budgeting when a batch is
planned, not when it is reviewed.

**The measurement was confirmed by its first real run.** CI run `35653955533` executed the new step and
it passed: `8. Build (astro build) → completed/success`, the whole job green. That is the evidence the
step needed, and it is why measurement 4 (the stripped environment) was worth doing instead of trusting
measurement 1 (the contaminated one).

### Advisories (eight, all `SUGGESTION` / informational)

None opened a correction. As in the previous batch, the closure lists them by id and location without
their text, so these rows are the whole record of them.

| Id | Lens | Location |
|---|---|---|
| `R2-dense-todo-row` | readability | `prod.todo.md:46` |
| `R2-fwd-commit-ref` | readability | `odd/tasks/ci-frontend-build-gate.md:6` |
| `R3-env-assumption` | reliability | `.github/workflows/ci.yml:77-82` |
| `R3-output-unasserted` | reliability | `.github/workflows/ci.yml:83-85` |
| `R3-stale-boundary-consistent` | reliability | `prod.todo.md:46` |
| `R4-latency-1` | resilience | `.github/workflows/ci.yml:83` |
| `R4-obs-1` | resilience | `.github/workflows/ci.yml:76-83` |
| `R4-scope-1` | resilience | `prod.todo.md:46` |

Two are worth naming because they point at the comment this candidate adds: `R3-env-assumption` — the
comment asserts that the build needs no environment, and a reader of the workflow cannot verify that from
the workflow — and `R3-output-unasserted` — the step asserts the exit code, not that an artifact was
produced. Both are recorded rather than fixed, because editing the tree after approval would deliver
something other than what was reviewed.
