import { defineMiddleware } from 'astro:middleware';
import { getSession } from 'auth-astro/server';
import {
  detectLocale,
  isPublicPagePath,
  isProtectedPagePath,
  getLocaleFromPath,
} from '@/i18n/utils';

const SKIP_PREFIX = ['/api/', '/_astro/', '/favicon'];

export const onRequest = defineMiddleware(async (context, next) => {
  // Store session
  context.locals.session = await getSession(context.request);

  const url = new URL(context.request.url);
  const { pathname } = url;

  // Skip non-page paths
  if (SKIP_PREFIX.some((p) => pathname.startsWith(p))) {
    return next();
  }

  // If path already has a locale prefix
  if (getLocaleFromPath(pathname)) {
    // Auth guard: redirect to login if page requires authentication
    if (!context.locals.session && isProtectedPagePath(pathname)) {
      const locale = getLocaleFromPath(pathname) as string;
      const cleanPath = pathname.replace(/^\/(en|es)/, '') || '/dashboard';
      const redirectTarget = `/${locale}/login?redirect=${encodeURIComponent(cleanPath)}`;
      return context.redirect(redirectTarget, 302);
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
