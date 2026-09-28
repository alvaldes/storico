import type { APIRoute } from 'astro';
import { config } from '@/lib/config';
import { HEALTH_SERVICES_PATH } from '@/lib/health';

/**
 * Public, same-origin hop for the status page's diagnostics document.
 *
 * Why this endpoint exists instead of the browser calling the backend directly:
 *
 * - The `/status` page is public, but the authenticated catch-all proxy
 *   (`/api/v1/[...path]`) answers `401` to anonymous visitors, so it cannot serve this.
 * - The backend's CORS allow-list is measured narrow: it declares exactly the origins it
 *   knows (dev `http://localhost:4321`, production one `*.vercel.app`), so a direct call
 *   would break on any other origin the site is served from.
 *
 * This is one fixed upstream call, not a proxy: no query, no path params, no body and no
 * headers are taken from the request. The path is imported from `@/lib/health`
 * (`HEALTH_SERVICES_PATH`) so this end and the parser cannot drift to different routes.
 *
 * The timeout keeps the worst case unchanged in kind from the pre-island page: the page
 * used to block its whole SSR document on the same `AbortSignal.timeout(10_000)`.
 */
const BACKEND_TIMEOUT_MS = 10_000;

export const GET: APIRoute = async () => {
  try {
    const backendResponse = await fetch(`${config.apiUrl}${HEALTH_SERVICES_PATH}`, {
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
    });

    if (!backendResponse.ok) {
      console.warn(
        `[api/health] backend ${backendResponse.status} ${backendResponse.statusText} — ${HEALTH_SERVICES_PATH}`,
      );
    }

    const body = await backendResponse.text();
    return new Response(body, {
      status: backendResponse.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    // `AbortSignal.timeout` aborts with a `TimeoutError` DOMException; `AbortError` is
    // checked too so an engine that reports the generic name still maps to 504.
    if (
      error instanceof DOMException &&
      (error.name === 'TimeoutError' || error.name === 'AbortError')
    ) {
      console.warn('[api/health] backend timeout —', HEALTH_SERVICES_PATH);
      return new Response(JSON.stringify({ detail: 'Backend timeout', type: 'proxy_timeout' }), {
        status: 504,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    console.warn('[api/health] proxy error:', error);
    return new Response(JSON.stringify({ detail: 'Backend unavailable', type: 'proxy_error' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }
};
