// @vitest-environment node
//
// This guard reads the two font-link consumers off disk — an Astro layout and a Starlight
// head override — so it needs a real filesystem path: jsdom hands out `http://localhost/...`
// URLs for `import.meta.url`, and `readFileSync` refuses those. The node environment keeps
// this file out of the jsdom suite instead of making the paths depend on the working
// directory.
//
// Why this guard exists: the app's web fonts used to be written out as a literal Google
// Fonts <link> in PublicLayout.astro only, so every surface that does not render through
// that layout — the Starlight docs pages — silently loaded no web fonts at all while
// declaring `--sl-font: Inter`. `document.fonts.check()` cannot catch this (it returns true
// for a family with no @font-face), so the drift is guarded here instead: one constant, two
// consumers, and neither may embed a font URL of its own.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

import {
  GOOGLE_FONTS_STYLESHEET_HREF,
  GOOGLE_FONTS_PRECONNECT_HOSTS,
  FONT_FAMILIES,
} from '@/lib/fonts';

/** Consumers that must load the app's fonts through the shared constant. */
const CONSUMER_SOURCES = Object.fromEntries(
  [
    'layouts/PublicLayout.astro',
    'components/starlight/Head.astro',
  ].map((relativePath) => [
    relativePath,
    readFileSync(new URL(`../../${relativePath}`, import.meta.url), 'utf8'),
  ]),
);

describe('web font single source of truth', () => {
  it('the consumers are read for real (non-vacuity)', () => {
    // If the path or the file content ever changes shape, every assertion below could
    // otherwise pass against an empty string. Each marker is stable structural content of
    // its file, not the font links themselves.
    expect(CONSUMER_SOURCES['layouts/PublicLayout.astro']).toContain('ClientRouter');
    expect(CONSUMER_SOURCES['components/starlight/Head.astro']).toContain('starlightRoute');
  });

  it('names exactly the three families the app loads, with the weights each is loaded at', () => {
    expect(FONT_FAMILIES).toEqual(['Inter', 'Space Grotesk', 'Geist Mono']);

    // The stylesheet href must request each declared family; a family named here but absent
    // from the URL would render in a fallback the constant does not describe.
    for (const family of FONT_FAMILIES) {
      expect(GOOGLE_FONTS_STYLESHEET_HREF).toContain(`family=${family.replace(/ /g, '+')}:`);
    }
    // And nothing beyond the declared families may sneak into the URL.
    const requested = [...GOOGLE_FONTS_STYLESHEET_HREF.matchAll(/family=([^&:]+)/g)].map(
      ([, family]) => family.replace(/\+/g, ' '),
    );
    expect(requested).toEqual([...FONT_FAMILIES]);
  });

  it('declares the two Google Fonts preconnect hosts with their crossorigin flags', () => {
    expect(GOOGLE_FONTS_PRECONNECT_HOSTS).toEqual([
      { host: 'https://fonts.googleapis.com', crossorigin: false },
      { host: 'https://fonts.gstatic.com', crossorigin: true },
    ]);
  });

  describe.each(Object.entries(CONSUMER_SOURCES))('%s', (path, source) => {
    it('loads the fonts through the shared constant, not an embedded URL', () => {
      expect(source).toContain('from \'@/lib/fonts\'');
      expect(source).toContain('GOOGLE_FONTS_STYLESHEET_HREF');
      // Reintroducing a literal font URL here is exactly the drift this guard exists for:
      // the two surfaces would load different faces while the constant claims otherwise.
      expect(source, `${path} must not embed its own fonts.googleapis.com URL`).not.toContain(
        'fonts.googleapis.com/css2',
      );
      expect(source, `${path} must not embed its own preconnect host`).not.toContain(
        'fonts.googleapis.com"',
      );
      expect(source, `${path} must not embed its own preconnect host`).not.toContain(
        'fonts.gstatic.com',
      );
    });
  });
});
