// @vitest-environment node
//
// This guard reads real source files off the filesystem, so it needs a real path: jsdom hands out
// `http://localhost/...` URLs for `import.meta.url`, and `readFileSync` refuses those. The node
// environment keeps this file out of the jsdom suite — the same reason `docs-content.test.ts` and
// the retired `api-docs-copy.test.ts` use(d) it.
import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';

import { retiredPathRedirect } from '@/lib/retired-paths';
import { detectLocale } from '@/i18n/utils';

/**
 * The retired app page `/api` (and its locale-prefixed forms) was deleted; its content now lives
 * in the generated docs reference at `/<locale>/docs/api-reference`. Old URLs are live in
 * production, so they redirect instead of 404ing.
 *
 * The property this guard exists to pin is NEGATIVE, not positive: `/api` is also the prefix of
 * the app's own Astro endpoints (`src/pages/api/health/services.ts`, called by the status page)
 * and of the proxy to the backend. `SKIP_PREFIX` in the middleware is `['/api/', …]` with a
 * trailing slash, so `/api` itself is NOT skipped and reaches page logic. A redirect written as a
 * prefix match would swallow `/api/health/*` and the backend proxy, and the status page would
 * break with no error at the redirect level. Every endpoint-shaped path below must resolve to
 * `null`.
 */

/** The real health endpoint the status page calls. If it moves, this guard must be revisited. */
const HEALTH_ENDPOINT = new URL('../../pages/api/health/services.ts', import.meta.url);

describe('the health endpoint the negative cases protect really exists', () => {
  it('finds src/pages/api/health/services.ts relative to this test', () => {
    expect(existsSync(HEALTH_ENDPOINT)).toBe(true);
  });
});

describe('retiredPathRedirect redirects the exact retired paths', () => {
  it('sends bare /api to the locale-resolved docs reference', () => {
    expect(retiredPathRedirect('/api', 'es-MX')).toBe('/es/docs/api-reference');
    expect(retiredPathRedirect('/api', 'en-US')).toBe('/en/docs/api-reference');
  });

  it('falls back to the detectLocale default when there is no Accept-Language', () => {
    expect(retiredPathRedirect('/api', null)).toBe(`/${detectLocale(null)}/docs/api-reference`);
    expect(retiredPathRedirect('/api', null)).toBe('/en/docs/api-reference');
  });

  it('treats /api/ the same as /api', () => {
    expect(retiredPathRedirect('/api/', 'es-MX')).toBe(retiredPathRedirect('/api', 'es-MX'));
    expect(retiredPathRedirect('/api/', 'es-MX')).toBe('/es/docs/api-reference');
  });

  it('honors the locale prefix already in the path', () => {
    expect(retiredPathRedirect('/en/api', 'es-MX')).toBe('/en/docs/api-reference');
    expect(retiredPathRedirect('/en/api/', null)).toBe('/en/docs/api-reference');
    expect(retiredPathRedirect('/es/api', 'en-US')).toBe('/es/docs/api-reference');
  });

  it('returns a target for at least one input, so a null-stub cannot pass this suite', () => {
    const targets = ['/api', '/api/', '/en/api', '/es/api'].map((p) => retiredPathRedirect(p, null));
    expect(targets.some((t) => t !== null)).toBe(true);
  });
});

describe('retiredPathRedirect never swallows the API surface the prefix shares', () => {
  it('leaves the app health endpoint alone', () => {
    expect(retiredPathRedirect('/api/health/services', 'es-MX')).toBeNull();
    expect(retiredPathRedirect('/api/health/services', null)).toBeNull();
  });

  it('leaves the backend proxy paths alone', () => {
    expect(retiredPathRedirect('/api/v1/workspaces/x/extract/', null)).toBeNull();
    expect(retiredPathRedirect('/api/v1/tasks/', null)).toBeNull();
  });

  it('does not match longer paths that merely share the prefix', () => {
    expect(retiredPathRedirect('/apiary', null)).toBeNull();
  });
});

describe('retiredPathRedirect ignores paths that were never retired', () => {
  it('returns null for live pages', () => {
    expect(retiredPathRedirect('/status', null)).toBeNull();
    expect(retiredPathRedirect('/en/status', null)).toBeNull();
    expect(retiredPathRedirect('/docs/api-reference', null)).toBeNull();
    expect(retiredPathRedirect('/en/docs/api-reference', null)).toBeNull();
  });
});

/**
 * The middleware cannot be imported here: it pulls `astro:middleware` and `auth-astro/server`, both
 * virtual modules. So the wiring is pinned at the source level, which is the same technique the
 * docs and sidebar guards in this repository use.
 */
const MIDDLEWARE = readFileSync(new URL('../../middleware.ts', import.meta.url), 'utf8');

describe('the middleware wiring calls the redirect before it skips /api/', () => {
  /**
   * Every case above was green while `/api/` answered 404 in a running dev server, and this is the
   * guard that would have caught it. `SKIP_PREFIX` is `['/api/', …]` matched with `startsWith`, so
   * `/api/` — WITH the trailing slash — was skipped before the redirect ran. The pure rule was
   * right and the wiring was wrong, which is a difference no test of the pure rule can see.
   */
  it('reads both surfaces it compares, or the ordering case is vacuous', () => {
    expect(MIDDLEWARE).toMatch(/retiredPathRedirect\(/);
    expect(MIDDLEWARE).toMatch(/SKIP_PREFIX\.some\(/);
  });

  it('calls retiredPathRedirect before the SKIP_PREFIX early return', () => {
    expect(
      MIDDLEWARE.indexOf('retiredPathRedirect('),
      'the redirect must be called, and before the skip: /api/ starts with /api/ and would 404',
    ).toBeLessThan(MIDDLEWARE.indexOf('SKIP_PREFIX.some('));
  });

  it('never matches a prefix, which is what would swallow the app endpoints', () => {
    expect(MIDDLEWARE).not.toMatch(/startsWith\([^)]*retiredPathRedirect/);
  });
});
