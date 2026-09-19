# ODD Feature: legacy-localstorage-key-cleanup

> **Status**: planning — no commit, no evidence yet.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/legacy-localstorage-key-cleanup` (to be created off `main` @ `6174f5a`).
> **Receipt-driven development**: off in this clone.

## Problem

The previous slice (`drop-per-user-llm-config`) replaced the persisted store key with
`storico-settings-v2` and **deliberately did not remove the old one** — recorded as decision
D7 in `odd/tasks/drop-per-user-llm-config.md`:

> **D7 | The legacy localStorage key | Not touched.** `removeItem('storico-settings')` is a
> behaviour change with its own risk (a browser that never upgrades keeps it), and the honest
> statement about current code already holds. Recorded.

The consequence is unchanged and now needs closing: a browser that ran an older build still
holds `storico-settings`, and that payload contained **per-user LLM API keys** (the pre-`v2`
`settings.llm` block). Nothing in the current code reads that key, so it is a credential
sitting in browser storage with no owner, no reader and no expiry.

Current state of the key in the tree — the name appears **only inside a comment**
(`frontend/src/stores/settingsStore.ts:97`); there is no `removeItem` call anywhere.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Where the cleanup lives | At `settingsStore` module initialisation, next to the persist configuration that explains the `-v2` suffix — the same place the key's history is documented. |
| D2 | Guard the environment | `typeof localStorage === 'undefined'` must be tolerated (SSR / Astro server render and the unit-test environment), so the cleanup cannot throw during a server render. Wrapped defensively rather than assuming a browser. |
| D3 | Only this key | Remove exactly `storico-settings`. `theme` and `storico-settings-v2` are live and must survive. |
| D4 | Failure mode | A `localStorage` that throws (Safari private mode, storage disabled) must not break store creation: swallow the error the way the rest of the module tolerates an unavailable API (`settingsStore.ts:49-52`). |
| D5 | Test shape | Assert the removal happens **and** that the live keys are untouched. A test that only asserts the removal would pass even if the cleanup also wiped `storico-settings-v2`. |

## Non-goals

- No change to what `storico-settings-v2` persists (`partialize` stays export-only).
- No migration of data out of the legacy key: the values in it are credentials that should not
  be carried forward.

## Tasks

- [ ] Confirm the exact legacy payload shape from git history before deleting anything.
- [ ] Implement the guarded removal at store initialisation.
- [ ] Add tests: removal happens, live keys survive, no throw without `localStorage`.
- [ ] Run `pnpm exec tsc --noEmit` and `pnpm vitest run`.
- [ ] Update `docs/frontend-state.md` so the key's disposition is recorded there too.
- [ ] Work-unit commit on the feature branch.
- [ ] Independent verification.
- [ ] Fast-forward into `main`, delete the branch, re-gate.

## Evidence

_None yet._
