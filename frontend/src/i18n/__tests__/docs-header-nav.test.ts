// @vitest-environment node
//
// This guard reads `astro.config.mjs` and the Starlight overrides off the real filesystem, so it
// needs a real path: jsdom hands out `http://localhost/...` URLs for `import.meta.url`, and
// `readFileSync` refuses those. The node environment keeps this file out of the jsdom suite — the
// same reason `docs-content.test.ts` next door uses it.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

import {
  DOCS_HEADER_NAV_PATHS,
  PUBLIC_NAV_PATHS,
  docsHeaderNavLinks,
  publicNavLinks,
} from '@/lib/public-nav';
import { localizedPath } from '@/i18n/utils';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

/**
 * The docs header no longer mirrors the app navbar: by the owner's decision, recorded in
 * `odd/tasks/docs-header-nav-scope.md`, it renders its own two-destination list (the app landing
 * page and the status page) while the app's navbar keeps the original three. Both surfaces still
 * consume one module (`src/lib/public-nav.ts`), so the guard pins BOTH declared lists explicitly —
 * not as a subset relation — and keeps refusing to let the header name a destination or a label
 * itself, so no third hardcoded copy of either list can appear.
 */
const CONFIG_SOURCE = readFileSync(new URL('../../../astro.config.mjs', import.meta.url), 'utf8');
const PUBLIC_LAYOUT = readFileSync(new URL('../../layouts/PublicLayout.astro', import.meta.url), 'utf8');
const SITE_TITLE = readFileSync(new URL('../../components/starlight/SiteTitle.astro', import.meta.url), 'utf8');
const HEADER = readFileSync(new URL('../../components/starlight/Header.astro', import.meta.url), 'utf8');

const CATALOGS = { en, es } as const;
type CatalogLocale = keyof typeof CATALOGS;

type FooterCatalog = (typeof en)['footer'];

/** The footer keys the shared module maps the app navbar's nav paths onto. */
const NAV_LABEL_KEYS = ['documentation', 'api_reference', 'status_page'] as const;

/**
 * The label key each declared nav path must map onto, as an independent expectation restated
 * here so a path added to a module list without a catalogue key fails this guard even though
 * the module's own map is compile-time enforced.
 */
const LABEL_KEY_BY_PATH: Record<string, keyof FooterCatalog> = {
  '/docs': 'documentation',
  '/docs/api-reference': 'api_reference',
  '/status': 'status_page',
  '/': 'home',
};

/**
 * The Starlight `components` override block, located by brace matching from its
 * `components: {` marker inside the `starlight()` integration options — the same
 * source-level technique `docs-content.test.ts` uses for the sidebar array.
 */
function starlightComponentsBlock(): string {
  const marker = CONFIG_SOURCE.indexOf('components: {');
  if (marker === -1) return '';

  let depth = 0;
  for (let i = marker + 'components:'.length; i < CONFIG_SOURCE.length; i++) {
    const char = CONFIG_SOURCE[i];
    if (char === '{') depth++;
    if (char === '}' && --depth === 0) return CONFIG_SOURCE.slice(marker, i + 1);
  }
  return '';
}

describe('the shared public nav module', () => {
  it('maps the nav paths onto the footer translation keys of each catalog', () => {
    for (const locale of ['en', 'es'] as CatalogLocale[]) {
      const labels = publicNavLinks(locale).map((link) => link.label);
      const expected = NAV_LABEL_KEYS.map((key) => CATALOGS[locale].footer[key]);
      expect(labels, `${locale} nav labels must come from the footer keys`).toEqual(expected);
    }
  });

  it('localizes every href through localizedPath', () => {
    for (const locale of ['en', 'es'] as CatalogLocale[]) {
      expect(publicNavLinks(locale).map((link) => link.href)).toEqual(
        PUBLIC_NAV_PATHS.map((path) => localizedPath(path, locale)),
      );
    }
  });
});

describe('the app navbar consumes the shared list', () => {
  it('builds its desktop nav from publicNavLinks, not an inline copy', () => {
    expect(PUBLIC_LAYOUT).toMatch(/publicNavLinks\(/);
    expect(PUBLIC_LAYOUT).not.toMatch(/\{ href: L\('\/docs'\), label: t\.footer\.documentation \}/);
  });
});

describe('the docs header renders its own two-destination list', () => {
  /**
   * The invariant this guard once protected — that the docs header nav equals the app's public
   * nav list — is retired deliberately: the owner decided the docs header shows the app landing
   * page and the status page only, while the app navbar keeps its three destinations
   * (`odd/tasks/docs-header-nav-scope.md`). The cases below pin each surface's list exactly so
   * neither can shrink or grow silently.
   */

  it('keeps the app navbar pinned to exactly the docs, api-reference and status destinations', () => {
    expect([...PUBLIC_NAV_PATHS]).toEqual(['/docs', '/docs/api-reference', '/status']);
    for (const locale of ['en', 'es'] as CatalogLocale[]) {
      const links = publicNavLinks(locale);
      expect(links.map((link) => link.path), `${locale} navbar paths must stay the docs, api-reference and status destinations`).toEqual([
        '/docs',
        '/docs/api-reference',
        '/status',
      ]);
      expect(links.map((link) => link.label)).toEqual(
        NAV_LABEL_KEYS.map((key) => CATALOGS[locale].footer[key]),
      );
    }
  });

  it('renders the docs header list as exactly the app home then the status page', () => {
    expect([...DOCS_HEADER_NAV_PATHS]).toEqual(['/', '/status']);
    for (const locale of ['en', 'es'] as CatalogLocale[]) {
      const links = docsHeaderNavLinks(locale);
      expect(links.map((link) => link.path), `${locale} docs header paths must be exactly / then /status`).toEqual([
        '/',
        '/status',
      ]);
      expect(links.map((link) => link.label)).toEqual([
        CATALOGS[locale].footer.home,
        CATALOGS[locale].footer.status_page,
      ]);
      expect(links.map((link) => link.href)).toEqual(
        DOCS_HEADER_NAV_PATHS.map((path) => localizedPath(path, locale)),
      );
      // localizedPath('/') carries a trailing slash: /en/ and /es/, never the bare prefix.
      expect(links[0].href).toBe(`/${locale}/`);
    }
  });

  it('gives every declared path a label key that exists in both catalogs, and proves the check is not vacuous', () => {
    const expectEveryPathHasLabelKey = (paths: readonly string[], locale: CatalogLocale): void => {
      for (const path of paths) {
        const key = LABEL_KEY_BY_PATH[path];
        expect(key, `declared path '${path}' has no label key`).toBeDefined();
        expect(
          CATALOGS[locale].footer[key as keyof FooterCatalog],
          `label key '${String(key)}' for '${path}' must exist in the ${locale} catalog`,
        ).toBeDefined();
      }
    };

    // Non-vacuity: a synthetic path with no label key must make this check fail loudly, so a
    // future empty or renamed list cannot let the check pass silently.
    expect(() => expectEveryPathHasLabelKey(['/synthetic-path-without-a-key'], 'en')).toThrow();

    const declaredPaths = [...PUBLIC_NAV_PATHS, ...DOCS_HEADER_NAV_PATHS];
    for (const locale of ['en', 'es'] as CatalogLocale[]) {
      expectEveryPathHasLabelKey(declaredPaths, locale);
    }
  });

  it('names no destination and hardcodes no nav label itself', () => {
    expect(HEADER).toMatch(/from '@\/lib\/public-nav'/);
    expect(HEADER).toMatch(/docsHeaderNavLinks\(/);
    expect(HEADER).not.toMatch(/publicNavLinks\(/);
    for (const path of [...PUBLIC_NAV_PATHS, ...DOCS_HEADER_NAV_PATHS]) {
      expect(
        HEADER.includes(`'${path}'`),
        `the docs header must not hardcode the destination '${path}'`,
      ).toBe(false);
    }
    // The bare '/' is checked as a quoted string only: a naked slash would match every closing tag.
    expect(HEADER.includes(`'/'`), `the docs header must not hardcode the destination '/'`).toBe(false);
    expect(HEADER.includes(`"/"`), `the docs header must not hardcode the destination "/"`).toBe(false);

    // Labels: scoped to the template (frontmatter stripped), so the file's doc comment can
    // describe the list without tripping the guard.
    const template = HEADER.replace(/^---[\s\S]*?---/, '');
    for (const label of ['Inicio', 'Home', 'Estado', 'Status']) {
      expect(template.includes(label), `the docs header template must not hardcode the label '${label}'`).toBe(false);
    }
  });

  it('carries the upstream fork marker naming the Starlight version to re-diff against', () => {
    expect(HEADER).toMatch(/@astrojs\/starlight@0\.37\.7/);
  });
});

describe('the docs title override', () => {
  it('links the brand mark to the app home and the docs-home label to the docs home, locale-aware', () => {
    expect(SITE_TITLE).toMatch(/localizedPath/);
    expect(SITE_TITLE).toMatch(/href=\{L\('\/'\)\}/);
    expect(SITE_TITLE).toMatch(/href=\{L\('\/docs'\)\}/);
    // Starlight computes the default href as formatPath(locale); the override must not use it.
    expect(SITE_TITLE).not.toMatch(/siteTitleHref/);
  });

  it('keeps one visible header label, `Storico Docs`, in both locales', () => {
    // A single literal serves both locales: the label is not translated, so the Spanish catalogue
    // carries no copy for it and the neutral-Spanish guard needs no widening.
    expect(SITE_TITLE).toMatch(/>\s*Storico Docs\s*</);
  });
});

/**
 * Source-level approximation only: these checks read the `.astro` template, not the emitted
 * HTML. They exist because the previous version of this guard only asserted that
 * `href={L('/')}` appeared in the file, and the component shipped an anchor nested inside an
 * anchor — invalid HTML, and with no `logo` configured the outer brand anchor serialised
 * empty, leaving the app-home link with no accessible name. The authoritative check is the
 * emitted build output (`.vercel/output/static/<locale>/docs/index.html`), which the parent's
 * verification step reads; this is not a rendering test and must not be described as one.
 */

/** The template with frontmatter and HTML comments removed, so the walk only sees markup. */
function siteTitleTemplate(): string {
  return SITE_TITLE.replace(/^---[\s\S]*?---/, '').replace(/<!--[\s\S]*?-->/g, '');
}

/**
 * Balanced-tag walk over `<a>` / `</a>` only (self-closing `<a ... />` never opens a scope;
 * there are none in this file today, but the guard should not rely on that). Returns the
 * offending opening tag when one anchor opens inside another.
 */
function findNestedAnchor(template: string): string | null {
  const tagRe = /<((?:\/(a\b))|a\b)[^>]*>/g;
  let depth = 0;
  let match: RegExpExecArray | null;
  while ((match = tagRe.exec(template)) !== null) {
    const tag = match[0];
    if (match[1].startsWith('/')) {
      depth = Math.max(depth - 1, 0);
    } else if (!/\/>$/.test(tag)) {
      if (depth > 0) return tag;
      depth++;
    }
  }
  return null;
}

/** The body of the brand anchor — the one whose href is `L('/')` — up to its closing tag. */
function brandAnchorBody(template: string): string | null {
  const open = template.match(/<a\b[^>]*href=\{L\('\/'\)\}[^>]*>/);
  if (!open || open.index === undefined) return null;
  const close = template.indexOf('</a>', open.index + open[0].length);
  return close === -1 ? null : template.slice(open.index + open[0].length, close);
}

describe('the docs title override stays structurally valid (source-level approximation)', () => {
  it('never nests one anchor inside another in the template', () => {
    const violation = findNestedAnchor(siteTitleTemplate());
    expect(violation, `anchor nested inside another: ${violation ?? 'n/a'}`).toBeNull();
  });

  it('gives the brand anchor a visible label source (logo img or t.app.name)', () => {
    const body = brandAnchorBody(siteTitleTemplate());
    expect(body, `brand anchor <a href={L('/')}> not found in the template`).not.toBeNull();
    expect(body).toMatch(/<img\b|t\.app\.name/);
  });
});

describe('the Starlight component overrides stay wired', () => {
  const components = starlightComponentsBlock();

  it('finds the components block, or every case below is vacuous', () => {
    expect(components).not.toBe('');
    expect(components).toMatch(/Head:/);
  });

  it('wires SiteTitle to the override file', () => {
    expect(components).toMatch(/SiteTitle:\s*'\.\/src\/components\/starlight\/SiteTitle\.astro'/);
  });

  it('wires Header to the override file', () => {
    expect(components).toMatch(/Header:\s*'\.\/src\/components\/starlight\/Header\.astro'/);
  });
});
