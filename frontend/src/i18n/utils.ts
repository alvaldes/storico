import en from './en.json';
import es from './es.json';

export type Locale = 'en' | 'es';

const translations: Record<Locale, typeof en> = { en, es };

/**
 * Returns the translation object for the given locale.
 * Falls back to English if the locale is not supported.
 */
export function useTranslations(locale: string): typeof en {
  if (locale === 'es') return translations.es;
  return translations.en;
}

/**
 * Returns a localized URL path for the given locale.
 * English paths have no prefix; Spanish paths get /es/ prefix.
 */
export function localizedPath(path: string, locale: Locale): string {
  return `/${locale}${path}`;
}

/**
 * Detects the preferred locale from the Accept-Language header.
 */
export function detectLocale(acceptLanguage: string | null): Locale {
  if (!acceptLanguage) return 'en';
  // Spanish (any variant: es-ES, es-MX, etc.)
  if (/^es\b/.test(acceptLanguage)) return 'es';
  return 'en';
}

/**
 * Returns true if the given path is a public page path (needs locale redirect).
 */
const PUBLIC_PATHS = [
  '/',
  '/login',
  '/about',
  '/privacy',
  '/terms',
  '/docs',
  '/api',
  '/status',
];

const PROTECTED_PATHS = [
  '/dashboard',
  '/stories',
  '/kanban',
  '/export',
  '/account',
];

/**
 * Returns true if the given path is a public page path (needs locale redirect).
 */
export function isPublicPagePath(pathname: string): boolean {
  return [...PUBLIC_PATHS, ...PROTECTED_PATHS].some(
    (p) => pathname === p || pathname === p + '/',
  );
}

/**
 * Returns true if the given path requires authentication.
 * Accepts both prefixed (e.g. "/en/dashboard") and non-prefixed paths.
 */
export function isProtectedPagePath(pathname: string): boolean {
  const path = pathname.replace(/^\/(en|es)/, '');
  return PROTECTED_PATHS.some(
    (p) => path === p || path === p + '/',
  );
}

/**
 * Returns the locale from a URL path that starts with /en/ or /es/.
 * Returns null if no locale prefix is found.
 */
export function getLocaleFromPath(pathname: string): Locale | null {
  const match = pathname.match(/^\/(en|es)(\/|$)/);
  if (match) return match[1] as Locale;
  return null;
}
