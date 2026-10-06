// @vitest-environment node
//
// This guard reads `starlight.css` and `globals.css` off the real filesystem, so it needs a real
// path: jsdom hands out `http://localhost/...` URLs for `import.meta.url`, and `readFileSync`
// refuses those. The node environment keeps this file out of the jsdom suite instead of making
// the paths depend on the working directory. Same technique as its sibling
// `design-tokens.test.ts`.
//
// What this guard is, and what it is not: it is a **source-level** guard. It proves that the
// token mirrors in `starlight.css` agree with `globals.css` and that every token the docs theme
// references is declared somewhere it can actually resolve. It does NOT prove that any colour
// renders correctly on a docs page — that is a browser pass's job, and the two are not
// substitutes.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const STARLIGHT_RAW = readFileSync(new URL('../starlight.css', import.meta.url), 'utf8');
const GLOBALS_RAW = readFileSync(new URL('../globals.css', import.meta.url), 'utf8');

/** Removes block comments so prose can never masquerade as a declaration or a selector. */
function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, ' ');
}

interface Decl {
  name: string;
  value: string;
  index: number;
}

/** Every custom-property declaration, in source order, with its character offset. */
function declarations(css: string): Decl[] {
  return [...css.matchAll(/(--[\w-]+)\s*:\s*([^;{}]+);/g)].map((match) => ({
    name: match[1]!,
    value: match[2]!.trim(),
    index: match.index ?? -1,
  }));
}

interface Rule {
  selector: string;
  body: string;
}

/**
 * Flat top-level rules of `starlight.css` only. The file has no nesting and no at-rules with
 * bodies, so a brace-flat scan is exact there; it would NOT be on globals.css (whose `@layer`
 * nests), which is why globals.css is only ever parsed positionally below.
 */
function rules(css: string): Rule[] {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
    selector: match[1]!.trim(),
    body: match[2]!,
  }));
}

const SL = stripComments(STARLIGHT_RAW);
const GL = stripComments(GLOBALS_RAW);
const SL_DECLS = declarations(SL);
const GL_DECLS = declarations(GL);

/** The files' dark selectors, single-quoted so they cannot hit a double-quoted variant line. */
const SL_DARK_IDX = SL.indexOf(":root[data-theme='dark'] {");
const GL_DARK_IDX = GL.indexOf(":root[data-theme='dark'],");

/**
 * Scope membership by source position, in both files alike: a declaration before the file's dark
 * selector belongs to the light scope, one after it to the dark scope. globals.css gets its dark
 * values from the very same positional rule, so the two files are compared on equal terms.
 *
 * Limitation, stated rather than overclaimed: this asserts ordering, not block membership. In
 * starlight.css the two Starlight mapping blocks sit after the dark selector and are therefore
 * positionally "dark", but they declare only `--sl-*` tokens, so no `--color-*` / `--font-*`
 * comparison is affected. A declaration after a dark block's closing brace would also count as
 * dark. The exact-value assertions are the real lock; this only guarantees each value lives on
 * the right side of the theme split.
 *
 * Within one scope, a token declared twice keeps its LAST value — the same winner CSS cascade
 * would pick for equal-specificity declarations.
 */
function scopeValues(decls: Decl[], darkIdx: number) {
  const light = new Map<string, string>();
  const dark = new Map<string, string>();
  for (const decl of decls) {
    (decl.index < darkIdx ? light : dark).set(decl.name, decl.value);
  }
  return { light, dark };
}

const SL_SCOPES = scopeValues(SL_DECLS, SL_DARK_IDX);
const GL_SCOPES = scopeValues(GL_DECLS, GL_DARK_IDX);

/** Tokens declared in BOTH files — the only ones a drift assertion can say anything about. */
const SHARED_TOKENS = [...SL_SCOPES.light.keys(), ...SL_SCOPES.dark.keys()].filter(
  (name, index, all) =>
    all.indexOf(name) === index &&
    (GL_SCOPES.light.has(name) || GL_SCOPES.dark.has(name)),
);

/** Effective value in a theme: the dark declaration if there is one, else the light one —
 * because a token declared in only one scope is inherited by the other in both files alike. */
function effectiveValue(
  scopes: { light: Map<string, string>; dark: Map<string, string> },
  name: string,
  theme: 'light' | 'dark',
): string | undefined {
  if (theme === 'light') return scopes.light.get(name);
  return scopes.dark.get(name) ?? scopes.light.get(name);
}

const SL_RULES = rules(SL);
/** Block 3: the `:root` block that maps Starlight's ramp — Starlight's dark default scope. */
const DARK_MAPPING_BLOCK = SL_RULES.find(
  (rule) => rule.selector === ':root' && rule.body.includes('--sl-color-bg:'),
);
/** Block 4: the same mapping for the explicit light scope. */
const LIGHT_MAPPING_BLOCK = SL_RULES.find((rule) => rule.selector === ":root[data-theme='light']");

/** Every `--color-*` token referenced through `var(...)` anywhere in starlight.css. */
const REFERENCED_COLOR_TOKENS = [
  ...new Set([...SL.matchAll(/var\(\s*(--color-[\w-]+)/g)].map((match) => match[1]!)),
];
const DECLARED_SL_NAMES = new Set(SL_DECLS.map((decl) => decl.name));

const ASIDE_CLASSES = ['note', 'tip', 'caution', 'danger'] as const;

function asideRules(cls: (typeof ASIDE_CLASSES)[number]): Rule[] {
  return SL_RULES.filter((rule) => rule.selector.includes(`.starlight-aside--${cls}`));
}

/** Starlight's raw callout hues, including their `-low` / `-high` forms. */
const STARLIGHT_RAW_HUES = /--sl-color-(?:blue|purple|orange|red)(?:-(?:low|high))?/;

describe('the parse is not vacuous', () => {
  it('finds both files’ dark selectors, or every scope check below is meaningless', () => {
    expect(SL_DARK_IDX, 'starlight.css dark selector').toBeGreaterThan(-1);
    expect(GL_DARK_IDX, 'globals.css dark selector').toBeGreaterThan(-1);
  });

  it('parses at least the declarations the assertions need, so a broken regex fails loudly', () => {
    // The finished file carries 44 `--color-*` mirrors plus the two `--font-*` mirrors; a broken
    // declaration regex yields a handful at most.
    expect(SL_DECLS.length).toBeGreaterThanOrEqual(40);
  });

  it('finds at least the var() references the assertions need', () => {
    expect(REFERENCED_COLOR_TOKENS.length).toBeGreaterThanOrEqual(20);
  });

  it('finds at least the shared tokens the drift assertion needs', () => {
    expect(SHARED_TOKENS.length).toBeGreaterThanOrEqual(15);
  });

  it('finds both Starlight mapping blocks, or the scrim/sidebar checks are meaningless', () => {
    expect(DARK_MAPPING_BLOCK, 'dark mapping block (:root with --sl-color-bg:)').toBeDefined();
    expect(LIGHT_MAPPING_BLOCK, 'light mapping block (:root[data-theme=light])').toBeDefined();
  });
});

describe('self-containment', () => {
  it('declares every --color-* token it references', () => {
    // globals.css never loads on Starlight pages (the docs render through Starlight's own
    // layout, not PublicLayout), so a referenced-but-undeclared token resolves to nothing: an
    // invisible surface, with no build error and no failing test to catch it.
    const unbacked = REFERENCED_COLOR_TOKENS.filter((name) => !DECLARED_SL_NAMES.has(name));
    expect(
      unbacked,
      'starlight.css references --color-* tokens it never declares; on a docs page they ' +
        'resolve to nothing because globals.css is not loaded there',
    ).toEqual([]);
  });
});

describe('drift against globals.css', () => {
  it('carries the identical value per theme for every token declared in both files', () => {
    for (const name of SHARED_TOKENS) {
      for (const theme of ['light', 'dark'] as const) {
        const globalsValue = effectiveValue(GL_SCOPES, name, theme);
        const starlightValue = effectiveValue(SL_SCOPES, name, theme);
        if (globalsValue === undefined || starlightValue === undefined) continue;
        expect(
          starlightValue,
          `${name} (${theme}) drifted from globals.css: starlight.css says ` +
            `"${starlightValue}", globals.css says "${globalsValue}". A value change in ` +
            'globals.css must be mirrored in starlight.css by hand, verbatim.',
        ).toBe(globalsValue);
      }
    }
  });
});

describe('the callout mappings', () => {
  it('styles each of the four aside classes from --color-* tokens', () => {
    for (const cls of ASIDE_CLASSES) {
      const matched = asideRules(cls);
      expect(matched.length, `.starlight-aside--${cls} must be styled`).toBeGreaterThan(0);
      for (const rule of matched) {
        expect(
          rule.body,
          `.starlight-aside--${cls} must set its colours from var(--color-…), not literals`,
        ).toMatch(/var\(--color-/);
      }
    }
  });

  it('gives tip, caution and danger exactly one rule each — their trios flip with the theme', () => {
    for (const cls of ['tip', 'caution', 'danger'] as const) {
      expect(asideRules(cls).length, `.starlight-aside--${cls} rule count`).toBe(1);
    }
  });

  it('gives note a dark-scoped variant, because the primary ramp is theme-invariant', () => {
    expect(
      SL_RULES.some((rule) => /:root\[data-theme='dark'\]\s+\.starlight-aside--note/.test(rule.selector)),
      'the note callout needs a :root[data-theme=dark] rule for its primary ramp steps',
    ).toBe(true);
  });

  it('names no raw Starlight hue inside any callout rule', () => {
    const bodies = ASIDE_CLASSES.flatMap(asideRules).map((rule) => rule.body);
    const offenders = bodies.filter((body) => STARLIGHT_RAW_HUES.test(body));
    // The hue ramp is shared with Card, Badge, Footer and ContentNotice; these rules must
    // recolour the asides without touching it.
    expect(offenders).toEqual([]);
  });
});

describe('the scrim and the sidebar', () => {
  it('declares --sl-color-backdrop-overlay from an app token, in both mapping blocks', () => {
    // Starlight declares the scrim in both theme scopes, so a single declaration would lose to
    // the light scope on specificity — it must exist in both.
    const backdrop = SL_DECLS.filter((decl) => decl.name === '--sl-color-backdrop-overlay');
    expect(backdrop.length, '--sl-color-backdrop-overlay declaration count').toBe(2);
    for (const decl of backdrop) {
      expect(decl.value, 'the scrim must be tinted from an app token').toContain('var(--color-');
    }
    expect(
      DARK_MAPPING_BLOCK!.body.includes('--sl-color-backdrop-overlay:'),
      'scrim declared in the dark mapping block',
    ).toBe(true);
    expect(
      LIGHT_MAPPING_BLOCK!.body.includes('--sl-color-backdrop-overlay:'),
      'scrim declared in the light mapping block',
    ).toBe(true);
  });

  it('maps --sl-color-bg-sidebar to --color-sidebar in both mapping blocks', () => {
    expect(
      DARK_MAPPING_BLOCK!.body.includes('--sl-color-bg-sidebar: var(--color-sidebar)'),
      'dark mapping block must map the sidebar background to --color-sidebar',
    ).toBe(true);
    expect(
      LIGHT_MAPPING_BLOCK!.body.includes('--sl-color-bg-sidebar: var(--color-sidebar)'),
      'light mapping block must map the sidebar background to --color-sidebar',
    ).toBe(true);
  });
});
