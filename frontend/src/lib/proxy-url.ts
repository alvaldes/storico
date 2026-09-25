/**
 * How the `/api/v1/*` proxy composes the backend URL for one forwarded request.
 *
 * Two properties matter, and both come from the same mistake: the builder used to be fed Astro's
 * `[...path]` rest parameter instead of the request URL.
 *
 * 1. **The trailing slash survives.** Astro strips it from the rest parameter, so the proxy must
 *    read the request URL instead. The backend publishes the slashed form, so a slashless URL
 *    answers `307` and `fetch` follows it: one extra round trip per list call, and against the dev
 *    pooler that is ~800ms. The browser already sends the slash.
 * 2. **A traversal attempt cannot leave the prefix.** Segments are filtered, and the result is
 *    always composed under `/api/v1` rather than used as an absolute path.
 *
 * Everything the route needs is derived here, from the request URL itself, so the tested surface is
 * the whole transformation rather than a part of it plus untested glue in the route.
 */

/** The one prefix this proxy forwards. */
export const API_PREFIX = '/api/v1';

/**
 * Remove traversal segments from a path, preserving everything else — including the trailing
 * slash, which is load-bearing (see this module's header).
 */
export function sanitizePath(raw: string): string {
  return raw
    .split('/')
    .filter((segment) => segment !== '..' && segment !== '.')
    .join('/');
}

/**
 * The backend URL for a request whose pathname is `incomingPathname`.
 *
 * The caller's pathname is used rather than the route's `params.path` precisely because the rest
 * parameter loses the trailing slash. A pathname without the prefix is still composed under it:
 * this route only serves `/api/v1/*`, and using the pathname as an absolute path would let a
 * request address anything the backend serves.
 *
 * Query parameters are the caller's to append — this returns a URL with none.
 */
/**
 * The backend URL for the request at `requestUrl`.
 *
 * The **request URL** is the input, not Astro's `params.path`, precisely because the rest
 * parameter loses the trailing slash: measured with a throwaway probe route, `params.path` is
 * `"stories"` for both `/api/probe/stories/` and `/api/probe/stories`, while `url.pathname` keeps
 * the slash. The backend publishes the slashed form, so a slashless list path answers `307` and
 * `fetch` follows it — one extra round trip per call, ~800ms against the dev pooler, and invisible
 * to the proxy, which only sees the final `200`.
 *
 * A pathname without the prefix is still composed under it: this route only serves `/api/v1/*`, and
 * using the pathname as an absolute path would let a request address anything the backend serves.
 *
 * Query parameters are the caller's to append — this returns a URL with none.
 */
export function buildBackendUrl(apiUrl: string, requestUrl: string): URL {
  const { pathname } = new URL(requestUrl);

  const withoutPrefix = pathname.startsWith(API_PREFIX)
    ? pathname.slice(API_PREFIX.length)
    : pathname;

  const clean = sanitizePath(withoutPrefix.replace(/^\/+/, ''));

  return new URL(`${API_PREFIX}/${clean}`, apiUrl);
}
