# ODD Feature: drop-stale-build-artifacts

> **Status**: planning — no commit, no evidence yet.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `chore/drop-stale-build-artifacts` (to be created off `main` after the code
> features land, so the rebuilt artifacts reflect them).
> **Receipt-driven development**: off in this clone.

## Problem

`frontend/.vercel/output/` (19 MB, 2161 files) and `frontend/dist/` (1.9 MB, 94 files) hold
bundles written in a single ~7-second window on **2026-09-17 22:58**, i.e. **before** the
commits that dropped the per-user LLM config and the false encryption claim (2026-09-18).

They are stale in a way that is provable, not merely suspected. They still contain strings
removed from the source:

- `setLLMProvider` / `setOllamaConfig` / `setOpenAIConfig` / `setAnthropicConfig` — deleted by
  `52d8a6f`; present in 1 `dist/` file and 3 `.vercel/output/` files each.
- `gpt-4o-mini`, `claude-3-haiku`, `gemini-2.0-flash`, `llama3.2`, `maxTokens` — the deleted
  per-provider defaults.
- The pre-change comment text `// New key — old 'storico-settings' still has API keys
  persisted, clean slate`, in the unminified SSR bundles.
- **`"Stored encrypted at rest"`** — the claim retracted by `7617b08`, still present in 8 built
  files.

The last one is why this matters beyond tidiness: the artifact that ships can state something
the code stopped claiming. Notably, `feat/encrypt-workspace-api-keys` is what would make that
particular sentence true again.

Both directories are **untracked and ignored** (`git ls-files` returns 0 for both;
`.gitignore:10`, `.gitignore:26`, `.gitignore:52`, `frontend/.gitignore:2`), and **nothing in
the repository reads them**: `frontend/package.json:8-16` only ever writes `dist/` via
`astro build`; `Makefile:32-33` builds as a smoke test; `.github/workflows/ci.yml:69-75` runs
only `tsc --noEmit` and `vitest run` and never builds the site; there is no frontend deploy
workflow at all. The risk is therefore purely operational — a deploy that reuses
`.vercel/output` without rebuilding serves the stale bundle — and it is already recorded as
such in `odd/tasks/honest-llm-copy-and-doc-drift.md:327-333` and
`odd/tasks/drop-per-user-llm-config.md:269`.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Delete | Remove both directories. They are outputs, nothing reads them, and a build regenerates them: `pnpm run build` for `dist/`, `vercel build` for `.vercel/output/`. |
| D2 | Ordering | Do this **last**, after the code features land, so the regenerated `dist/` proves the current tree rather than an intermediate one. |
| D3 | Proof, not assertion | Verify after rebuilding that the stale strings are actually gone from the fresh artifacts. Deleting a directory and assuming the rebuild is clean is the same class of unverified claim this feature exists to remove. |
| D4 | The operational hazard | A deletion fixes today and cannot prevent tomorrow. Record the hazard where a deploy would look — `docs/deployment.md` — stating that the frontend output must be rebuilt, not reused. A CI guard is **not** added in this slice: CI does not build the frontend today, and adding a build job is a workflow change with its own cost, so it is proposed rather than bundled. |
| D5 | No commit of artifacts | Nothing is committed: both paths stay ignored. This feature commits documentation only, and must not accidentally start tracking build output. |

## Non-goals

- No new CI job that builds the frontend.
- No `vercel.json` at the frontend root (the only one in the repo is the backend's).
- No change to the build configuration or to the Astro adapter.

## Tasks

- [ ] Record the pre-deletion evidence: sizes, file counts, mtimes, and the exact stale strings
      with the files that carry them.
- [ ] Confirm nothing tracked is lost (`git status` unchanged after deletion).
- [ ] Delete `frontend/dist` and `frontend/.vercel/output`.
- [ ] Rebuild (`pnpm run build`) and verify the stale strings are absent from the fresh output.
- [ ] Add the deploy-order note to `docs/deployment.md`.
- [ ] Work-unit commit (documentation only).
- [ ] Fast-forward into `main`, delete the branch, re-gate.

## Evidence

_None yet._
