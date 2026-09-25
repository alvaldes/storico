import { describe, it, expect } from 'vitest';

import { API_PREFIX, buildBackendUrl, sanitizePath } from '@/lib/proxy-url';

const API = 'http://localhost:8000';
const FRONT = 'http://localhost:4321';

/**
 * The proxy builds the backend URL from the request URL the browser actually sent.
 *
 * It used to build it from Astro's `[...path]` rest parameter, and Astro strips the trailing
 * slash: measured with a throwaway probe route, `params.path` is `"stories"` for both
 * `/api/probe/stories/` and `/api/probe/stories`, while `url.pathname` keeps the slash. The
 * backend publishes the slashed form, so the slashless URL it was handed answered `307` and Node's
 * `fetch` followed it — one invisible extra round trip on every list call, ~800ms against the dev
 * pooler. The browser does send the slash; the proxy was dropping it.
 *
 * The URLs below are the ones measured in the browser: the list call is
 * `4321/api/v1/stories/?workspace_id=…`, slash included.
 */
describe('buildBackendUrl', () => {
  it('preserves the trailing slash of a list call', () => {
    expect(buildBackendUrl(API, `${FRONT}/api/v1/stories/?workspace_id=ws-1`).toString()).toBe(
      'http://localhost:8000/api/v1/stories/',
    );
  });

  it('leaves a path the caller sent without a slash without one', () => {
    // Preserved, not normalised: the proxy forwards what it was asked for. A caller that omits the
    // slash still pays the backend's redirect, and the fix is to send it, not to hide it here.
    expect(buildBackendUrl(API, `${FRONT}/api/v1/stories`).toString()).toBe(
      'http://localhost:8000/api/v1/stories',
    );
  });

  it('keeps a path without a trailing slash without one', () => {
    expect(buildBackendUrl(API, `${FRONT}/api/v1/stories/abc-1`).toString()).toBe(
      'http://localhost:8000/api/v1/stories/abc-1',
    );
  });

  it('preserves a nested trailing slash', () => {
    // The extraction POST and its status read are published this way, and the extraction router is
    // mounted with `redirect_slashes=False`.
    expect(buildBackendUrl(API, `${FRONT}/api/v1/workspaces/ws-1/extract/`).toString()).toBe(
      'http://localhost:8000/api/v1/workspaces/ws-1/extract/',
    );

    expect(
      buildBackendUrl(API, `${FRONT}/api/v1/workspaces/ws-1/extract/status/ex-1`).toString(),
    ).toBe('http://localhost:8000/api/v1/workspaces/ws-1/extract/status/ex-1');
  });

  it('composes the path under the prefix exactly once', () => {
    const url = buildBackendUrl(API, `${FRONT}/api/v1/projects/`);

    expect(url.pathname).toBe('/api/v1/projects/');
    expect(url.pathname).not.toContain('//api');
  });

  it('answers the prefix root', () => {
    expect(buildBackendUrl(API, `${FRONT}/api/v1/`).pathname).toBe('/api/v1/');
  });

  it('treats a path with no prefix as relative to it', () => {
    // Defensive: the route only serves under the prefix, so a pathname without it cannot be
    // forwarded as an absolute path — that would escape the backend's own namespace.
    expect(buildBackendUrl(API, `${FRONT}/stories/`).pathname).toBe('/api/v1/stories/');
  });

  it('carries no query string of its own', () => {
    // The route appends the caller's params after this; composing them here as well would double
    // them.
    expect(buildBackendUrl(API, `${FRONT}/api/v1/stories/?page=1`).search).toBe('');
  });
});

describe('sanitizePath', () => {
  it('drops traversal segments', () => {
    expect(sanitizePath('stories/../../admin')).toBe('stories/admin');
    expect(sanitizePath('./stories')).toBe('stories');
  });

  it('keeps the trailing slash, which is the point of the module', () => {
    expect(sanitizePath('stories/')).toBe('stories/');
  });

  it('keeps nested segments untouched', () => {
    expect(sanitizePath('workspaces/ws-1/extract/')).toBe('workspaces/ws-1/extract/');
  });
});

describe('a traversal attempt through the proxy', () => {
  it('cannot leave the backend prefix', () => {
    const url = buildBackendUrl(API, `${FRONT}/api/v1/stories/../../../../etc/passwd`);

    // The URL parser resolves `..` per RFC 3986 before this module sees the request, so the
    // pathname arrives as `/etc/passwd`. It is then composed **under** the prefix rather than used
    // as an absolute path, which is the property that matters: no request can address a backend
    // path outside the namespace this route serves. `sanitizePath` is the second line of defence,
    // for the forms the parser leaves alone.
    expect(url.pathname).toBe('/api/v1/etc/passwd');
    expect(url.href).not.toContain('//localhost:8000/etc/passwd');
  });

  it('filters a traversal segment the URL parser leaves in place', () => {
    expect(sanitizePath('stories/../admin')).toBe('stories/admin');
  });
});

describe('API_PREFIX', () => {
  it('is the one prefix the proxy forwards', () => {
    expect(API_PREFIX).toBe('/api/v1');
  });
});
