// @vitest-environment node
//
// This guard reads the Starlight markdown and `astro.config.mjs` off the real filesystem, so it
// needs a real path: jsdom hands out `http://localhost/...` URLs for `import.meta.url`, and
// `readFileSync` refuses those. The node environment keeps this file out of the jsdom suite
// instead of making the paths depend on the working directory.
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';

/**
 * The Starlight docs exist in two locales that must not drift apart: a page added to one
 * locale and forgotten in the other is a 404 in that locale's sidebar, and a markdown link
 * that names a deleted page — or points at the wrong locale — is a documented promise that
 * 404s. Nothing in the build enforces any of this, so it is enforced here.
 *
 * Every side of every check is derived, never restated: the page slugs come from the content
 * directories, the links from the markdown bodies, and the sidebar from `astro.config.mjs`.
 * Nothing here holds a second copy of the page list that could drift on its own.
 */
const DOCS_ROOT = new URL('../../content/docs/', import.meta.url);
const CONFIG_SOURCE = readFileSync(new URL('../../../astro.config.mjs', import.meta.url), 'utf8');

const LOCALES = ['en', 'es'] as const;

/** Every `.md` file under a locale's docs directory, recursively, with its locale. */
function markdownFiles(locale: string, dir: URL): { locale: string; name: string; text: string }[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const entryUrl = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, dir);
    if (entry.isDirectory()) return markdownFiles(locale, entryUrl);
    if (!entry.name.endsWith('.md')) return [];
    return [{ locale, name: entry.name, text: readFileSync(entryUrl, 'utf8') }];
  });
}

/** The page slugs a locale exposes, derived from its content directory. */
function pageSlugs(locale: string): string[] {
  return readdirSync(new URL(`${locale}/docs/`, DOCS_ROOT))
    .filter((name) => name.endsWith('.md'))
    .map((name) => name.replace(/\.md$/, ''));
}

const MARKDOWN = LOCALES.flatMap((locale) => markdownFiles(locale, new URL(`${locale}/`, DOCS_ROOT)));
const PAGES = Object.fromEntries(LOCALES.map((locale) => [locale, pageSlugs(locale)]));

/** Internal docs links (`/xx/docs/...`) found in the markdown bodies. */
const LINKS = MARKDOWN.flatMap(({ locale, name, text }) =>
  [...text.matchAll(/\]\((\/(?:en|es)\/docs[^\s)]*)\)/g)].map((match) => ({
    locale,
    file: name,
    target: match[1],
  })),
);

/**
 * The `link` entries of the Starlight `sidebar`, parsed out of the config.
 *
 * The sidebar array is located by bracket matching from its `sidebar: [` marker rather than
 * by scanning the whole file for `link:`, so a future `link` option on another integration
 * cannot masquerade as a sidebar entry.
 */
function sidebarLinks(): string[] {
  const marker = CONFIG_SOURCE.indexOf('sidebar: [');
  if (marker === -1) return [];

  let depth = 0;
  let end = -1;
  for (let i = marker + 'sidebar:'.length; i < CONFIG_SOURCE.length; i++) {
    const char = CONFIG_SOURCE[i];
    if (char === '[') depth++;
    if (char === ']' && --depth === 0) {
      end = i;
      break;
    }
  }
  if (end === -1) return [];

  return [...CONFIG_SOURCE.slice(marker, end).matchAll(/link:\s*'([^']+)'/g)].map(
    (match) => match[1],
  );
}

const SIDEBAR_LINKS = sidebarLinks();

/** The slug a docs path points at; `/docs/` and `/en/docs/` are both the `index` page. */
function slugOf(docsPath: string): string {
  const withoutDocs = docsPath.replace(/^\/(?:(?:en|es)\/)?docs\/?/, '').replace(/\/+$/, '');
  return withoutDocs === '' ? 'index' : withoutDocs;
}

describe('the docs parse is not vacuous', () => {
  it('finds the markdown of both locales', () => {
    for (const locale of LOCALES) {
      expect(
        MARKDOWN.filter((file) => file.locale === locale).length,
        `${locale} has docs pages`,
      ).toBeGreaterThanOrEqual(5);
    }
  });

  it('finds internal links in the markdown, or the link cases below are vacuous', () => {
    expect(LINKS.length).toBeGreaterThan(0);
    for (const locale of LOCALES) {
      expect(LINKS.filter((link) => link.locale === locale).length).toBeGreaterThan(0);
    }
  });

  it('parses the sidebar out of the config, or the sidebar cases below are vacuous', () => {
    expect(SIDEBAR_LINKS.length).toBeGreaterThan(0);
    expect(SIDEBAR_LINKS.every((link) => link.startsWith('/docs'))).toBe(true);
  });
});

describe('locale slug parity', () => {
  it('exposes the same page slugs in both locales', () => {
    expect([...PAGES.es].sort()).toEqual([...PAGES.en].sort());
  });
});

describe('docs link integrity', () => {
  it('uses the locale of the file it appears in', () => {
    const crossLocale = LINKS.filter((link) => !link.target.startsWith(`/${link.locale}/docs`));
    expect(
      crossLocale.map((link) => `${link.locale}/${link.file} -> ${link.target}`),
      'a markdown file must link within its own locale',
    ).toEqual([]);
  });

  it('resolves to a page that exists in the locale it claims', () => {
    const broken = LINKS.filter((link) => {
      const targetLocale = link.target.match(/^\/(en|es)\//)?.[1];
      return targetLocale === undefined || !PAGES[targetLocale]?.includes(slugOf(link.target));
    });
    expect(
      broken.map((link) => `${link.locale}/${link.file} -> ${link.target}`),
      'every internal docs link must resolve to an existing page',
    ).toEqual([]);
  });
});

describe('sidebar coverage', () => {
  it('links only to pages that exist', () => {
    const broken = SIDEBAR_LINKS.filter((link) => !PAGES.en.includes(slugOf(link)));
    expect(broken, `sidebar links to missing pages: ${broken.join(', ')}`).toEqual([]);
  });

  it('lists every existing page', () => {
    const listed = new Set(SIDEBAR_LINKS.map(slugOf));
    const missing = PAGES.en.filter((slug) => !listed.has(slug));
    expect(missing, `pages missing from the sidebar: ${missing.join(', ')}`).toEqual([]);
  });
});
