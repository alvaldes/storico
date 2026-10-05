# ODD Feature: blocking-page-loader

> **Status**: implementation and verification complete on `feat/blocking-page-loader`, off `main` @
> `72b9013`. Four work-unit commits, no native review (receipt-driven development is off in this
> clone).
> **Created**: 2026-10-05
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/blocking-page-loader`

## Problem

The owner's report, verbatim:

> Quiero agregar un loader para la pagina completa porque hay momentos en que siento que se demora
> la llamada y que no muestra nada que indique que esta cargando. Por ejemplo cuando le doy a
> invalida a una tarea se cierra el modal pero no se muestra nada y la llamada que hace el cambio
> se demora.

Two separate facts, and both are real:

1. **There is no global loading surface.** Every island carries its own local flag — `Dashboard`,
   `KanbanBoard`, `ExportPanel`, `LLMConfigEditor` each have an `initialLoading`/`loading`, and
   buttons grow a small in-place `Loader2` (`TaskEditor.tsx:566`, `StoryDetail.tsx:774`). Nothing
   in the app says "the whole page is busy".
2. **In the invalidation case the signal exists but is nearly invisible.** In
   `TaskEditor.tsx:301-302`, `performSave` runs `setConfirmAction(null)` — which closes the
   confirmation `AlertDialog` immediately — and only then `setSaving(true)`. What the user
   perceives is a modal closing with a spinner stranded in a corner button of the dialog
   underneath. That is exactly the "se cierra el modal pero no se muestra nada" in the report.

The overlay is therefore built once, globally, and driven automatically: per-action opt-in would
have left the next slow call site with the same hole.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Trigger | **Automatic, by HTTP method, with an explicit exception list.** The owner chose this over per-action opt-in. Any `POST`/`PUT`/`PATCH`/`DELETE` through `ApiClient` blocks the page unless its path is on the exception list. Reads (`GET`) never block — which is what keeps the 2 s `pollExtraction` cadence and every background refresh out of the overlay without needing an entry each. |
| D2 | Coverage | **Full viewport, blocking.** The owner chose this. The overlay covers the sidebar, the header and any open dialog, and swallows clicks. |
| D3 | Anti-flicker | **Show after `BLOCKING_LOADER_DELAY_MS` (250 ms) with the request still in flight; once shown, stay shown until `BLOCKING_LOADER_MIN_VISIBLE_MS` (400 ms) have elapsed *since the veil appeared*, and only then hide as soon as the last request ends.** Without this, D1 makes the app unusable: a Kanban drag fires a `PUT` that answers in ~100 ms and the whole screen would blink on every card move. With it, only a call that is genuinely slow gets the overlay — which is precisely the owner's complaint ("la llamada ... se demora"). This is why the trigger can be automatic at all. |
| D3b | What the minimum is measured from | **Appearance, not completion** — and the independent verification is what settled this (F1 below). The floor exists to stop a *short* request from blinking; it must never hold the veil open 400 ms past a request the user already watched run for ten seconds. So the hide delay is `max(0, MIN_VISIBLE - (now - visibleSince))`, which is 0 for any request that outlived the window. `odd/tasks` D3 as first written said "after the last request ends", which describes the opposite; the code was right and the sentence was wrong. |
| D4 | Where the accounting lives | A module-level counter in `stores/loadingStore.ts`, **not** component state. The counter outlives the island, so a mutation in flight when a route navigation unmounts and remounts `DashboardShell` keeps its overlay instead of dropping it. |
| D5 | z-index | `z-[60]`: above the shadcn dialogs (`z-50`, `Dialog`/`AlertDialog`), below sonner (`z-index: 999999999` in `sonner/dist/styles.css:50`). A success toast fired as the request settles must stay readable above the overlay. |
| D6 | Exception list | Exactly three, each carrying its reason in code: the automatic first-login onboarding `PATCH`, the automatic LLM model probe `POST`, and the extraction-start `POST`. Rationale per entry in `lib/blocking-requests.ts`. |
| D7 | Copy | One generic label, not one per operation: several mutations can be in flight at once, and naming one of them would be a lie. `common.processing` → `Processing...` / `Procesando...`. Impersonal gerund, so it satisfies the neutral-Spanish rule (`neutral-spanish.test.ts`). |

## Non-goals

- No change to any store's existing `loading`/`saving` flags. Those stay; this is an additional,
  coarser signal, not a replacement.
- No change to `lib/status-health-api.ts` or the public pages. Neither imports `ApiClient`; the
  public surfaces have no slow mutations.
- No progress percentage, no cancel button, no request timeout.

## Work units

| WU | Scope | Files |
|----|-------|-------|
| 1 | The decision: which requests block | `lib/blocking-requests.ts` + its test |
| 2 | The accounting: delay, minimum visibility, nested counter | `stores/loadingStore.ts` + its test |
| 3 | The wiring and the surface: `ApiClient`, the overlay, its mount, the copy | `lib/api.ts`, `lib/__tests__/api-blocking-requests.test.ts`, `components/react/FullPageLoader.tsx` + its test, `components/react/DashboardShell.tsx`, `i18n/en.json`, `i18n/es.json` |
| 4 | The contract, written down | `docs/frontend-state.md`, this document |

## Measured before writing the step

| What | Measured | How |
|---|---|---|
| Frontend suite baseline | **58 files, 685 tests, all passing** (12.1 s) | `pnpm vitest run` on `72b9013` |
| No global loading surface exists | `grep -rn "loading" src/components/ui/` → 0 hits; no overlay/portal component in `components/ui/` or `components/react/` | `ls src/components/ui` |
| Dialogs sit at `z-50`, sonner far above | `sonner/dist/styles.css:50` → `z-index: 999999999` | read |
| Mutating call sites through `ApiClient` | 25, all in `frontend/src/lib/*-api.ts` and 3 stores | `grep -rn "api\.\(post\|put\|patch\|delete\)\|postForm"` |
| Automatic non-user writes that must not block | onboarding `PATCH`, LLM model probe `POST` | `lib/user-api.ts:50`, `lib/llm-config-api.ts:44`, fired by `OnboardingModal` and `LLMConfigEditor:367-378` |
| Background reads that must not block | `pollExtraction` every 2 s, `fetchTasksForWorkspace`, breadcrumb resolves | `taskStore.ts`, `AutoBreadcrumb.tsx` |
| `ApiClient` is never imported server-side | 0 hits for `from '@/lib/api'` under `src/pages/` | `grep` |

## Verified in a real browser

Run on 2026-10-05 against the live dev stack (Astro dev on `:4321`, backend on `:8000`, both
answering `200`), in a logged-in session, with the `ego-browser` Chromium and its Node driver. The
screenshots live only in the session (`/tmp/blocking-loader-overlay.png`,
`/tmp/blocking-loader-real-request.png`); what is recorded here is the command and the raw output,
which is the part that has to survive.

### The veil, its coverage and its release

The overlay was raised on `/en/dashboard` by importing the app's own module and hit-tested with
`elementFromPoint` at the four corners and the centre:

```
ego-browser nodejs -e '… page.evaluate(async () => {
  const mod = await import("/src/stores/loadingStore.ts"); mod.beginBlockingRequest(); … })'

PROBE { before: 0, at100: 0, at550: 1, viewport: { w: 1352, h: 757 },
        hasOverlay: true, text: "Processing...", ariaLive: "polite",
        cls: "fixed inset-0 z-[60] flex items-center justify-center bg-background/70 backdrop-blur-sm",
        hitTests: { topLeft_overSidebar: true, leftEdge_overSidebar: true, header: true,
                    center_overContent: true, bottomRight_overContent: true } }
TEARDOWN {"at50":1,"at700":0}
```

`at100: 0` / `at550: 1` is the 250 ms delay holding in a real browser. `at50: 1` after
`endBlockingRequest()` is the 400 ms floor holding. All five hit tests true is the blocking claim:
the browser's own hit testing resolves to the overlay, not to what is underneath, over the sidebar,
the header and the content.

### The whole chain, from a real HTTP request

A real `POST` through the app's `ApiClient` to a path that does not exist — a 404 writes nothing —
with 1500 ms of latency injected at the protocol level:

```
page.cdp("Network.emulateNetworkConditions", { offline: false, latency: 1500, … })

SLOW-E2E { pendingDuringPost: 1, overlayAt120ms: false, overlayAt620ms: true,
           overlayZ: "60", overlayPosition: "fixed", overlayCoversViewport: true,
           overlayPointerEvents: "auto", text: "Processing...",
           topmostTopLeftIsOverlay: true, postOutcome: "ERR:404",
           pendingAfterPost: 0, overlayAfterSettle: false }
```

Three things this pins that unit tests cannot. `overlayAt120ms: false` — the delay survives a real
request. `topmostTopLeftIsOverlay: true` — the veil is above the sidebar at the hit-test level.
And `ERR:404` with `pendingAfterPost: 0, overlayAfterSettle: false` — an error response releases the
counter and brings the veil down, which is the one failure mode that would have been catastrophic
here (an overlay that never comes down).

Without latency the same probe returns `pendingDuringGet: 0, pendingAfterGet: 0,
overlayAfterGet: false` and `pendingDuringPost: 1` — a real `GET` never touches the counter, a real
`POST` always does.

### `z-[60]` versus the dialogs

`overlayZ: "60"` in the browser. The overlay's whole ancestor chain was walked for stacking-context
triggers and has none — `div.group/sidebar-wrapper`, `astro-island`, `body` and `html` are all
`position: static`, `z-index: auto`, `transform: none`, `opacity: 1`, `isolation: auto`,
`contain: none`, `will-change: auto`. So the `60` competes in the root stacking context against the
dialogs' `z-50` (`ui/dialog.tsx:31,53`, `ui/alert-dialog.tsx:26,48`, `ui/sheet.tsx:31,56`).

**Limitation, stated plainly**: no dialog was open during the hit test. The dev database is empty by
D-a-3, so no page exposed a reachable dialog trigger, and D5 rests on the two halves above rather
than on a single observation of one over the other.

### Why the top-level decision is safe

`D1` was the risky half: if an island bundled its own copy of `loadingStore`, the writer and the
overlay would be different objects and the veil would never paint. Two independent checks:

- The production build (`make test-frontend`, exit 0) puts the exclusion reasons' literal in exactly
  one chunk — `grep -l "Extraction start answers 202 immediately" .vercel/output/static/_astro/*.js`
  → `api.Dy8D0NNO.js`, one hit. Rollup assigns a module to exactly one chunk, so there is one copy.
- The browser run above raised the veil through a dynamic import of `/src/stores/loadingStore.ts` and
  the overlay that appeared is the one `DashboardShell` mounted. Two instances would have produced
  nothing.

## Independent verification

Two read-only passes by `gentle-ai-verify`, neither of which edited repository files. The first
returned 8 claims (6 confirmed, 1 partially refuted) and six findings; the second re-checked the
delta and returned 6 claims (4 confirmed, 2 refuted) and five findings. Every refutation is recorded
below, including the two that were about this document rather than the code.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| F1 | Med | `loadingStore.ts:99` measures the minimum from `visibleSince`, not from the last request end, so a request that outlives the window hides with 0 ms of extra wait. **The code is right and D3's wording was wrong** ("after the last request ends" describes the opposite). The suite also only reached the degenerate branch. | **Fixed.** D3 rewritten, D3b added, the misleading test name replaced, and the negative-`remaining` branch given its own test. Then verification #2 refuted the *new* test's own claim — see V1a. |
| F2 | Low | Exclusion #1 is documented as a `POST` but the real call site (`lib/user-api.ts:50`) is a `PATCH`. The regex is path-only, so behaviour was correct; a method-aware rewrite would have silently dropped it. | **Fixed.** The test now drives the real `PATCH` and keeps `POST`, pinning that the exclusion is path-scoped rather than verb-scoped. |
| F3 | Low | Two pairs of defensive guards are mutually redundant — removing either one alone leaves every test green (`loadingStore.ts:72` vs `:93`, and `:104` vs `:66`). | **Recorded, no change.** Both are early-returns that make the invariant local instead of relying on a distant caller; they cost nothing and nothing here depends on them being observable. |
| F4 | Low | No test covered a *rejected* `fetch` — a different path from an error `Response`, and the one a dropped connection takes. | **Fixed.** New test, and verification #2 proved it fails when the `finally` is removed. |
| F5 | Low | D2 (full-viewport, swallows clicks) and D5 (`z-[60]`) had no test — static reading only. | **Closed by the browser run** above, with the D5 limitation recorded. |
| F6 | Low | That one shared module instance survives island remounts was argued, not build-verified. | **Closed** by the two checks in "Why the top-level decision is safe". |
| V1a | Med | **Refuted a claim this document made.** The new negative-`remaining` test does NOT pin the `Math.max(0, remaining)` clamp: `setTimeout` already normalizes a negative delay to 0, so deleting the clamp keeps it green. The comment claiming otherwise was false. | **Fixed.** The comment now says what the test actually pins (the outcome: hidden after one flush) and states that the clamp is intent, not behaviour. |
| V1b | Low | The delta handed to verification #2 omitted `docs/frontend-state.md`, which had been written 3 minutes before that run. | **Owned.** The delta list was wrong, not the repository: the doc was written after the delta was described. Recorded so the omission is not mistaken for an unexplained write. |
| D1 | Low | `docs/frontend-state.md` claimed a browser measurement dated 2026-10-01 with no artifact anywhere in the repo — and the date was wrong: the branch was created 2026-10-05. | **Fixed.** The date is corrected and the raw commands and outputs are recorded in this document, which is now the artifact. |
| D2 | Low | D3b referenced "(F1 below)" when no findings section existed. | **Fixed** — this table is that section. |
| D3 | Low | The header said `Created: 2026-10-01`. | **Fixed** — the real date, 2026-10-05. |
| D4 | Low | The new test's comment claimed to pin the clamp. | **Fixed** — same edit as V1a. |

## Gates

| Check | Command | Result |
|---|---|---|
| Full frontend suite (before the two review fixes) | `cd frontend && pnpm vitest run` | **63 files, 715 tests, all passing** |
| Full frontend suite (final) | `cd frontend && pnpm vitest run` | **63 files, 717 tests, all passing** |
| Types | `cd frontend && pnpm exec tsc --noEmit` | **exit 0, no output** |
| Neutral Spanish guard | `pnpm vitest run src/i18n/__tests__/neutral-spanish.test.ts` | **3 tests passing** |
| Production build | `make test-frontend` (`astro build` + `@astrojs/vercel`) | **exit 0** — run before the two review fixes, which touch only test files and so cannot affect a build |
| Baseline before any change | `pnpm vitest run` on `72b9013` | 58 files, 685 tests |

## Tasks — all closed

- [x] **WU1** — `lib/blocking-requests.ts` + `lib/__tests__/blocking-requests.test.ts` (11 tests).
- [x] **WU2** — `stores/loadingStore.ts` + `stores/__tests__/loadingStore.test.ts` (8 tests).
- [x] **WU3** — `lib/api.ts` wiring, `FullPageLoader.tsx`, the `DashboardShell` mount, `common.processing`
      in both locales, plus `api-blocking-requests` (8 tests), `FullPageLoader` (4), `DashboardShell` (2).
- [x] **WU4** — gates green, `docs/frontend-state.md` extended, this document closed.
- [x] Browser verification with raw evidence recorded above.
- [x] Two independent verification passes; every finding dispositioned.

## Not done, and on purpose

- No native review: receipt-driven development is off in this clone, so no review was started. The
  owner decides delivery.
- Nothing was pushed and no pull request was opened: commit, push, PR and merge are the owner's calls.
- `taskStore`'s `updatingTaskId` and the per-component `loading`/`saving` flags were left alone. They
  are finer-grained signals that this overlay complements rather than replaces.

