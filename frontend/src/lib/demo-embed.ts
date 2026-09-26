/**
 * Host-side wiring of the landing ↔ live-demo embed bridge.
 *
 * The live demo (`storico-live-demo`, a separate static Astro project) runs its
 * typing-loop animation inside an iframe. A cross-origin host cannot forward raw
 * `blur`/`focus` events into the frame, so the two sides use one explicit message:
 * the host sends `{ source: 'storico-landing', type: 'demo-leave' }` via
 * `iframe.contentWindow.postMessage`, and the demo restarts its loop if the visitor
 * had already interacted (a harmless no-op otherwise). The protocol is defined by the
 * demo side and documented in its `LOOP_ANIMATION_BEHAVIOR.md`; everything in this
 * module exists to emit exactly that message, to exactly one origin.
 *
 * The mistake this module prevents: hard-coding the demo URL or the target origin,
 * or letting `postMessage` fall back to `'*'`. A wildcard targetOrigin would deliver
 * the bridge message to any window on any origin — so a base without an origin must
 * fail loudly instead (see `demoTargetOrigin`).
 */

/** The demo base URL when `PUBLIC_DEMO_URL` is not set — the demo dev server. */
export const DEFAULT_DEMO_BASE = 'http://localhost:4322';

/**
 * The iframe `src` for the demo page in `locale`.
 *
 * The demo routes its locales the same way the product does — a leading and a
 * trailing slash (`/en/`, `/es/`) — so a base that already carries a path (e.g. a
 * preview deployment under a subpath) survives untouched apart from the appended
 * locale segment.
 */
export function demoEmbedUrl(base: string, locale: 'en' | 'es'): string {
  return `${base.replace(/\/+$/, '')}/${locale}/`;
}

/**
 * The `postMessage` target origin for a demo base URL: the origin of the resolved
 * URL, and never `'*'`.
 *
 * A relative base (`/demo`, no scheme/host) has no origin to postMessage against.
 * Rather than silently producing a broken or wildcard target, this throws naming
 * `PUBLIC_DEMO_URL` — this repo's doctrine is no silent fallbacks, and a silently
 * broken targetOrigin is worse than a loud failure at render time.
 */
export function demoTargetOrigin(base: string): string {
  let resolved: URL;
  try {
    resolved = new URL(base);
  } catch {
    throw new Error(
      `PUBLIC_DEMO_URL must be an absolute URL (got "${base}"): a relative base has no origin, ` +
        `and the demo bridge needs one to postMessage against — falling back to '*' is not acceptable.`,
    );
  }
  return resolved.origin;
}

/** The one message the demo accepts. Shape is validated demo-side, never the origin. */
const DEMO_LEAVE_MESSAGE = Object.freeze({ source: 'storico-landing', type: 'demo-leave' });

/**
 * Forward "the visitor left the demo" signals to the iframe, per the demo's embed
 * protocol. Sends `DEMO_LEAVE_MESSAGE` on exactly three triggers:
 *
 * 1. `window` `blur` — the visitor left the page/tab.
 * 2. `document` `visibilitychange`, only when the document is hidden.
 * 3. `pointerdown` on `document`, only when the target is outside the iframe —
 *    the visitor clicked the landing instead of the demo.
 *
 * No IntersectionObserver, deliberately: jsdom has none (so it cannot be tested
 * here), and a scroll-out trigger would restart the animation every time the
 * visitor scrolls past the demo, which nobody asked for.
 *
 * Call this once per iframe per page load, from a page script that runs on
 * `astro:page-load`. The returned teardown removes every listener, but it may be
 * safely discarded: an Astro view-transition swap inserts a fresh `<iframe>` and
 * drops the old document along with its listeners, so there is nothing leaky to
 * clean up.
 */
export function attachDemoLeaveForwarding(iframe: HTMLIFrameElement): () => void {
  const targetOrigin = iframe.dataset.targetOrigin;
  if (!targetOrigin) {
    // Same doctrine as `demoTargetOrigin`: the attribute is rendered server-side
    // from `demoTargetOrigin(config.demoUrl)`; its absence means the wiring was
    // fed an iframe the page did not build, and guessing an origin is worse than
    // failing loudly.
    throw new Error(
      'Missing data-target-origin on the demo iframe: attachDemoLeaveForwarding refuses to ' +
        'postMessage without an explicit target origin.',
    );
  }

  const send = () => {
    // A fresh object per send: `postMessage` serializes it anyway, and a shared
    // frozen object is one mutation away from a cross-listener bug.
    iframe.contentWindow?.postMessage({ ...DEMO_LEAVE_MESSAGE }, targetOrigin);
  };

  const onVisibilityChange = () => {
    if (document.hidden) send();
  };

  const onPointerDown = (event: Event) => {
    const target = event.target;
    // A pointer event whose target lives inside the frame is the visitor engaging
    // with the demo, not leaving it.
    if (target instanceof Node && iframe.contains(target)) return;
    send();
  };

  window.addEventListener('blur', send);
  document.addEventListener('visibilitychange', onVisibilityChange);
  document.addEventListener('pointerdown', onPointerDown);

  return () => {
    window.removeEventListener('blur', send);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    document.removeEventListener('pointerdown', onPointerDown);
  };
}
