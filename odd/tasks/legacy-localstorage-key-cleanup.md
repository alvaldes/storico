# ODD Feature: legacy-localstorage-key-cleanup

> **Status**: done and landed on `main` @ `957cb3b` — five commits from `4f142bd`:
> `a2d5be8` (the fix, its tests and `docs/frontend-state.md`), `4df5e3e` (the doc close),
> `ed9518a` (the widened reach that answers the first verification), `3183eb6` (the rewritten
> record) and `957cb3b` (the retraction and test hygiene that answer the second). Branch deleted,
> `main` re-gated, **not pushed**. Receipt-driven development is **off** in this clone, so no
> native review ran; **two** independent verifications did, and the second corrected this
> document's own conclusion.
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

**A "remaining gap" was recorded here and it was wrong; the second verification refuted it.** This
document first claimed that `pages/index.astro` does not include `ThemeScript` and therefore "a
browser whose only visit is the landing page keeps the key until it loads another page". The
verifier fetched `/` from the shipped SSR function and measured `status=302 location=/en/` with an
empty body: `index.astro` is seven lines whose only statement is an `Astro.redirect`, and
`middleware.ts` answers `/` before the route is reached. A browser cannot stay on that page, and
the target `/[locale]/` is `ThemeScript`-covered. **Coverage is therefore complete**: 18 of 19
pages are covered through their layout, and the nineteenth redirects to one that is.

The doc/code drift underneath the withdrawn claim is real and pre-existing:
`ThemeScript.astro:14-15` states that "every layout (MainLayout, PublicLayout, AuthLayout) and
standalone page (`index.astro`) MUST include this component", while `index.astro` never has — it
has been a redirect in all four of its historical revisions. That is a doc statement that is not
true, and it belongs with the drift sweep rather than here.

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
| Is shipped | `entryModules` in `.vercel/output/_functions/manifest_*.mjs` | contains `_astro/ThemeScript.astro_astro_type_script_index_0_lang.qKOSAZe_.js` |
| Served in real HTML | boot the shipped SSR function and fetch pages | `/_astro/ThemeScript.astro_astro_type_script_index_0_lang.qKOSAZe_.js` present on `/en/about`, `/en/login`, `/en/`, and even the 404 |
| `/` cannot strand a browser | fetch `/` | `status=302 location=/en/` — `index.astro` never renders, so the withdrawn gap was unreachable |
| Layout coverage | `grep -rln ThemeScript src/layouts/` | all three: `MainLayout`, `PublicLayout`, `AuthLayout` |
| Guard idiom matches the corpus | `git grep -n "typeof window\|typeof localStorage\|typeof document" -- frontend/src` | **8** — 7 pre-existing (e.g. `stores/uiStore.ts:33`, `lib/theme.ts:17`) + 1 here |

An `ast-grep` hint (`no-runtime-typeof`) fires on the guard. **Not adopted**: `typeof x ===
'undefined'` is the established idiom in this repo and a bare reference to `localStorage` would
throw a `ReferenceError` on the server — the case the guard exists for.

**Not verified, stated honestly**: the browser-level observation — executing the chunk in a real
engine — was not done, and this repo has no Playwright (see `AGENTS.md`). "Runs in a browser"
rests on the module-script tag in the served HTML plus Astro's ClientRouter code path, not on a
browser observation.

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

### Second verification — the widened reach (`4df5e3e..3183eb6`)

Ran over the follow-up commit that answered F4. All seven claims confirmed except the one this
document itself had wrong. It also discharged the runtime proof the first report had listed as
not executed, by booting the shipped SSR function and reading real HTML.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| G1 | low–medium | The "remaining gap" recorded here did not exist: `/` answers `302 → /en/` with an empty body, so a browser cannot stay on `index.astro`, and the target is covered. | **Fixed** — the gap is withdrawn above, with the measurement that refutes it. |
| G2 | low | The `typeof localStorage` guard has **no independent coverage**: deleting it keeps all 6 module tests and the whole 394-test suite green, because the surrounding `catch` swallows the resulting `ReferenceError` (mutant M2). The test named "does not throw on the server" pins the no-throw contract, not the guard. | **Documented, guard kept** — the two are not redundant in intent (no storage vs. storage that refuses), and the guard is this repo's SSR idiom. The test's comment now says exactly what it does and does not pin, instead of implying coverage it lacks. |
| G3 | low | `vi.unstubAllGlobals()` and `spy.mockRestore()` were manual while `vitest.config.ts` sets no `restoreMocks`/`unstubGlobals`, so a failing assertion could leak a throwing `removeItem` or an absent `localStorage` into later tests. | **Fixed** — an `afterEach` restores both unconditionally. |
| G4 | info | `ThemeScript`'s script now imports the cleanup chunk, so a chunk-load failure would also block theme initialisation on that page. | **Accepted** — same origin, immutably cached, and a page whose module chunks fail is broken regardless. Recorded rather than worked around, since the alternative (inlining the key into the anti-flash script) trades a duplicated string literal for the coupling. |
| G5 | info | Cost: +190 B raw and one extra immutably-cached request per cold load. The 129 B cleanup chunk gzips to 162 B, i.e. compression makes it larger. | **Recorded**, no change: the chunk is shared, not duplicated, and `AccountPage` imports it instead of inlining it. |
| G6 | info | The `Is shipped` row called Astro's `entryModules` a "client-script list". | **Fixed** — the row names the field. |

The mutation matrix is worth keeping: removing the body fails 4 tests; removing the `catch` fails
the refusal test; a `localStorage.clear()` implementation fails the live-keys test; never calling
`removeItem` fails the assertion added in this feature; the wrong key fails 4. And the store tests
fail both when the call is removed and when it is merely moved inside the store factory — so they
pin module evaluation specifically, which is the behaviour that matters.

**Collateral the verifier disclosed**: to guarantee a fresh build it deleted
`frontend/dist` and `frontend/.vercel/output` before rebuilding. Those directories had already
been regenerated by this feature's own `pnpm run build`, so the pre-change artifacts described in
`odd/tasks/drop-stale-build-artifacts.md` no longer exist on disk. That feature's evidence now
rests on the reconnaissance record rather than on live files; noted there.

## Tasks — all closed

- [x] Confirm the exact legacy payload shape from git history before deleting anything.
- [x] Implement the guarded removal.
- [x] Add tests: removal happens, live keys survive, idempotent, no throw without `localStorage`, no throw when storage refuses.
- [x] Run `pnpm exec tsc --noEmit`, `pnpm vitest run` and `pnpm run build`.
- [x] Update `docs/frontend-state.md`.
- [x] Work-unit commit on the feature branch (`a2d5be8`).
- [x] Independent verification — 6/7 confirmed, F4 fixed by widening the reach, F1/F2 fixed here.
- [x] Second independent verification — 7/7 on the follow-up, with the record's own "gap" refuted (G1) and the runtime proof produced.
- [x] Fast-forward into `main`, delete the branch, re-gate — `main` @ `957cb3b`, 34 files /
      394 tests passed and `tsc --noEmit` exit 0 re-run **after** the merge.
