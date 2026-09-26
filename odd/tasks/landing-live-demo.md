# ODD Feature: put the live demo in the landing hero

> **Created**: 2026-09-26
> **Workflow**: Organic Driven Development (ODD)
> **Branches**: `storico` @ `feat/landing-live-demo` (off `main` @ `b1ed1bb`),
> `storico-live-demo` @ `feat/landing-embed-bridge` (off `main` @ `9c6ee4f`).
> **Receipt-driven development**: off in this clone (unchanged since the last record read here).

## Problem

The landing advertises a demo it does not have. `landing.hero.cta_secondary` is the string
"View Demo" / "Ver demo", and `frontend/src/pages/[locale]/index.astro:80` sends it to `/login`.
The vault note *"Cuándo el demo necesita un despliegue"* recorded the intended fix as a one-line
`href` change, **sin `iframe` ni isla en la landing**.

That note is now superseded by its own successor: `storico-live-demo` grew a `SafariFrame.astro`
whose default URL label is `storico.vercel.app/demo` and a `LOOP_ANIMATION_BEHAVIOR.md` whose
"Integration Checklist for Landing Page" assumes an iframe. The operator decided on 2026-09-26:
**the SafariFrame wins, and the demo goes inside the hero, below what the hero already has.**

## Decisions taken by the operator (not derived here)

| # | Decision | Consequence |
| --- | --- | --- |
| D1 | The iframe `src` comes from `PUBLIC_DEMO_URL`, defaulting to `http://localhost:4322`. | Nothing is blocked on a deploy. The deploy stays a separate decision and a separate commit. |
| D2 | `cta_secondary` points at the in-hero anchor `#demo`. | The broken `/login` href is fixed without inventing a page that does not exist yet. |
| D3 | The demo block renders on mobile too, with reduced height. | The hero stays usable on a phone without hiding the product. |
| D4 | The cross-origin `blur`/`focus` forwarding is solved now, in **both** repositories. | `storico-live-demo` needs a `message` receiver; the landing needs a sender. |
| D5 | No new i18n keys. The demo block is labelled by the iframe `title` alone. | `en.json`/`es.json` parity is untouched; the copy comes from existing keys. |
| D6 | The uncommitted `prod.todo.md` change goes to `git stash`, not into this work. | `stash@{0}` holds it; the branch starts from a clean tree. |

## Technical constraints found while exploring

- **The demo already frames itself.** `src/layouts/DemoLayout.astro:59` wraps the whole app shell
  in `<SafariFrame url="storico.vercel.app/demo" height="70vh">`. The landing must not draw a second
  frame: an iframe of the demo page brings the chrome with it.
- **`SafariFrame` sizes itself twice and they disagree.** The outer `<div class="safari-frame h-175">`
  is a fixed 700 px while `.safari-content` gets `height: ${height}` (70vh) from the prop. A host that
  wants to control the height from outside has only one of those two knobs. Task 2 fixes that.
- **The loop only listens to its own window.** `src/scripts/demo.ts:223` registers `blur` on the
  demo's `window`. Inside a cross-origin iframe, a parent cannot dispatch that event — the only
  channel is `postMessage`. The receiver must not trust an origin allowlist either, because Vercel
  preview URLs are random per deployment: validate the **message shape**, not the sender, and accept
  exactly one command (`leave`), whose worst case is a cosmetic animation restart.
- **`localStorage['theme']` does not cross origins.** The theme contract between landing and demo,
  recorded on 2026-09-26, silently does not hold while the demo is served from another origin. This
  is accepted with D1, and it is the reason the deploy decision is still open.
- **No CSP or `frame-ancestors` header exists** anywhere in the frontend (`grep` over `src`,
  `astro.config.mjs`, `docs/`), so nothing blocks embedding. Correspondingly, `sandbox` must **not**
  be set on the iframe: without `allow-same-origin` the demo's `localStorage` bootstrap throws.
- **`PublicNavbar` is static** (`<header class="border-b …" data-public-nav>`, no `sticky`/`fixed`),
  so `#demo` needs no large `scroll-margin-top`.
- **`ClientRouter` is active** (`PublicLayout.astro:87`), so any inline script wiring the sender has
  to survive view transitions rather than assume a fresh document per navigation.
- **Test infrastructure is `.tsx` and JSON only.** `vitest.config.ts` runs jsdom over `src/lib/*` and
  `src/components/react/*`; no `.astro` page is imported by any test. So the URL resolution has to
  live in a plain TS helper under `src/lib/` to be testable at all — that is the repo's own pattern
  (`src/lib/proxy-url.ts`, `src/lib/theme.ts`, each with a mirror test in `src/lib/__tests__/`).

## Tasks

Checked only when the outcome was observed, not when the edit was made.

- [x] **T10 — Zoom the embedded demo on small screens.** Follow-up the operator asked for after
  the first close: fix the mobile clipping with a zoom on the iframe, changing no crop and **not
  touching `storico-live-demo` again**. *Surface:* `frontend/src/pages/[locale]/index.astro`

- [x] **T1 — Demo: the bridge receiver.** `message` listener in `src/scripts/demo.ts` that treats a
  validated `storico:demo-leave` signal as the `blur` it replaces. Document the protocol in
  `LOOP_ANIMATION_BEHAVIOR.md` and tick the checklist items it owns.
  *Landed as:* `initEmbedMessaging()` + `resumeLoop`, `onBlur` renamed `onLeave`; the receiver is
  module-level so it degrades to a no-op when no loop exists (missing `[data-story-text]` or
  `prefers-reduced-motion`, where `initTyping()` returns before assigning `resumeLoop`).
- [x] **T2 — Demo: one height knob.** `.safari-frame` now takes its height from `--frame-height`
  (the `height` prop) and `.safari-content` is `flex-1 min-h-0`; `data-embedded` on `<html>`, set
  before paint by an inline head script, makes the frame fill the iframe viewport and drops the
  standalone body padding. Measured: the standalone page renders a 591px frame at `70vh` of an
  844px viewport, and one frame only.
- [x] **T3 — Storico: URL helper, tested first.** `src/lib/demo-embed.ts` + 14 vitest cases.
- [x] **T4 — Storico: the hero block.** `flex-wrap` on the hero section, `#demo` as a `w-full`
  last child, iframe rendered server-side, `loading="lazy"`, no `sandbox`.
- [x] **T5 — Storico: repoint the CTA.** `cta_secondary` `/login` → `#demo`. Verified in the
  rendered DOM of both locales; the primary CTA and the two `PublicLayout` links still go to
  `/login`, on purpose.
- [x] **T6 — Storico: the sender.** `attachDemoLeaveForwarding()` wired from the page script.
- [x] **T7 — Storico: document the variable.** **Closed by the operator, with a different value
  than the one proposed.** The Gentle AI safety policy refuses writes to any `.env*` path — for the
  bounded writer *and* for this session — and routing around it with `bash` would defeat a
  deliberate control, so the edit was the operator's. Root `.env.example` now carries
  `PUBLIC_DEMO_URL=https://alvaldes.github.io/storico-live-demo`, which is not the default
  (`DEFAULT_DEMO_BASE = http://localhost:4322`): the example documents the deployed home, the code
  default keeps a fresh clone working against a local demo. `demoEmbedUrl` handles the subpath
  correctly — verified: the landing renders `src="https://alvaldes.github.io/storico-live-demo/en/"`
  and `data-target-origin="https://alvaldes.github.io"`, which matches, so `postMessage` still has a
  valid origin.
  **Mirror closed by the operator too:** `frontend/.env.example` now lists the same variable with
  the same value (measured: identical string in both files). That file is a reference document, so
  the entry is for discoverability — and both edits were the operator's, because the policy blocks
  `.env*` for this session.
- [x] **T8 — Verify.** See **Verification** below.
- [x] **T9 — Close.** Four work-unit commits, listed below.

## Verification

Commands run by this session, not reported second-hand.

| Check | Result |
| --- | --- |
| `pnpm vitest run src/lib/__tests__/demo-embed.test.ts` | 1 file / 14 tests passed |
| `pnpm test` (frontend, full suite) | 50 files / **567 tests passed**, zero failures |
| `pnpm build` (frontend) | `[build] Complete!` with no `PUBLIC_DEMO_URL` set, i.e. the default applied |
| `pnpm build` (demo) | passed (worker-run; this session verified the served module instead) |
| `curl :4321/en/` and `/es/` | iframe `src` is locale-correct, `data-target-origin="http://localhost:4322"`, `sandbox` absent, `href="#demo"` present |
| Hero geometry @1352px | text column `y 283..676`, phone `y 185..775`, `#demo` `y 839`, `w 1120 h 720` — **below**, not a third column |
| `#demo` anchor | `scrollY 0 → 839`, same document, no navigation |
| Demo receiver, measured in its own realm (`:4322`) | story `textContent` `147 → 0 → 28` after `postMessage({source:'storico-landing',type:'demo-leave'})` |
| Landing sender, measured by intercepting `HTMLIFrameElement.prototype.contentWindow` | exactly `{source:'storico-landing',type:'demo-leave'}` + `http://localhost:4322` on parent `blur` and on `pointerdown` outside; **no send** for `pointerdown` on the frame or a visible `visibilitychange` |
| Desktop light + dark, mobile 390px | screenshots reviewed; the frame draws once and fills the box |
| **Deployed pair** (landing → `alvaldes.github.io/storico-live-demo`) | frame flush to the iframe box on all four edges, story typing inside it, no dev toolbar in the built artifact |
| Pages rollout | run 36275721453 `build`+`deploy` success; the first `curl` after it read stale — GitHub's CDN needed a cache-buster to show `data-embedded`. A 200 is not a fresh deploy |

The landing's own `.env` also carries the Pages URL, so `pnpm dev` on 4321 now embeds the
**deployed** demo, not the local one on 4322. Editing the demo locally no longer shows up in the
landing until the variable is unset or pointed back at `:4322`.

## Recorded debt (decided, not discovered late)

1. **RESOLVED (T10) — the typing story was clipped below `lg`.** At the 420px box the embedded demo
   showed its header, its own `h1` and the metadata row, and the `FULL USER STORY` card — the thing
   that types — fell entirely below the frame's bottom edge. Measured baseline at 390px: the card
   was not visible at all.

   The fix is a zoom on the iframe, which is what the operator asked for, and it needs nothing from
   the demo. The frame is laid out at `1/zoom` of the box (`--demo-zoom: 0.72`) and scaled back into
   it with `transform: scale()`, so the nested browsing context receives a **larger** layout
   viewport while the box the visitor sees keeps its size. `transform` is the point: it does not
   affect layout, so the demo's own `100dvh` embedded frame still fills whatever box it is handed —
   which is why `storico-live-demo` did not have to be touched again.

   Measured after the change, all with the story card and its validation chips visible and
   `scrollWidth === innerWidth` (no horizontal overflow):

   | Ancho | Viewport del hijo | Caja visible | Resultado |
   | --- | --- | --- | --- |
   | 390 | 494 × 583 | 356 × 420 | tarjeta + 2 chips visibles, layout móvil del demo |
   | 640 | 842 × 583 | 608 × 420 | tarjeta visible |
   | 900 | 1158 × 583 | 836 × 420 | **layout desktop completo** del demo: sidebar, tarjeta, chips y el inicio de PARTS |
   | 1100 (`lg`) | sin transform | 1078 × 722 | intacto, la regla termina donde empieza `lg` |

   **The cost, stated plainly:** text renders at 72% of its size, so the demo reads as a preview on
   a phone rather than as a comfortable touch target. Interaction still works — hit-testing follows
   the transform — but tapping a card at 390px means tapping at 72%. That is the trade the zoom
   makes instead of cropping, and it is why the rule stops at `lg`.

   **One consequence to notice:** the box is now a uniform 420px below `lg`. The previous
   `sm:h-[520px]` step is gone, because with the zoom the child height is 583px at every sub-`lg`
   width and a taller box would only enlarge the visible area, not reveal more of the demo's
   layout. If the tablet range ever wants a taller frame, that is a second decision, not a revert.

1b. **The demo's own `h1` and description still occupy the top of the frame on phones.** The
   rejected alternative remains the better long-term fix — hiding the demo's page framing when
   `data-embedded` gives the story card the top of the box at full size — but it needs a change in
   `storico-live-demo`, which the operator explicitly excluded from this round.
2. **The landing's theme and the demo's theme do not agree — and this no longer fixes itself.**
   Photographed: dark landing, light demo. `localStorage['theme']` is per-origin, so the contract
   recorded on 2026-09-26 holds only when the two share an origin. The deferral assumed the "dónde"
   question was open; the operator answered it by deploying the demo to **GitHub Pages**
   (`alvaldes.github.io/storico-live-demo`, `build_type: workflow`, `site` + `base` set in
   `astro.config.mjs`), which is a *different* origin from `storico.vercel.app`. So the gap is now
   permanent unless something closes it deliberately: either the landing passes the resolved theme
   as `?theme=` on the iframe src and the demo's inline bootstrap honours it, or the demo moves
   under the product's origin. The first is a small change on both sides; the second is the deploy
   decision, re-opened.
3. **CERRADO POR DECISIÓN — the fake browser chrome reads `storico.vercel.app/demo` while the demo
   is served from GitHub Pages.** The operator decided it stays: it is decoration, not an address
   (`"se queda así, es puro decorativo"`). Recorded so nobody "fixes" it later on the assumption it
   was an oversight. (The modal's `storico.vercel.app/dashboard` link was always correct: it points
   at the real product.)
4. **The Astro dev toolbar renders inside the iframe** in development, because the demo's own dev
   server injects it. Confirmed absent in the deployed artifact, so it is not part of this change.
5. **Pre-existing demo defect, out of scope:** at 390px the story metadata row wraps
   ("Creada 25 de septiembre de 2026" over four lines). Reproduced on the standalone demo page, so
   it is not caused by the embed.
6. **Minor cosmetic:** the landing's iframe carries `rounded-2xl` while the embedded frame's corners
   are square in embedded mode, so a small wedge shows at the top corners. Visible in the deployed
   screenshot; not worth a change until the frame's radius is decided.

## A measurement lesson worth keeping

Three earlier attempts to observe "parent sends → child restarts" in one continuous run produced
readings that looked like a delivery failure and were not. Two causes, both mine:

- The accessibility snapshot of a cross-origin frame is a coarse, timing-blind channel: the loop's
  own 2s pause produces the same text transitions as a `demo-leave` restart, so a single sample
  cannot tell them apart. Only a **timeline** sampled faster than the pause can.
- Reading the child through the parent is blocked by design (cross-origin), and clicking into the
  frame by coordinates did not reach it. Worse, each `page.evaluate`/`snapshot` moved focus, which
  fired the child's **real** `blur` and restarted the loop — the observation was itself the
  intervention. The child's `blur` path and the message path converge on the same `onLeave`, so
  what looked like a failed test was a passing one measured through the wrong door.

The two halves were then each proven with direct instrumentation in the realm that owns them, which
is the claim this record makes. What is *not* claimed is a single unbroken observation of
parent-click → child-restart.

Two more traps the zoom round added to that list:

- **Removing an inline override does not remove a media-query rule.** The first "baseline"
  screenshot of this round was labelled `zoom-none` and was actually at 0.72: clearing the inline
  `--demo-zoom` left the stylesheet's own declaration in force, so the comparison compared 0.72 to
  0.72 and appeared to prove the clipping was already fixed by the demo's embedded mode. The real
  baseline needed `transform: none` and explicit width/height inline. `getComputedStyle` on the
  element is what caught it.
- **`getBoundingClientRect()` returns the transformed box**, so it reads 356×420 at every zoom
  factor and proves nothing about the zoom. The values that matter are the element's *layout*
  width/height (`getComputedStyle`) — that is the child's viewport.
- **With the Vercel adapter, `dist/` holds only `client`.** A page's scoped `<style>` is inlined
  into the server chunk, so grepping `dist/` for a rule that renders fine in dev returns zero and
  looks like a dropped stylesheet. The place to look is `.vercel/output/…/pages/[locale]/index.astro`
  — where `demo-zoom` was, all along.

## Out of scope (declared, not forgotten)

- **Deploying the demo.** D1 keeps it a separate decision. Until it happens, `PUBLIC_DEMO_URL`
  points at a local server and the production landing would embed nothing.
- **Same-origin theme sharing.** Restored only if the demo ends up under the same origin, which is
  the open "dónde" from the vault note.
- **The phone mockup** stays exactly as it is; the brief was to add below the hero, not to replace it.
