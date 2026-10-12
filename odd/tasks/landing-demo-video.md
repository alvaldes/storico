# ODD Feature: landing demo video

> **Status**: closing. Two commits on `main`, no tag.
> **Created**: 2026-10-12
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

The landing showed the product two ways: the hero copy and a live embedded demo
(`#demo`, served from `PUBLIC_DEMO_URL`). The owner has a demo video on YouTube and asked for a
section for it, using `justinribeiro/lite-youtube` rather than a bare iframe.

## Decisions taken by the operator (not derived here)

| # | Decision | Consequence |
| --- | --- | --- |
| D1 | Placement: **after** the features band, before the FAQ. | This reversed the first implementation, which had put the section between the hero and the features band. |
| D2 | Content: title, description, video and a call to action. | Six new `landing.video.*` keys in both catalogs. |

## Decisions taken while implementing

| # | Decision | Choice |
| --- | --- | --- |
| D3 | Package | `@justinribeiro/lite-youtube@1.9.0`, the repo the owner named. Not `lite-youtube-embed` (Paul Irish's variant), which needs a separate CSS import. MIT, Shadow DOM, no CSS file, zero transitive dependencies. |
| D4 | CTA weight | The section's call to action is the secondary (ghost) treatment, not a copy of the hero's gradient button. `landing-cta` D1 settled that the hero's button is *the* action on the page, and a second one at the same weight dilutes it. The destination is the same (`/login`, or `/dashboard` with a session). |
| D5 | i18n split | `videotitle` is the video's real YouTube title and stays in English: it is the same recording in both locales. Only `playlabel` is translated, which is the half the component uses as the verb in front of it. |
| D6 | Video identity | The id and the title are constants in `index.astro`, not an environment variable like `PUBLIC_DEMO_URL`: this is content, and it does not differ between dev and production. |
| D7 | Frame | One frame per embed. The section draws the border and radius, and `--lite-youtube-frame-shadow-visible: no` turns off the 60px gradient the component paints across the top of the poster, which otherwise reads as a second frame. |

## Technical constraints found while exploring

- **`customElements.define` is unguarded upstream.** `@justinribeiro/lite-youtube` defines
  `lite-youtube` at module scope with no `customElements.get` check, so a second evaluation throws
  `NotSupportedError` and aborts the rest of that script. The wrapper imports it behind the guard.
- **`params` must be passed explicitly.** The component's getter interpolates
  `getAttribute('params')` into the query it builds, so with no attribute the embed src would end
  `&null`. The wrapper defaults it to `rel=0`.
- **The default poster is too small for the box.** `hqdefault` is 480x360 and the landing hands the
  component a box about 1120px wide, so the default is upscaled roughly 2.3x and reads soft even on
  a 1x display. `maxresdefault` is 1280x720 and 29KB for this video, the largest poster YouTube
  publishes for it, and the component drops back to `hqdefault` on its own when the requested
  quality does not exist.
- **The poster is `loading="lazy"`,** which matters twice: nothing is requested until the box nears
  the viewport, and after the section moved below the features band a browser check that waits for
  the poster without scrolling first times out. That timeout is the lazy behaviour working.
- **No CSP and no `frame-ancestors` anywhere in the frontend,** so nothing blocks the embed.

## Tasks

Checked only when the outcome was observed, not when the edit was made.

- [x] **T1 — Dependency.** `pnpm add @justinribeiro/lite-youtube` under the version pinned in
  `package.json` (`pnpm@10.15.0`), so the lockfile keeps its format. The lock diff is 8 insertions
  for one leaf package with no transitive dependencies.
- [x] **T2 — Wrapper.** `frontend/src/components/astro/LiteYouTube.astro`, which owns the
  third-party element's contract: the guarded import, the attribute names, the poster quality, the
  frame-shadow switch, and the light-DOM anchor that stands in when the element never upgrades.
- [x] **T3 — Copy.** Six `landing.video.*` keys in `en.json` and `es.json`, in neutral Spanish.
- [x] **T4 — The section.** In `frontend/src/pages/[locale]/index.astro`, with the pill, the
  heading, the framed embed and the secondary CTA.
- [x] **T5 — Reorder.** The owner moved the section from between the hero and the features band to
  between the features band and the FAQ. One comment word changed with it.
- [x] **T6 — Docs.** `docs/i18n.md` lists the `landing` group's sections and did not include the new
  one. It now reads `Hero, video, features, FAQ, CTA`.
- [x] **T7 — Verify.** See below.
- [x] **T8 — Close.** Two work-unit commits, listed under Status.

## Verification

Commands run by this session, not reported second-hand.

| Check | Result |
| --- | --- |
| `pnpm run lint` | 0 errors, 4 pre-existing warnings in files this change does not touch |
| `pnpm vitest run` | 81 files, 953 tests passed |
| `pnpm build`, before and after the reorder | `[build] Complete!`, and the artifact carries `static/_astro/lite-youtube.*.js` plus the wrapper's own script chunk |
| Rendered SSR, `/en/` and `/es/` | `<lite-youtube videoid="VLvg0Lpxmng" videotitle="Storico — …" videoplay="Play the demo"|"Reproducir la demo" params="rel=0" nocookie posterquality="maxresdefault">`, the fallback anchor, and the section CTA at `/en/login` and `/es/login` signed out, `/es/dashboard` signed in |
| Section order, both locales | the features title precedes the video copy in the rendered DOM |
| Chromium, real page | the element upgrades, play button `aria-label` is `Play the demo: Storico — Automate your user stories to Kanban boards with AI`, the host box is 1118x629 (aspect 1.778) and fills the outer 1120px bordered box exactly, the poster loads at 1280x720 |
| Chromium, before the click | no iframe, and no request to youtube.com in resource timing (only `i.ytimg.com`, for the poster) |
| Chromium, real click on the play button | iframe `https://www.youtube-nocookie.com/embed/VLvg0Lpxmng?autoplay=1&start=0&rel=0`, `allowfullscreen`, `referrerpolicy="strict-origin-when-cross-origin"` |
| No regression on the landing | exactly one `[data-cta-attention]` (still the hero's, so the one-shot hop is unchanged), `#demo` intact, one `<lite-youtube>` |
| Independent verification | `gentle-ai-verify` over the diff: no blockers |

## Advisories accepted, recorded rather than fixed

1. **The pill markup is duplicated** between `index.astro` and `FeatureSegments.astro`. Extracting a
   shared component is the fix, and it would touch the features band, which is outside what this
   change was asked to do. Maintenance only.
2. **The `▶` in the badge may be announced by screen readers.** The features band's eyebrow already
   ships a decorative glyph in the same position (`✨`), so this follows the existing pattern rather
   than inventing a second one. Moving the glyph into markup behind `aria-hidden` is the fix if the
   pattern is ever retired.
3. **A correction to this session's own report**, kept because the wrong number was stated out loud:
   the lockfile diff is **8 insertions**, not the 3 first reported.

## Open, for the owner

The copy describes the video's content, and only its title could be checked offline (via oEmbed:
"Storico — Automate your user stories to Kanban boards with AI"). If the recording does not show
the story to tasks to export flow the subtitle assumes, the six `landing.video.*` keys are the
edit.
