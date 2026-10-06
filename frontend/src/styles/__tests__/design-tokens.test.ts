// @vitest-environment node
//
// This guard reads `globals.css` off the real filesystem, so it needs a real path: jsdom hands
// out `http://localhost/...` URLs for `import.meta.url`, and `readFileSync` refuses those. The
// node environment keeps this file out of the jsdom suite instead of making the paths depend on
// the working directory.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const CSS = readFileSync(new URL('../globals.css', import.meta.url), 'utf8');

/**
 * The warning and destructive families promoted in `globals.css`, with the exact values they
 * must carry. These are Tailwind ramp steps copied from `node_modules/tailwindcss/theme.css`,
 * not taste — see the comments on the declarations themselves.
 *
 * `--color-warning` and `--color-destructive` are deliberately absent from the dark table:
 * like `--color-success`, they are theme-invariant accents with no dark override.
 */
const LIGHT_TOKENS = {
  '--color-warning': 'oklch(0.769 0.188 70.08)',
  '--color-warning-bg': 'oklch(0.987 0.022 95.277)',
  '--color-warning-border': 'oklch(0.924 0.12 95.746)',
  '--color-warning-text': 'oklch(0.473 0.137 46.201)',
  '--color-destructive-bg': 'oklch(0.971 0.013 17.38)',
  '--color-destructive-border': 'oklch(0.885 0.062 18.334)',
  '--color-destructive-text': 'oklch(0.444 0.177 26.899)',
} as const;

const DARK_TOKENS = {
  '--color-warning-bg': 'oklch(0.279 0.077 45.635 / 0.3)',
  '--color-warning-border': 'oklch(0.414 0.112 45.904)',
  '--color-warning-text': 'oklch(0.879 0.169 91.605)',
  '--color-destructive-bg': 'oklch(0.258 0.092 26.042 / 0.3)',
  '--color-destructive-border': 'oklch(0.396 0.141 25.723)',
  '--color-destructive-text': 'oklch(0.808 0.114 19.571)',
} as const;

/** Every `--color-*` declaration in the file, in source order, with its character offset. */
const DECLARATIONS = [...CSS.matchAll(/--color-[\w-]+\s*:\s*([^;]+);/g)].map((match) => ({
  name: match[0].slice(0, match[0].indexOf(':')).trim(),
  value: match[1].trim(),
  index: match.index ?? -1,
}));

/**
 * The first line of the dark override block. Its single-quoted form is unique: the
 * `@custom-variant dark` line above it uses double quotes, so this index can only be the
 * selector the overrides live under.
 */
const DARK_BLOCK_START = CSS.indexOf(":root[data-theme='dark']");

/**
 * Scope membership by source position: a light declaration must sit before the dark selector
 * and a dark declaration after it.
 *
 * Limitation, stated rather than overclaimed: this asserts *ordering*, not block membership.
 * A declaration placed after the light `@theme` block but still before the dark selector
 * (say, in some future rule between the two) would pass the light check, and a declaration
 * after the dark block's closing brace would pass the dark one. The exact-value assertions
 * are the real lock; this check only guarantees the value lives on the right side of the
 * theme split.
 */
const LIGHT_DECLARATIONS = DECLARATIONS.filter((decl) => decl.index < DARK_BLOCK_START);
const DARK_DECLARATIONS = DECLARATIONS.filter((decl) => decl.index > DARK_BLOCK_START);

function declaredIn(
  declarations: { name: string; value: string }[],
  name: string,
  value: string,
): boolean {
  return declarations.some((decl) => decl.name === name && decl.value === value);
}

describe('the token parse is not vacuous', () => {
  it('finds the dark override block, or every scope check below is meaningless', () => {
    expect(DARK_BLOCK_START).toBeGreaterThan(-1);
  });

  it('parses at least the declarations it is responsible for, so a broken regex fails loudly', () => {
    expect(DECLARATIONS.length).toBeGreaterThanOrEqual(
      Object.keys(LIGHT_TOKENS).length + Object.keys(DARK_TOKENS).length,
    );
  });
});

describe('light-scope tokens', () => {
  it('declares each token with its exact value before the dark block', () => {
    for (const [name, value] of Object.entries(LIGHT_TOKENS)) {
      expect(
        declaredIn(LIGHT_DECLARATIONS, name, value),
        `${name} must be ${value} in the light scope`,
      ).toBe(true);
    }
  });
});

describe('dark-scope tokens', () => {
  it('declares each token with its exact value inside the dark block', () => {
    for (const [name, value] of Object.entries(DARK_TOKENS)) {
      expect(
        declaredIn(DARK_DECLARATIONS, name, value),
        `${name} must be ${value} in the dark scope`,
      ).toBe(true);
    }
  });

  it('does not add dark overrides for the theme-invariant accents', () => {
    for (const accent of ['--color-warning', '--color-destructive']) {
      expect(
        DARK_DECLARATIONS.filter((decl) => decl.name === accent),
        `${accent} must stay theme-invariant, like --color-success`,
      ).toEqual([]);
    }
  });
});

describe('theme split', () => {
  it('gives the shared trio tokens genuinely different light and dark values', () => {
    for (const name of Object.keys(DARK_TOKENS)) {
      const light = LIGHT_DECLARATIONS.filter((decl) => decl.name === name);
      const dark = DARK_DECLARATIONS.filter((decl) => decl.name === name);
      expect(light.length, `${name} is declared once in the light scope`).toBe(1);
      expect(dark.length, `${name} is declared once in the dark scope`).toBe(1);
      expect(
        light[0]!.value,
        `${name}: light and dark must not carry the same value`,
      ).not.toBe(dark[0]!.value);
    }
  });
});
