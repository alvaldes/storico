import { describe, it, expect, vi, afterEach } from 'vitest';

import {
  DEFAULT_DEMO_BASE,
  demoEmbedUrl,
  demoTargetOrigin,
  attachDemoLeaveForwarding,
} from '@/lib/demo-embed';

const DEMO = 'http://localhost:4322';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('DEFAULT_DEMO_BASE', () => {
  it('is the demo dev server', () => {
    expect(DEFAULT_DEMO_BASE).toBe('http://localhost:4322');
  });
});

describe('demoEmbedUrl', () => {
  it('appends the locale segment with leading and trailing slashes', () => {
    // The demo routes its locales the same way the product does: `/en/`, `/es/`.
    expect(demoEmbedUrl(DEMO, 'en')).toBe('http://localhost:4322/en/');
    expect(demoEmbedUrl(DEMO, 'es')).toBe('http://localhost:4322/es/');
  });

  it('strips a trailing slash from the base instead of doubling it', () => {
    expect(demoEmbedUrl(`${DEMO}/`, 'en')).toBe('http://localhost:4322/en/');
  });

  it('keeps a base that already carries a path untouched apart from the locale', () => {
    // Preview deployments serve the demo under a subpath; the locale segment is
    // appended, never treated as a new root.
    expect(demoEmbedUrl('https://demo.example/preview', 'es')).toBe(
      'https://demo.example/preview/es/',
    );
  });
});

describe('demoTargetOrigin', () => {
  it('returns the origin of the resolved URL', () => {
    expect(demoTargetOrigin(DEMO)).toBe('http://localhost:4322');
  });

  it('returns the bare origin for a base that carries a path', () => {
    expect(demoTargetOrigin('https://demo.example/preview')).toBe('https://demo.example');
  });

  it('never returns a wildcard', () => {
    // The whole point of the helper: a wildcard targetOrigin would let any window
    // on any origin receive the bridge message.
    expect(demoTargetOrigin(DEMO)).not.toBe('*');
    expect(demoTargetOrigin('https://demo.example/preview')).not.toBe('*');
  });

  it('rejects a relative base by name instead of falling back silently', () => {
    // A relative base has no origin to postMessage against. This repo's doctrine
    // is no silent fallbacks: a silently-broken targetOrigin is worse than a loud
    // failure at render time.
    expect(() => demoTargetOrigin('/demo')).toThrowError(/PUBLIC_DEMO_URL/);
    expect(() => demoTargetOrigin('/demo')).toThrowError(/absolute/i);
  });
});

describe('attachDemoLeaveForwarding', () => {
  const PROTOCOL = { source: 'storico-landing', type: 'demo-leave' };

  /** An iframe whose `contentWindow.postMessage` is a spy, plus a spy handle. */
  function makeIframe(): { iframe: HTMLIFrameElement; postMessage: ReturnType<typeof vi.fn> } {
    const postMessage = vi.fn();
    const iframe = document.createElement('iframe');
    iframe.dataset.targetOrigin = DEMO;
    Object.defineProperty(iframe, 'contentWindow', {
      value: { postMessage },
      configurable: true,
    });
    document.body.appendChild(iframe);
    return { iframe, postMessage };
  }

  it('sends the exact protocol payload to the exact target origin on window blur', () => {
    const { iframe, postMessage } = makeIframe();

    attachDemoLeaveForwarding(iframe);
    window.dispatchEvent(new Event('blur'));

    expect(postMessage).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledWith(PROTOCOL, DEMO);
  });

  it('sends on visibilitychange only when the document is hidden', () => {
    const { iframe, postMessage } = makeIframe();
    const hidden = Object.getOwnPropertyDescriptor(document, 'hidden');
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });

    attachDemoLeaveForwarding(iframe);
    document.dispatchEvent(new Event('visibilitychange'));

    expect(postMessage).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledWith(PROTOCOL, DEMO);

    // While visible the message must NOT be sent — the visitor is still watching.
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));

    expect(postMessage).toHaveBeenCalledTimes(1);

    if (hidden) Object.defineProperty(document, 'hidden', hidden);
  });

  it('sends on pointerdown outside the iframe and stays silent inside it', () => {
    const { iframe, postMessage } = makeIframe();

    attachDemoLeaveForwarding(iframe);

    // A click inside the demo is the visitor engaging with the demo, not leaving.
    const inside = document.createElement('div');
    iframe.appendChild(inside);
    expect(iframe.contains(inside)).toBe(true);
    inside.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    expect(postMessage).not.toHaveBeenCalled();

    // A click on the landing itself is a leave: the demo must restart its loop.
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    outside.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    expect(postMessage).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledWith(PROTOCOL, DEMO);
  });

  it('sends on none of the events the protocol does not cover', () => {
    // Guard against scope creep: no scroll, no focus, no IntersectionObserver —
    // a scroll-out trigger would restart the animation every time the visitor
    // scrolls past the demo, which nobody asked for.
    const { iframe, postMessage } = makeIframe();

    attachDemoLeaveForwarding(iframe);
    window.dispatchEvent(new Event('focus'));
    window.dispatchEvent(new Event('scroll'));
    document.dispatchEvent(new Event('scroll'));

    expect(postMessage).not.toHaveBeenCalled();
  });

  it('rejects an iframe without a target origin instead of falling back silently', () => {
    const iframe = document.createElement('iframe');
    Object.defineProperty(iframe, 'contentWindow', {
      value: { postMessage: vi.fn() },
      configurable: true,
    });

    expect(() => attachDemoLeaveForwarding(iframe)).toThrowError(/data-target-origin/);
  });

  it('teardown stops every registered trigger', () => {
    const { iframe, postMessage } = makeIframe();

    const teardown = attachDemoLeaveForwarding(iframe);
    teardown();

    window.dispatchEvent(new Event('blur'));

    const hidden = Object.getOwnPropertyDescriptor(document, 'hidden');
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    if (hidden) Object.defineProperty(document, 'hidden', hidden);

    const outside = document.createElement('button');
    document.body.appendChild(outside);
    outside.dispatchEvent(new Event('pointerdown', { bubbles: true }));

    expect(postMessage).not.toHaveBeenCalled();
  });
});
