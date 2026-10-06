import { localizedPath, useTranslations, type Locale } from '@/i18n/utils';

export interface PublicNavLink {
  /** Locale-less app path, e.g. `/docs`. */
  path: string;
  /** Locale-aware href, e.g. `/en/docs`. */
  href: string;
  /** Label from the app's translation catalogs. */
  label: string;
}

/**
 * The desktop nav destinations of the app's public navbar, in render order.
 * Consumed by `PublicLayout.astro` only: the Starlight docs header renders its
 * own, shorter list (`DOCS_HEADER_NAV_PATHS` below) and deliberately does NOT
 * mirror this one — see `odd/tasks/docs-header-nav-scope.md`. This module owns
 * both lists so neither can drift into a third hardcoded copy.
 */
export const PUBLIC_NAV_PATHS = ['/docs', '/api', '/status'] as const;

/**
 * The nav destinations of the Starlight docs header (`Header.astro` override),
 * in render order: the app landing page, then the status page. This list is
 * deliberately NOT the app navbar's `PUBLIC_NAV_PATHS` above — the owner scoped
 * the reduction to the docs header surface only
 * (`odd/tasks/docs-header-nav-scope.md`).
 */
export const DOCS_HEADER_NAV_PATHS = ['/', '/status'] as const;

/**
 * Every path either list may declare. The builder is typed against this union rather than
 * `string`, so a call site passing an undeclared path is a compile error and not an `undefined`
 * label at runtime.
 */
type NavPath = (typeof PUBLIC_NAV_PATHS)[number] | (typeof DOCS_HEADER_NAV_PATHS)[number];

/**
 * Label key (into each catalog's `footer` section) for every path in either declared list. Typed
 * against the union of both path unions, so adding a path to either list without a label key here
 * is a compile error, not a runtime `undefined` label.
 */
const NAV_LABEL_KEYS: Record<NavPath, 'documentation' | 'api_reference' | 'status_page' | 'home'> = {
  '/docs': 'documentation',
  '/api': 'api_reference',
  '/status': 'status_page',
  '/': 'home',
};

/**
 * The one builder both surfaces go through, so href and label construction cannot drift between
 * the app navbar and the docs header.
 */
function buildNavLinks(paths: readonly NavPath[], locale: Locale): PublicNavLink[] {
  const t = useTranslations(locale);
  return paths.map((path) => ({
    path,
    href: localizedPath(path, locale),
    label: t.footer[NAV_LABEL_KEYS[path]],
  }));
}

/**
 * Build the app's public desktop nav links for a locale. Labels come from the
 * same footer translation keys the navbar has always used; hrefs go through
 * `localizedPath`, so they carry the locale prefix.
 */
export function publicNavLinks(locale: Locale): PublicNavLink[] {
  return buildNavLinks(PUBLIC_NAV_PATHS, locale);
}

/**
 * Build the Starlight docs header nav links for a locale: the app landing page
 * labelled `footer.home`, then the status page labelled `footer.status_page`.
 * Shares the builder with `publicNavLinks` so the two surfaces cannot drift.
 */
export function docsHeaderNavLinks(locale: Locale): PublicNavLink[] {
  return buildNavLinks(DOCS_HEADER_NAV_PATHS, locale);
}
