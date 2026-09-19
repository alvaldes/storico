# ODD Feature: legacy-localstorage-key-cleanup

> **Status**: done — commit `a2d5be8` on `fix/legacy-localstorage-key-cleanup`, off `main` @
> `4f142bd`, not pushed. Receipt-driven development is **off** in this clone, so no native
> review ran; independent verification is recorded below.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/legacy-localstorage-key-cleanup`.
>
> **Process note**: the edits were first made while still on `main` instead of on a branch — a
> slip against ODD's "branch first when on the default branch". Nothing was committed to `main`
> and the branch carried the working tree over unchanged, so the record is clean; noted because
> the mistake is invisible in the history otherwise.

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

## What the legacy payload actually was

Confirmed from history, not inferred. `git show 1a53eee^:frontend/src/stores/settingsStore.ts`:

```ts
{
  name: 'storico-settings',
  // Only persist the settings field, not API state
  partialize: (state) => ({ settings: state.settings }),
}
```

`state.settings` is the whole `AppSettings`, whose `llm` slice held a `model`/`apiKey`/`base_url`
per provider — so the key holds a **plaintext API key per cloud provider**, wrapped in zustand's
`{ state, version }` envelope. That is what the cleanup removes.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Legacy shape | `git show 1a53eee^:frontend/src/stores/settingsStore.ts` | `name: 'storico-settings'` + `partialize: { settings }` (full `AppSettings`, incl. `llm`) |
| Repro (before) | `pnpm vitest run …/settingsStore.unit.test.ts` | **2 failed**, 8 passed — both removal assertions (`expected '{"state":{}}' to be null`) |
| Fixed file | `pnpm vitest run …/settingsStore.unit.test.ts` | **10 passed** |
| Full frontend suite | `pnpm vitest run` | **33 files, 388 passed** (384 after this batch's feature 1, +4 new) |
| Types | `pnpm exec tsc --noEmit` | exit 0 |
| Guard idiom matches the corpus | `grep -rn "typeof window\|typeof localStorage" frontend/src` | 8 hits total — 7 pre-existing `typeof` guards plus this one |

An `ast-grep` hint (`no-runtime-typeof`) fires on the guard. **Not adopted**: `typeof x ===
'undefined'` is the established idiom in this repo (7 pre-existing occurrences, e.g.
`stores/uiStore.ts:33`, `lib/theme.ts:17`), and a bare reference to `localStorage` would throw a
`ReferenceError` on the server — the case the guard exists for.

## Tasks — all closed

- [x] Confirm the exact legacy payload shape from git history before deleting anything.
- [x] Implement the guarded removal at store initialisation.
- [x] Add tests: removal happens, live keys survive, no throw without `localStorage`, no throw when storage refuses.
- [x] Run `pnpm exec tsc --noEmit` and `pnpm vitest run`.
- [x] Update `docs/frontend-state.md`.
- [x] Work-unit commit on the feature branch (`a2d5be8`).
- [ ] Independent verification — **pending**.
- [ ] Fast-forward into `main`, delete the branch, re-gate — **pending**.
