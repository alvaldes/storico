import { defineMiddleware } from 'astro:middleware';
import {
  detectLocale,
  isPublicPagePath,
  isProtectedPagePath,
  getLocaleFromPath,
} from '@/i18n/utils';
import { retiredPathRedirect } from '@/lib/retired-paths';

const SKIP_PREFIX = ['/api/', '/_astro/', '/favicon'];

export const onRequest = defineMiddleware(async (context, next) => {
  const url = new URL(context.request.url);
  const { pathname } = url;

  // Retired pages go first, and deliberately BEFORE the SKIP_PREFIX early return below: `/api/`
  // starts with `/api/`, so the skip would swallow it and it would 404 instead of redirecting —
  // the pure guard and the manual walkthrough both say it redirects, and they were right about
  // the rule and wrong about the wiring. The match is exact, so `/api/health/services` and the
  // backend proxy still fall through to the skip, which is the property that must not break.
  const retiredTarget = retiredPathRedirect(pathname, context.request.headers.get('accept-language'));
  if (retiredTarget) {
    return context.redirect(retiredTarget, 302);
  }

  // Skip non-page paths
  if (SKIP_PREFIX.some((p) => pathname.startsWith(p))) {
    return next();
  }

  // If path already has a locale prefix
  if (getLocaleFromPath(pathname)) {
    // Auth guard: redirect to login if page requires authentication. The session is loaded here,
    // where it is consumed, and nowhere else: a top-level static import of `auth-astro/server`
    // drags `auth.config.ts` → `src/lib/config.ts` into every import of this middleware, and that
    // module throws at import time by design (`required('API_URL')`). The docs prerender runs this
    // middleware at build time — the 20 Starlight pages cannot be turned off, Pagefind indexes
    // them — so the build must reach this module without needing any environment. The dynamic
    // import keeps the auth module out of that graph entirely: any future prerendered public page
    // stays environment-free, and public requests stop paying a cookie parse + `@auth/core` call
    // that nothing read.
    if (isProtectedPagePath(pathname)) {
      const { getSession } = await import('auth-astro/server');
      context.locals.session = await getSession(context.request);
      if (!context.locals.session) {
        const locale = getLocaleFromPath(pathname) as string;
        const cleanPath = pathname.replace(/^\/(en|es)/, '') || '/dashboard';
        const redirectTarget = `/${locale}/login?redirect=${encodeURIComponent(cleanPath)}`;
        return context.redirect(redirectTarget, 302);
      }
    }
    return next();
  }

  // Redirect non-prefixed public paths to the detected locale
  if (isPublicPagePath(pathname)) {
    const acceptLang = context.request.headers.get('accept-language');
    const locale = detectLocale(acceptLang);
    const target = pathname === '/' ? `/${locale}/` : `/${locale}${pathname}`;
    return context.redirect(target, 302);
  }

  return next();
});
