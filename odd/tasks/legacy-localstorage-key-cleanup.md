# ODD Feature: legacy-localstorage-key-cleanup

> **Status**: done — commits `a2d5be8` (the fix, its tests and `docs/frontend-state.md`),
> `4df5e3e` (the doc close) and the follow-up commit that answers the independent verification
> on `fix/legacy-localstorage-key-cleanup`, off `main` @ `4f142bd`, not pushed. Receipt-driven
> development is **off** in this clone, so no native review ran; the independent verification is
> recorded below and it changed the scope of this feature.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/legacy-localstorage-key-cleanup`.
>
> **Process note**: the first edits were made while still on `main` instead of on a branch — a
> slip against ODD's "branch first when on the default branch". Nothing was committed to `main`
> and the branch carried the working tree over unchanged, so the record is clean; noted because
> the mistake leaves no trace in history otherwise.

## Problem

The previous slice (`drop-per-user-llm-config`) replaced the persisted store key with
`storico-settings-v2` and **deliberately did not remove the old one** — recorded as decision
D7 in `odd/tasks/drop-per-user-llm-config.md`:

> **D7 | The legacy localStorage key | Not touched.** `removeItem('storico-settings')` is a
> behaviour change with its own risk (a browser that never upgrades keeps it), and the honest
> statement about current code already holds. Recorded.

The consequence is unchanged and now needs closing: a browser that ran an older build still
holds `storico-settings`, and that payload contained **per-user LLM API keys**. Nothing in the
current code reads that key, so it is a credential sitting in browser storage with no owner, no
reader and no expiry.

## What the legacy payload actually was

Confirmed from history, not inferred. `git show 1a53eee^:frontend/src/stores/settingsStore.ts`
(`1a53eee^` = `0d62ffe`, the last revision under the old key):

```ts
{
  name: 'storico-settings',
  // Only persist the settings field, not API state
  partialize: (state) => ({ settings: state.settings }),
}
```

`state.settings` is the whole `AppSettings`, whose `llm` slice held a `model`/`apiKey`/`base_url`
per provider — so the key holds a **plaintext API key per cloud provider**, wrapped in zustand's
`{ state, version }` envelope.

**Precision the verifier added**: the key was not always persisted with that `partialize`. It was
introduced in `e676b52` with **no `partialize` at all**, i.e. zustand's default whole-state
persist, which the credential-bearing `settings.llm` was part of. So the quoted shape is exact for
the revision cited, and the credential conclusion holds for every era the key existed.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Where the cleanup lives | Its own module, `@/lib/legacy-storage-cleanup`, so more than one call site can share one implementation. |
| D2 | Guard the environment | `typeof localStorage === 'undefined'` must be tolerated: the module is evaluated during server render (Astro SSRs these pages), so it cannot throw without a browser. |
| D3 | Only this key | Remove exactly `storico-settings`. `theme`, `storico-settings-v2` and `workspace-storage` are live and must survive. |
| D4 | Failure mode | A `localStorage` that throws (Safari private mode, storage disabled) must not break store creation or a page render: swallow it, as the rest of the module already tolerates an unavailable API (`settingsStore.ts:49-52`). The key survives, which is the honest outcome. |
| D5 | Test shape | Assert the removal **and** that the live keys are untouched. A test that only asserted the removal would pass even if the cleanup wiped all of storage. |
| D6 | Call sites | **Two, both idempotent**: `stores/settingsStore.ts` at module evaluation, and the bundled script in `components/astro/ThemeScript.astro`. This is the decision the verification forced; see below. |

## What the verification found, and why D6 exists

The first implementation cleaned up only when `stores/settingsStore.ts` was evaluated. The
verifier checked the reach instead of trusting it: the store's **only** importer chain is
`pages/[locale]/account.astro` → `AccountPage.tsx` → the store. So the cleanup ran for a browser
that visited `/account` and **nowhere else** — meaning most browsers would have kept the plaintext
key forever, and the feature would have looked done without being done.

The cleanup is therefore extracted to `@/lib/legacy-storage-cleanup` and called from two places:

- the store, at module evaluation, for anything that imports it; and
- the bundled script in `ThemeScript.astro`, which all three layouts include, so a browser is
  cleaned on its **first full page load whichever page that is**.

`ThemeScript` hosts it because it is the one script every layout already includes; the component's
own header records that the cleanup is not theme work and why it lives there.

**Remaining gap, recorded not hidden**: `pages/index.astro` does not include `ThemeScript`, so a
browser whose only visit is the landing page keeps the key until it loads another page. This is
also a pre-existing doc/code drift: `ThemeScript.astro`'s header states that "every layout … and
standalone page (`index.astro`) MUST include this component", and `index.astro` does not. Fixing
that is a change to the landing page's theme behaviour and belongs with the drift sweep, not here.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Legacy shape | `git show 1a53eee^:frontend/src/stores/settingsStore.ts` | `name: 'storico-settings'` + `partialize: { settings }` (full `AppSettings`, incl. `llm`) |
| Repro (before) | `pnpm vitest run …/settingsStore.unit.test.ts` | **2 failed**, 8 passed — both removal assertions (`expected '{"state":{}}' to be null`) |
| Store wiring | `pnpm vitest run …/settingsStore.unit.test.ts` | **10 passed** |
| Cleanup module | `pnpm vitest run src/lib/__tests__/legacy-storage-cleanup.test.ts` | **6 passed** |
| Full frontend suite | `pnpm vitest run` | **34 files, 394 passed** (384 at the end of this batch's feature 1, +10 new) |
| Types | `pnpm exec tsc --noEmit` | exit 0 |
| Build | `pnpm run build` | complete — proves the `ThemeScript` import bundles rather than failing at build time |
| Reaches the client | `grep -rl legacy-storage-cleanup dist/client/_astro/` | `ThemeScript.astro_astro_type_script_index_0_lang.qKOSAZe_.js` — the layout script chunk imports the cleanup |
| Is shipped | client-script list in `.vercel/output/_functions/manifest_*.mjs` | contains `_astro/ThemeScript.astro_astro_type_script_index_0_lang.qKOSAZe_.js` |
| Layout coverage | `grep -rln ThemeScript src/layouts/` | all three: `MainLayout`, `PublicLayout`, `AuthLayout` |
| Guard idiom matches the corpus | `git grep -n "typeof window\|typeof localStorage\|typeof document" -- frontend/src` | **8** — 7 pre-existing (e.g. `stores/uiStore.ts:33`, `lib/theme.ts:17`) + 1 here |

An `ast-grep` hint (`no-runtime-typeof`) fires on the guard. **Not adopted**: `typeof x ===
'undefined'` is the established idiom in this repo and a bare reference to `localStorage` would
throw a `ReferenceError` on the server — the case the guard exists for.

**Not verified, stated plainly**: the definitive runtime proof would be fetching real HTML from a
running server and finding the script tag on a non-`/account` page. That was not executed. The
evidence above is static (build graph plus the client-script manifest), which is why the
`index.astro` gap is reported from source rather than from a measurement.

## Independent verification

Ran over `4f142bd..4df5e3e`, read-only, on the **first** implementation. Six of seven claims
confirmed; one refuted as stated, and it is the finding that mattered:

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| F4 | low | The cleanup ran only where the store module is evaluated, and only `/account` imports it, so a browser that never visits `/account` keeps the plaintext key. | **Fixed** — extracted to `@/lib/legacy-storage-cleanup` and also called from `ThemeScript`'s script (D6). The remaining `index.astro` gap is recorded above. |
| F1 | low | The problem section pointed at `settingsStore.ts:97` for the comment naming the legacy key; the fix had moved it to `:126`, and it now lives at `settingsStore.ts:108`. | **Fixed** — this rewrite states the key's history from git rather than from a line pointer that the change itself invalidates. |
| F2 | low | The guard-idiom row named a grep without `typeof document` but reported the count that grep including it produces. | **Fixed** — the row now names the exact pattern it counts with. |
| F3 | low | "Touches only the three files" was refuted for the reviewed range (four, with the ODD doc). | **Not a document claim** — it was a constraint in the verification request. The code commit `a2d5be8` does touch exactly three files; no code collateral exists. |
| F5 | info | Removal precedes `create(persist(...))`. Harmless now (persist's name is `-v2`), but a future hydration-time migration reading the legacy key would find it already deleted. | **Recorded**, no change. |
| F6 | info | `sidebar-collapsed` is a stale localStorage key with no reader in HEAD (removed in `a73578b`). It holds `"true"`/`"false"` — no credential. | **Recorded**, no change: not a credential, and out of this feature's scope. |
| F7 | info | `frontend/dist` and `frontend/.vercel/output` still embed the pre-change store shape. | **Recorded**, tracked by `odd/tasks/drop-stale-build-artifacts.md`. |

Two further things the verifier established, kept because they are load-bearing:

- **The tolerance tests are guard-only.** They pass on the pre-fix code too, so they are not
  evidence of the fix. One of them also did not assert that `removeItem` was actually reached;
  the module's own test now pins that (`toHaveBeenCalledWith(LEGACY_KEY)`), and the pre-fix
  reproduction of the two removal assertions is what carries the proof.
- **`vi.resetModules()` is load-bearing.** A cached dynamic import does *not* re-run the
  module-scope call, which the verifier demonstrated separately — so the store tests would fail
  spuriously without it.

## Tasks — all closed

- [x] Confirm the exact legacy payload shape from git history before deleting anything.
- [x] Implement the guarded removal.
- [x] Add tests: removal happens, live keys survive, idempotent, no throw without `localStorage`, no throw when storage refuses.
- [x] Run `pnpm exec tsc --noEmit`, `pnpm vitest run` and `pnpm run build`.
- [x] Update `docs/frontend-state.md`.
- [x] Work-unit commit on the feature branch (`a2d5be8`).
- [x] Independent verification — 6/7 confirmed, F4 fixed by widening the reach, F1/F2 fixed here.
- [ ] Fast-forward into `main`, delete the branch, re-gate — **pending**.
