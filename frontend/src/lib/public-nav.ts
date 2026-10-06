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
 * `PublicLayout.astro` and the Starlight docs header (`Header.astro` override)
 * both render from this list, so it cannot drift into a third hardcoded copy.
 */
export const PUBLIC_NAV_PATHS = ['/docs', '/api', '/status'] as const;

const NAV_LABEL_KEYS: Record<(typeof PUBLIC_NAV_PATHS)[number], 'documentation' | 'api_reference' | 'status_page'> = {
  '/docs': 'documentation',
  '/api': 'api_reference',
  '/status': 'status_page',
};

/**
 * Build the app's public desktop nav links for a locale. Labels come from the
 * same footer translation keys the navbar has always used; hrefs go through
 * `localizedPath`, so they carry the locale prefix.
 */
export function publicNavLinks(locale: Locale): PublicNavLink[] {
  const t = useTranslations(locale);
  return PUBLIC_NAV_PATHS.map((path) => ({
    path,
    href: localizedPath(path, locale),
    label: t.footer[NAV_LABEL_KEYS[path]],
  }));
}
