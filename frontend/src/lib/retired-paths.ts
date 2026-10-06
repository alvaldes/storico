import { detectLocale, type Locale } from '@/i18n/utils';

/**
 * Redirect target for the retired API Reference page, or `null` when the path is not retired.
 *
 * The app's hand-written `/api` page was deleted; its content now lives in the generated docs
 * reference at `/<locale>/docs/api-reference` (see `odd/tasks/api-reference-in-docs.md`). The old
 * URLs are live in production, so they redirect (302) rather than 404. The locale comes from the
 * path prefix when present (`/en/api`, `/es/api`) and otherwise from `Accept-Language` via the
 * same `detectLocale` the public-path redirect uses.
 *
 * The match is EXACT, never a prefix, and that is not an implementation detail: `/api` is also
 * the prefix of this app's own Astro endpoints (`src/pages/api/health/services.ts`, which the
 * status page calls) and of the proxy to the backend. The middleware's `SKIP_PREFIX` is
 * `['/api/', …]` with a trailing slash, so `/api` itself is not skipped and reaches page logic —
 * but `/api/health/services` is skipped and must stay that way. A `startsWith('/api')` match here
 * would swallow those endpoints behind a redirect: the status page would silently lose its
 * service data, with no error anywhere at the redirect level. The exact regex and the negative
 * cases in `retired-paths.test.ts` are the guard against that regression.
 */
export function retiredPathRedirect(pathname: string, acceptLanguage: string | null): string | null {
  const match = pathname.match(/^\/(?:(en|es)\/)?api\/?$/);
  if (!match) return null;

  const locale: Locale = match[1] === 'es' ? 'es' : match[1] === 'en' ? 'en' : detectLocale(acceptLanguage);
  return `/${locale}/docs/api-reference`;
}
