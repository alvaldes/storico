# ODD Feature: dialog-viewport-overflow

> **Status**: fixed on `fix/dialog-viewport-overflow`, off `main` @ `54abdc7`: `305f551` (the two
> primitives) and `af01c3d` (TaskEditor). Browser acceptance probe red -> green; gates 64 files /
> 720 tests passing and `tsc --noEmit` exit 0. Not merged, not pushed.
> **Created**: 2026-10-05
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/dialog-viewport-overflow`

## Problem

The owner reported the task editor dialog looked "demasiado grande para ese ancho". It is not a width
problem, and it is not cosmetic: **in the reported state the Save button cannot be clicked at all.**

Reproduced and measured in the real browser on `/en/stories/01a10dee-6d92-7d13-812f-bc39dfd8e767`,
editing "Audit color tokens for contrast", with the browser window at 1352 x 757 CSS px:

| | Measured |
|---|---|
| Dialog height, `Invalid` ticked (the reported state, which reveals the Reason field) | **883 px** |
| Viewport height | 757 px |
| Overhang | **126 px** — 63 px clipped at the top, 63 px at the bottom |
| `max-height` on the popup | `none` |
| `overflow-y` on the popup | `visible` |
| Internal scroll | **none** — `scrollHeight === clientHeight` |
| Dialog header ("Edit Task") | off the top, `top: -63` |
| **Save Changes** | `top: 772`, `bottom: 804`, `elementFromPoint` at its centre does **not** return it |

With `Invalid` unticked the dialog measures 757.25 px in a 757 px viewport — already exactly at the
edge, so a single extra field is what breaks it.

## Root cause

`ui/dialog.tsx:53` gives the popup no ceiling and no scroll container:

```
'fixed top-1/2 left-1/2 z-50 grid w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 gap-4 …'
```

The height is content-driven. Because the popup is centred with `-translate-y-1/2`, an over-tall
dialog grows past **both** edges and the excess is clipped with no way to reach it. There is no broken
scroll: there is no scroll.

`ui/alert-dialog.tsx:48` has the identical defect.

This is a **shared-primitive** defect, not a `TaskEditor` one: measured, **20 render sites in
production code reach it** — 12 `<DialogContent>` and 8 `<AlertDialogContent>` — so
`ImportStoriesDialog` (`sm:max-w-xl`, CSV import with a report table) and `OnboardingModal` carried the
same latent bug. (A first draft of this document said 14; that was a miscount of *files* rather than of
render sites, and an independent verifier caught it.)

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Fix the primitive, not the one call site | Both `DialogContent` and `AlertDialogContent` get `max-h-[calc(100dvh-2rem)]` + `overflow-y-auto overscroll-contain`. This is one class-string edit each and it makes every dialog in the app reachable, immediately and independently of D2. |
| D2 | `dvh`, not `vh` | `100dvh` tracks the visual viewport; `100vh` on iOS Safari includes the URL-bar area, so a `100vh` ceiling still gets cut. The `-2rem` leaves 1 rem of air top and bottom. |
| D3 | `grid` becomes `flex flex-col` in the primitive | A single-column stack gains nothing from grid, and it is the display mode TaskEditor needs in order to pin its footer. `cn()` is `twMerge(clsx(...))` (`lib/utils.ts`), so a call site passing `overflow-hidden` or its own `max-h` still wins — verified before writing, because a plain Tailwind override would have been decided by stylesheet order instead, and this whole design depends on the call site being able to override. |
| D4 | TaskEditor gets a structural fix, not just a width bump | Popup `overflow-hidden` overrides the primitive's scroll (twMerge, last wins), header `shrink-0`, fields wrapped in `min-h-0 flex-1 overflow-y-auto`, footer `shrink-0`. Header and footer stay pinned and only the fields scroll, which is what a form wants. |
| D5 | No `sticky` | With the popup's `p-4` plus `DialogFooter`'s existing `-mx-4 -mb-4`, a `sticky bottom-0` sits 1 rem outside the scrollport and gets cut. The flex column achieves the pinned footer without guessing offsets. |
| D6 | Width 512 px -> 672 px (`sm:max-w-lg` -> `sm:max-w-2xl`) | Secondary, and it *also* reduces height: less wrapping in the description and the amber repetition notice. Not sufficient on its own — the measured overhang is 126 px and wider text saves roughly 60 px — which is why it travels with D4 rather than alone. |
| D7 | The idiom is already the repo's | `MobileNav.tsx:77` already passes `max-h-[calc(100dvh-var(--public-nav-h,4.25rem))]` to its `SheetContent`. This fix follows an existing convention instead of inventing one. |
| D8 | `ui/sheet.tsx` is out of scope | Measured: the sheet is already `flex flex-col` and its call site already passes a `dvh` ceiling, so it does not carry the defect. Recorded rather than expanded into. |

## Acceptance — the only check that can prove this

**jsdom has no layout engine, so a unit test of the overflow would be a lie**: it could only assert
that a class string is present. The real criterion is the browser probe, which is repeatable:

> Open the editor, tick **Invalid** through real pointer input, then assert that
> `elementFromPoint` at the centre of **Save Changes** resolves to that button.

| | Before |
|---|---|
| `saveInViewport` | **false** |
| `saveClickWouldReachIt` | **false** |
| `dialogHeight` / `viewportHeight` | 883 / 757 |

The fix must flip both to `true`. Anything that does not flip them has not fixed the report, whatever
the class strings say.

## Work units

| WU | Scope | Files |
|----|-------|-------|
| 1 | The ceiling and the scroll, in both primitives | `ui/dialog.tsx`, `ui/alert-dialog.tsx` |
| 2 | TaskEditor: width, flex column, scrollable body, pinned footer | `components/react/TaskEditor.tsx` + this document |
| 3 | The visual pass over the other long dialogs, and the evidence | `docs/frontend-state.md` (if it needs the contract), a `docs` commit with the measured after-state |

## Measured before writing the step

| What | Measured | How |
|---|---|---|
| `main` baseline | 63 files / 717 tests passing, `tsc --noEmit` exit 0 | inherited from the `blocking-page-loader` landing |
| The overflow | see the table above | browser probe, 2026-10-05 |
| Primitive reach | **20 render sites** in production code: 12 `<DialogContent>` + 8 `<AlertDialogContent>` | `grep -rn "<DialogContent" src \| wc -l` (13, minus the one in this branch's new test) and the same for `AlertDialogContent` (9 minus 1) |
| No call site depends on grid | 0 call sites pass `grid`, `flex`, `grid-cols-*`, `col-span-*`, `row-span-*` or `col-start-*` to a popup | `grep -rn "<DialogContent\|<AlertDialogContent" -A1 \| grep -iE "grid\|flex\|col-span\|row-span\|col-start"` → no hits |
| `AlertDialogMedia` (the only `row-span-2` in the primitives) is unused | 0 hits outside `ui/alert-dialog.tsx` | `grep -rn "AlertDialogMedia" src` |
| `cn()` resolves conflicts last-wins | `twMerge(clsx(...))` | `frontend/src/lib/utils.ts` |
| `TaskEditor` is used in exactly one place | `StoryDetail.tsx:816` | `grep` — which is why D4 is a structural change and not a route extraction |
| Other dialogs with their own overflow | `command.tsx:49` passes `overflow-hidden` (twMerge wins); `icon-picker.tsx:266` has its own `max-h-72 overflow-y-auto` inner region | read |

## Non-goals

- No new route. `TaskEditor` depends on state that lives in `StoryDetail` (`displayedVersionFrozen`,
  the sibling tasks for dependencies, and `onInvalidationChange`, which updates the story's
  `markedTaskIds`), so a route means re-deriving or relocating that state and reworking a cross-island
  update. That is a separate feature, not this fix.
- No redesign of the fields, and no change to the write contract or the mark flow.
- No fix in `ui/sheet.tsx` (D8).

## Tasks — all closed

- [x] **WU1** — ceiling + scroll in `ui/dialog.tsx:53` and `ui/alert-dialog.tsx:48`, `grid` ->
      `flex flex-col` in both; contract test in `ui/__tests__/dialog.test.tsx`. Commit `305f551`.
- [x] **WU2** — TaskEditor: `sm:max-w-2xl`, flex column, `shrink-0` header and footer, fields plus the
      save-error banner in the single scroll region. Commit `af01c3d`.
- [x] **WU3** — browser probe green, visual pass over the reachable dialogs, gates.
- [x] **WU4** — this document and the contract in `docs/frontend-state.md`.

## Verification

### The acceptance probe, before and after

Measured with the real editor on `/en/stories/01a10dee-6d92-7d13-812f-bc39dfd8e767`, editing "Audit
color tokens for contrast", at a 1352 x 757 viewport, with **Invalid** ticked through real pointer
input:

| | Before | After |
|---|---|---|
| Dialog rect | `top -63`, `bottom 820`, height **883**, width 512 | `top 16`, `bottom 741`, height **725**, width **672** |
| Fits the viewport | no | **yes** |
| `max-height` on the popup | `none` | `725px` |
| `overflow-y` on the popup | `visible` | **`hidden`** — the call site's override wins, measured in the browser and not only in a class assertion |
| Header visible | no | **yes** |
| Footer visible | no | **yes** |
| Scroll region | does not exist | `clientHeight 568` / `scrollHeight 600` |
| **Save Changes** | `top 772`, `inViewport false`, `elementFromPoint` missed it | `top 693`, **`clickWouldReachIt true`** |

Scrolling the fields region to its end gives `scrollTop 31.5`, brings the Reason textarea **fully into
view**, and leaves `footerBottom` at **741** — the footer is genuinely pinned and only the fields move.

`725 = 757 - 32` is the `-2rem` ceiling, and a centred 725 in 757 gives exactly `top 16` / `bottom 741`.

### The visual pass

| Dialog | Height | Fits | Popup scrolls | Unreachable controls | Verdict |
|---|---|---|---|---|---|
| `TaskEditor` (with Reason) | 725 | yes | no — fields region scrolls | 0 | fixed, see above |
| `ProjectForm` | 467 | yes | no | 0 | unaffected |
| `IconPicker` (nested in `ProjectForm`) | 431 | yes | **no** | 0 | no double scrollbar: the popup stays under the ceiling and the inner icon list keeps its own `max-h-72 overflow-y-auto` (`clientHeight 288` / `scrollHeight 741`) as the only scroller |
| `ImportStoriesDialog` | 269 empty, **601** with a real 40-error report | yes | no | 0 | unaffected; the error list scrolls inside its own bounded box and the footer stays reachable |
| `DeleteAccountDialog` | — | — | — | — | **not exercised** |
| `OnboardingModal` | — | — | — | — | **not exercised** |
| `CommandDialog` | — | — | — | — | **unused** — 0 hits outside `ui/command.tsx`, so its risk is moot; it would be safe anyway, since it passes `overflow-hidden` and the override is verified working |

The `ImportStoriesDialog` report was produced for real: a 41-line CSV of unparsable lines was uploaded
and submitted, which fails validation and writes nothing.

Two dialogs could not be reached: `OnboardingModal` only opens on a first login, and `/en/account`
rendered only its heading in this session (`mainLen: 22`, no `Delete Account` trigger appeared), so
`DeleteAccountDialog` never mounted. That is a **coverage gap, not a risk**: the ceiling applies to every
popup by construction, and the page's missing content is unrelated to this change — none of the three
files touched are on `AccountPage`'s render path for the page body, since the dialog is rendered at the
end of its tree. Recorded rather than diagnosed, because diagnosing it is a separate job.

Note on the metric: an earlier version of this probe counted *controls outside the viewport* and
reported 46 clipped controls in `IconPicker`. That was a false positive — it counted icon buttons
positioned inside a scrollable region, which is what a scroll region looks like by design. The metric
was corrected to "outside the viewport **and** with no scrollable ancestor inside the dialog", and the
numbers above are the corrected ones.

### Gates

| Check | Command | Result |
|---|---|---|
| Full suite | `cd frontend && pnpm vitest run` | **64 files, 720 tests passing** (baseline 63 / 717; the 3 new tests are the primitive contract) |
| Types | `cd frontend && pnpm exec tsc --noEmit` | **exit 0** |
| Production build | `make test-frontend` | **exit 0** |
| Arbitrary value emitted in the production CSS | see below | confirmed |

That last row was a real production-only risk worth checking, because Tailwind arbitrary values can be
emitted in dev and missed by the build. `dist/client/_astro/globals.CX6g8ra1.css` contains
`max-h-\(calc\(100dvh-2rem\)\){max-height:calc(100dvh - 2rem)}` and
`overscroll-contain{overscroll-behavior:contain}`. (The first `grep` for this reported zero hits; the
miss was the escaping of `(` in the pattern, not a missing rule — recorded because a false alarm that
looks like a production break is worth documenting.)

### Independent verification

One read-only pass by `gentle-ai-verify` over `54abdc7..af01c3d`. All eight claims confirmed except the
scope check, plus three findings:

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| V1 | Med | `git status --short` was not clean — this plan document was untracked and so was absent from the branch. | **Fixed** by WU4, which is this commit. A process gap, not a code defect. |
| V2 | Low | This document said "14 call sites"; the measured number is **20 render sites** (12 + 8). | **Fixed** above. The grid-safety conclusion is unaffected. |
| V3 | Info | The built CSS predates the commits (it is a working-tree build), so it evidences that the utility is emitted but not that it was emitted from `af01c3d`. | **Recorded.** No file changed between the build and the commits except nothing — the build ran on this working tree, and the only later change is this document. |

The verifier independently reproduced the `twMerge` dependency the hard way: with plain `clsx`
instead of `twMerge` in a scratch copy, the override test fails. It also confirmed that deleting any one
of the three classes makes a test fail, and that making `DialogContent` return `null` fails two of them —
so the tests cannot pass while the component stops rendering. It could not re-run the browser probe
(told not to start a browser), so the after-state numbers are orchestrator-measured and arithmetically
cross-checked, not independently re-measured.

## Not done, and on purpose

- No native review: receipt-driven development is off in this clone.
- Not merged and not pushed. Those are the owner's calls.
- No route extraction for the task editor: it depends on state that lives in `StoryDetail`, so that is a
  separate feature rather than part of this fix.
- `ui/sheet.tsx` untouched: it does not carry the defect (D8).
