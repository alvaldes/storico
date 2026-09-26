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
- [ ] **T7 — Storico: document the variable.** **BLOCKED, not skipped.** The Gentle AI safety
  policy refuses writes to any `.env*` path — for the bounded writer *and* for this parent
  session (`Gentle AI safety policy blocked access to sensitive path: …/.env.example`). Routing
  around it with `bash` would defeat a deliberate control, so it is the operator's edit. Paste
  this into the root `.env.example`, at the end of the `## ── Frontend (Astro — no prefix) ──`
  section, and mirror it in `frontend/.env.example`:

  ```
  ## Live-demo embed URL — the landing hero iframes the demo at this base
  ## (`<base>/en/`, `<base>/es/`). Unset means the demo's own dev server.
  ## The PUBLIC_ prefix is deliberate and is the one exception to this section's
  ## "no prefix" rule: the value is rendered into the page, so the name has to
  ## guarantee it is safe to expose. It is not a secret and never carries one.
  PUBLIC_DEMO_URL=http://localhost:4322
  ```

  Nothing breaks without it: `config.demoUrl` falls back to `DEFAULT_DEMO_BASE`, which is the same
  value. The cost of leaving it undocumented is that nobody learns the knob exists at deploy time.
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

## Recorded debt (decided, not discovered late)

1. **The typing story is clipped on mobile.** At the 420px mobile height the embedded demo shows its
   header, its own `h1` and the metadata row, and the `FULL USER STORY` card — the thing that types —
   falls below the frame's bottom edge. The operator chose to ship it and record it rather than fix
   it in this branch. The fix that was measured and rejected is: hide the demo's own page framing
   when `data-embedded` (inside the hero it repeats what the landing already said) and raise the
   mobile height. The demo's `main` scrolls, so the content is reachable, just not first-paint.
2. **The landing's theme and the demo's theme do not agree.** Photographed: dark landing, light
   demo. `localStorage['theme']` is per-origin, so the contract recorded on 2026-09-26 holds only
   when the two share an origin. Deferred with D1: it disappears if the "dónde" decision in
   `~/Documents/second-brain/01 - Projects/Storico Live Demo/Notas/Cuándo el demo necesita un
   despliegue.md` lands on a same-origin `/demo`. The alternative that was considered and deferred
   is passing the resolved theme as `?theme=` on the iframe src.
3. **The Astro dev toolbar renders inside the iframe** in development, because the demo's own dev
   server injects it. It is not in the built output and is not part of this change.
4. **Pre-existing demo defect, out of scope:** at 390px the story metadata row wraps
   ("Creada 25 de septiembre de 2026" over four lines). Reproduced on the standalone demo page, so
   it is not caused by the embed.

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

## Out of scope (declared, not forgotten)

- **Deploying the demo.** D1 keeps it a separate decision. Until it happens, `PUBLIC_DEMO_URL`
  points at a local server and the production landing would embed nothing.
- **Same-origin theme sharing.** Restored only if the demo ends up under the same origin, which is
  the open "dónde" from the vault note.
- **The phone mockup** stays exactly as it is; the brief was to add below the hero, not to replace it.
