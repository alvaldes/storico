// @vitest-environment node
//
// This guard walks the whole `frontend/src` tree off the real filesystem, so it needs real
// paths: jsdom hands out `http://localhost/...` URLs for `import.meta.url`, and `readFileSync`
// refuses those. The node environment keeps this file out of the jsdom suite instead of making
// the paths depend on the working directory.
//
// ── The class of bug this prevents ───────────────────────────────────────────────────
//
// A CSS custom-property reference that resolves to nothing is *invalid at computed-value
// time*: the property collapses to `unset` silently — no console error, no failed build, no
// broken test. Six names shipped that way once (`--color-surface-tertiary`,
// `--radix-dropdown-menu-trigger-width`, `--secondary`, `--foreground`, `--sidebar-border`,
// `--sidebar-accent`); the guard exists so a seventh cannot.
//
// Both reference syntaxes count, and both must be scanned:
//   1. `var(--name)` / `var(--name, fallback)` — plain CSS.
//   2. Tailwind v4's arbitrary-value shorthand `(--name)`, as in `bg-(--color-x)` or
//      `w-(--sidebar-width)`. Four of the six broken names appeared ONLY in this form, so a
//      guard that only greps `var(` would have missed them entirely.
//
// Declarations are collected only from CSS positions (`.css` files, `<style>` spans in
// `.astro`, quoted inline-style keys, Tailwind arbitrary properties `[--x:…]`) and CSS comments
// are stripped before the stylesheet scan, so a comment mentioning `--x:` cannot declare a token
// and silently mask a broken reference. TypeScript and Astro prose is never scanned for the
// stylesheet form: the quoted-key and bracket patterns below require a shape a comment would have
// to mimic deliberately, and each one still has to survive the resolution rule.
//
// A reference with a fallback is EXEMPT — `var(--x, 0rem)` is the explicit statement that the
// token is optional.
//
// Measured limitation, documented rather than enforced: a name declared inside an
// `@theme inline` block is emitted by Tailwind only when the scanner sees a reference to it
// somewhere in the source. A raw `var()` reference to such a name is therefore fragile — it
// resolves today only because Tailwind happened to notice some other reference.
// `ui/sonner.tsx`'s `var(--color-popover)` works today precisely because of that. Enforcing
// this would require an allowlist for working code, so the rule is left as prose.
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, realpathSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// ── Reference extraction ─────────────────────────────────────────────────────────────

const CUSTOM_PROPERTY_NAME = '[A-Za-z0-9_-]+';
const IS_CUSTOM_PROPERTY_NAME = new RegExp(`^--${CUSTOM_PROPERTY_NAME}$`);

/** Tailwind v4's arbitrary-value shorthand: `bg-(--name)`, `w-(--name)`, ... */
const SHORTHAND_REFERENCE = new RegExp(`\\((--${CUSTOM_PROPERTY_NAME})\\)`, 'g');

export interface Reference {
  name: string;
  hasFallback: boolean;
  index: number;
}

/** Index of the `)` closing the `(` at `afterOpen`, or -1 when the parentheses are unbalanced. */
function matchingParenEnd(source: string, afterOpen: number): number {
  let depth = 1;
  for (let i = afterOpen; i < source.length; i++) {
    if (source[i] === '(') depth++;
    else if (source[i] === ')' && --depth === 0) return i;
  }
  return -1;
}

/** Index of the first `,` outside any parentheses in `text`, or -1 when there is none. */
function topLevelCommaIndex(text: string): number {
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '(') depth++;
    else if (text[i] === ')') depth--;
    else if (text[i] === ',' && depth === 0) return i;
  }
  return -1;
}

/**
 * Collect every `var()` reference in `source` into `references`, and the character span each one
 * occupies into `spans` (the shorthand scan below needs the spans). `base` is the offset of
 * `source` within the file, so recursive calls report absolute indices.
 *
 * The parentheses are walked, not pattern-matched, because a reference inside another
 * reference's FALLBACK is itself a reference: `var(--outer, var(--inner))` must report
 * `--outer` as fallback-carrying and `--inner` as carrying none. A pattern that swallowed the
 * nested span would report only `--outer`, and an unresolved `--inner` could hide there
 * forever — the exact failure mode this file exists to catch.
 */
function collectVarReferences(
  source: string,
  base: number,
  references: Reference[],
  spans: Array<[number, number]>,
): void {
  const opener = /var\(/g;
  let match: RegExpExecArray | null;
  while ((match = opener.exec(source)) !== null) {
    const afterOpen = match.index + match[0].length;
    const close = matchingParenEnd(source, afterOpen);
    // Unbalanced parentheses: nothing safe to judge, so judge nothing rather than guess.
    if (close === -1) continue;
    spans.push([base + match.index, base + close + 1]);

    const inner = source.slice(afterOpen, close);
    const comma = topLevelCommaIndex(inner);
    const headEnd = comma === -1 ? inner.length : comma;
    const head = inner.slice(0, headEnd).trim();

    if (IS_CUSTOM_PROPERTY_NAME.test(head)) {
      references.push({ name: head, hasFallback: comma !== -1, index: base + match.index });
    } else if (inner.slice(0, headEnd).includes('var(')) {
      // No name before the comma, so only a nested `var()` can be at stake in that position.
      collectVarReferences(inner.slice(0, headEnd), base + afterOpen, references, spans);
    }
    if (comma !== -1) {
      collectVarReferences(inner.slice(comma + 1), base + afterOpen + comma + 1, references, spans);
    }
    // Do not rescan the contents: the recursion above already covered the fallback position.
    opener.lastIndex = close + 1;
  }
}

/**
 * Every custom-property reference in a source string, in source order.
 *
 * `var(...)` spans are blanked with spaces before the shorthand scan: the shorthand pattern
 * `\((--x)\)` would otherwise also match the `(--x)` inside `var(--x, fallback)` and lose the
 * fallback information.
 */
export function referencesIn(source: string): Reference[] {
  const references: Reference[] = [];
  const spans: Array<[number, number]> = [];
  collectVarReferences(source, 0, references, spans);

  // `split('')` splits by UTF-16 code unit, which is what a regex `index` counts. `[...source]`
  // would split by code point and misalign every offset after the first surrogate pair.
  const blanked = source.split('');
  for (const [start, end] of spans) {
    for (let i = start; i < end; i++) blanked[i] = ' ';
  }
  for (const match of blanked.join('').matchAll(SHORTHAND_REFERENCE)) {
    references.push({ name: match[1]!, hasFallback: false, index: match.index! });
  }

  return references.sort((left, right) => left.index - right.index);
}

// ── Declaration extraction ───────────────────────────────────────────────────────────

/**
 * A `--name:` declaration inside real CSS text. The caller strips CSS comments first, so this
 * needs no boundary class at all: a boundary class can only ever be an incomplete guess at the
 * characters that may precede a declaration — `{`, `;`, whitespace and a quote are the common
 * ones, but `>` (a `<style>` span opening straight onto a declaration) and the very first
 * character of a file are just as valid. Guessing drops declarations, and a dropped declaration
 * makes the guard call a broken reference resolved, which is the failure this file exists to
 * prevent.
 */
const CSS_DECLARATION = new RegExp(`(--${CUSTOM_PROPERTY_NAME})\\s*:`, 'g');

/**
 * Blank out CSS block comments before scanning. This is what lets `CSS_DECLARATION` skip the
 * boundary class: a comment mentioning `--x:` must not be able to declare a token and mask a
 * broken reference. CSS has no line comments, so there is no `https://` style pitfall here.
 */
function stripCssComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, (comment) => ' '.repeat(comment.length));
}

/** A quoted inline-style key: `'--name':` or `"--name":` inside a TS/TSX style object. */
const QUOTED_DECLARATION = new RegExp(`['"](--${CUSTOM_PROPERTY_NAME})['"]\\s*:`, 'g');

/** A Tailwind arbitrary property inside a class string: `[--name:…]`. */
const BRACKET_DECLARATION = new RegExp(`\\[(--${CUSTOM_PROPERTY_NAME})\\s*:`, 'g');

export function declaredNamesInCssPositions(source: string): string[] {
  return [...stripCssComments(source).matchAll(CSS_DECLARATION)].map((match) => match[1]!);
}

function declaredNamesEverywhere(source: string): string[] {
  return [
    ...[...source.matchAll(QUOTED_DECLARATION)].map((match) => match[1]!),
    ...[...source.matchAll(BRACKET_DECLARATION)].map((match) => match[1]!),
  ];
}

// ── The source walk ──────────────────────────────────────────────────────────────────

/** frontend/src, resolved off this file's own URL — never off the working directory. */
const SOURCE_ROOT = fileURLToPath(new URL('../../', import.meta.url));

const SOURCE_EXTENSIONS = ['.css', '.astro', '.ts', '.tsx'];

function collectSourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (!entry.isFile() || !SOURCE_EXTENSIONS.some((ext) => entry.name.endsWith(ext))) continue;
    // Tests are allowed to name arbitrary tokens (this file does); only app source is policed.
    if (entry.parentPath.split(/[\\/]/).includes('__tests__')) continue;
    found.push(join(entry.parentPath, entry.name));
  }
  return found;
}

const SOURCE_FILES = collectSourceFiles(SOURCE_ROOT);

function lineStartsOf(source: string): number[] {
  const starts = [0];
  for (let i = 0; i < source.length; i++) {
    if (source[i] === '\n') starts.push(i + 1);
  }
  return starts;
}

function lineOf(lineStarts: number[], index: number): number {
  // linear scan is fine at this file size and keeps the guard free of binary-search tricks
  let line = 0;
  while (line + 1 < lineStarts.length && lineStarts[line + 1]! <= index) line++;
  return line + 1;
}

interface ReferenceOccurrence extends Reference {
  file: string;
  line: number;
}

const REFERENCES: ReferenceOccurrence[] = SOURCE_FILES.flatMap((file) => {
  const source = readFileSync(file, 'utf8');
  const lineStarts = lineStartsOf(source);
  return referencesIn(source).map((reference) => ({
    ...reference,
    file,
    line: lineOf(lineStarts, reference.index),
  }));
});

// ── Declarations, from CSS positions only ────────────────────────────────────────────

/**
 * The real stylesheet text of a source file, or null when the file holds none: a `.css` file
 * wholesale, the `<style>` spans of an `.astro` component, and nothing at all for TypeScript
 * (where a declaration can only appear as a quoted inline-style key or a Tailwind arbitrary
 * property, both collected separately below).
 *
 * Splitting this out is what lets the suite prove, on synthetic input, that an Astro
 * component's markup and frontmatter are excluded and that a `<style>` span opening straight
 * onto a declaration is included.
 */
export function cssTextIn(file: string, source: string): string | null {
  if (file.endsWith('.css')) return source;
  if (!file.endsWith('.astro')) return null;
  return [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)]
    .map((span) => span[1]!)
    .join('\n');
}

const DECLARED_NAMES = new Set<string>();

for (const file of SOURCE_FILES) {
  const source = readFileSync(file, 'utf8');
  const cssText = cssTextIn(file, source);
  if (cssText !== null) {
    for (const name of declaredNamesInCssPositions(cssText)) DECLARED_NAMES.add(name);
  }
  // every file: quoted inline-style keys and Tailwind arbitrary properties
  for (const name of declaredNamesEverywhere(source)) DECLARED_NAMES.add(name);
}

// ── Externally provided token sets ───────────────────────────────────────────────────
//
// Both packages are pnpm symlinks into `node_modules/.pnpm/…`. They are resolved with
// `fs.realpathSync` before walking: `readdirSync(dir, { recursive: true })` does NOT follow
// symlinked directories, so walking the unresolved path derives an EMPTY set and every
// reference then looks broken.

/** frontend/node_modules, resolved off this file's own URL. */
const NODE_MODULES = fileURLToPath(new URL('../../../node_modules/', import.meta.url));

function walkFiles(root: string, keep: (name: string) => boolean): string[] {
  const found: string[] = [];
  const visit = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.isFile() && keep(entry.name)) found.push(full);
    }
  };
  visit(root);
  return found;
}

/** Starlight's shipped stylesheet declares the `--sl-*` tokens its components reference. */
const STARLIGHT_TOKENS = new Set<string>();
for (const file of walkFiles(
  realpathSync(join(NODE_MODULES, '@astrojs/starlight/style')),
  (name) => name.endsWith('.css'),
)) {
  for (const name of declaredNamesInCssPositions(readFileSync(file, 'utf8'))) {
    STARLIGHT_TOKENS.add(name);
  }
}

/** Base UI injects these variables at runtime into positioned popups and similar elements. */
const BASE_UI_TOKENS = new Set<string>();
for (const file of walkFiles(
  realpathSync(join(NODE_MODULES, '@base-ui/react')),
  (name) => name.includes('CssVars') && (name.endsWith('.mjs') || name.endsWith('.js')),
)) {
  for (const match of readFileSync(file, 'utf8').matchAll(/['"](--[A-Za-z0-9_-]+)['"]/g)) {
    BASE_UI_TOKENS.add(match[1]!);
  }
}

// ── The rule ─────────────────────────────────────────────────────────────────────────
//
// Fail on a reference when ALL of these hold: it has no fallback, the name is not declared
// anywhere in frontend/src, and the name is not in either external set.

function isResolved(reference: { name: string; hasFallback: boolean }): boolean {
  return (
    reference.hasFallback ||
    DECLARED_NAMES.has(reference.name) ||
    STARLIGHT_TOKENS.has(reference.name) ||
    BASE_UI_TOKENS.has(reference.name)
  );
}

/**
 * The rule above, applied to a single source string, returning the names that resolve to
 * nothing. Exported so the suite can prove the rule FIRES on a synthetic undeclared name and
 * CLEARS on a synthetic declared one: a resolution rule that only ever ran over the real tree
 * could be vacuously true — an over-broad declaration pattern would resolve everything and no
 * test would notice.
 */
export function unresolvedIn(source: string): string[] {
  return [
    ...new Set(
      referencesIn(source)
        .filter((reference) => !isResolved(reference))
        .map((reference) => reference.name),
    ),
  ].sort();
}

const UNRESOLVED = new Map<string, ReferenceOccurrence[]>();
for (const reference of REFERENCES) {
  if (isResolved(reference)) continue;
  const group = UNRESOLVED.get(reference.name) ?? [];
  group.push(reference);
  UNRESOLVED.set(reference.name, group);
}

const UNRESOLVED_REPORT = [...UNRESOLVED.entries()]
  .map(([name, occurrences]) =>
    [`${name}`, ...occurrences.map((occurrence) => `  ${occurrence.file}:${occurrence.line}`)].join(
      '\n',
    ),
  )
  .join('\n');

// Tokens whose only declaration lives outside static CSS positions (a runtime
// `setProperty`, an external stylesheet) and which therefore rely on their fallback.
const DOCUMENTED_EXEMPT_TOKENS = ['--public-nav-h', '--sl-content-inline-start'];

describe('the reference parse is not vacuous', () => {
  it('walks a substantial part of the source tree, so a broken walk fails loudly instead of passing on an empty list', () => {
    expect(SOURCE_FILES.length).toBeGreaterThanOrEqual(100);
  });

  it('parses at least a substantial number of references, so a broken regex fails loudly', () => {
    expect(REFERENCES.length).toBeGreaterThanOrEqual(100);
  });

  it('parses at least a substantial number of declarations, so a broken declaration scan cannot mask broken references', () => {
    expect(DECLARED_NAMES.size).toBeGreaterThanOrEqual(50);
  });

  it('derives a non-empty Starlight token set from the installed package', () => {
    expect(
      STARLIGHT_TOKENS.size,
      'the Starlight set is empty — the walk probably ran on an unresolved pnpm symlink',
    ).toBeGreaterThan(50);
  });

  it('derives a non-empty Base UI token set from the installed package', () => {
    expect(
      BASE_UI_TOKENS.size,
      'the Base UI set is empty — the walk probably ran on an unresolved pnpm symlink',
    ).toBeGreaterThan(20);
  });
});

describe('the reference detector', () => {
  it('fires on a synthetic source containing an undeclared name in both reference syntaxes', () => {
    const synthetic = [
      '.probe {',
      '  color: var(--undeclared-detector-probe);',
      '  background: var(--fallback-detector-probe, red);',
      '}',
      '.chip { background: bg-(--shorthand-detector-probe); }',
    ].join('\n');

    const found = referencesIn(synthetic);

    const probe = (name: string) => found.filter((reference) => reference.name === name);
    expect(probe('--undeclared-detector-probe')).toHaveLength(1);
    expect(probe('--undeclared-detector-probe')[0]!.hasFallback).toBe(false);
    expect(probe('--fallback-detector-probe')).toHaveLength(1);
    expect(probe('--fallback-detector-probe')[0]!.hasFallback).toBe(true);
    expect(probe('--shorthand-detector-probe')).toHaveLength(1);
    expect(probe('--shorthand-detector-probe')[0]!.hasFallback).toBe(false);
  });

  it('does not double-report a var() reference as a shorthand reference after blanking', () => {
    const found = referencesIn('var(--probe-x)');
    expect(found.filter((reference) => reference.name === '--probe-x')).toHaveLength(1);
  });

  it('reports a reference nested in another reference’s fallback, with the fallback of each one', () => {
    const found = referencesIn('color: var(--outer-probe, var(--inner-probe));');

    expect(found.map((reference) => [reference.name, reference.hasFallback])).toEqual([
      ['--outer-probe', true],
      ['--inner-probe', false],
    ]);
  });

  it('returns references in source order across both syntaxes', () => {
    const found = referencesIn('a: bg-(--first-probe)\n\ncolor: var(--second-probe);');

    expect(found.map((reference) => reference.name)).toEqual(['--first-probe', '--second-probe']);
  });
});

describe('the declaration scan is not vacuous', () => {
  it('takes a stylesheet from a .css file and from the <style> spans of an .astro component, and nothing else', () => {
    expect(cssTextIn('a.css', '.x { --a: 1rem; }')).toBe('.x { --a: 1rem; }');
    expect(
      cssTextIn('a.astro', '---\n// prose --b: 2\n---\n<div />\n<style>--c: 1rem;</style>'),
      'only the <style> span is a declaration position; frontmatter and markup are not',
    ).toBe('--c: 1rem;');
    expect(cssTextIn('a.tsx', "const className = 'style';")).toBeNull();
  });

  it('recognises a declaration at every real CSS boundary, including the first character a <style> span hands over', () => {
    expect(declaredNamesInCssPositions('--a: 1rem;')).toEqual(['--a']);
    expect(declaredNamesInCssPositions('.x { --b: 1rem; }')).toEqual(['--b']);
    expect(declaredNamesInCssPositions('[--c:--spacing(4)]')).toEqual(['--c']);
    expect(declaredNamesInCssPositions('.x {\n  --d: 1rem;\n}')).toEqual(['--d']);
  });

  it('never lets a CSS comment declare a token, so a comment cannot mask a broken reference', () => {
    expect(
      declaredNamesInCssPositions('/* --not-a-token: hello */\n.x { --real: 1rem; }'),
      'a commented-out declaration must not count as a declaration',
    ).toEqual(['--real']);
  });

  it('recognises the two declaration shapes that live in TypeScript, not in a stylesheet', () => {
    expect(
      declaredNamesEverywhere("style={{ '--sidebar-width': '16rem' }}"),
      'a quoted inline-style key is a declaration',
    ).toContain('--sidebar-width');
    expect(
      declaredNamesEverywhere('className="gap-(--card-spacing) [--card-spacing:--spacing(4)]"'),
      'a Tailwind arbitrary property is a declaration',
    ).toContain('--card-spacing');
  });
});

describe('the resolution rule is not vacuous', () => {
  it('reports a synthetic undeclared reference in both syntaxes, at any nesting depth', () => {
    expect(
      unresolvedIn('.probe { color: var(--no-such-token); }'),
      'the rule must fire on an undeclared name, or the guard below is decorative',
    ).toEqual(['--no-such-token']);
    expect(unresolvedIn('.probe { background: bg-(--also-no-such-token); }')).toEqual([
      '--also-no-such-token',
    ]);
    expect(unresolvedIn('.probe { color: var(--outer-probe, var(--no-such-inner)); }')).toEqual([
      '--no-such-inner',
    ]);
  });

  it('clears a synthetic reference to a token that IS declared and to one carrying a fallback', () => {
    expect(
      unresolvedIn(
        '.probe { color: var(--color-text); background: bg-(--color-surface-secondary); }',
      ),
      'the rule must not flag a declared token, or it would fail on the whole tree',
    ).toEqual([]);
    expect(unresolvedIn('.probe { color: var(--no-such-token, red); }')).toEqual([]);
  });
});

describe('fallback exemptions stay visible', () => {
  it('finds each documented optional token as a fallback-carrying reference, so the exemption list cannot rot silently', () => {
    for (const name of DOCUMENTED_EXEMPT_TOKENS) {
      expect(
        REFERENCES.some((reference) => reference.name === name && reference.hasFallback),
        `${name} is expected to be referenced with a fallback; if that changed, update DOCUMENTED_EXEMPT_TOKENS`,
      ).toBe(true);
    }
  });
});

describe('every no-fallback custom-property reference resolves', () => {
  it('finds no reference that is undeclared in src and provided by no external set', () => {
    expect(
      UNRESOLVED_REPORT,
      `${UNRESOLVED.size} custom-property name(s) are referenced with no fallback and resolve to nothing —\n` +
        'each property is invalid at computed-value time and collapses to unset, silently.\n' +
        'Either declare the token, switch to a declared token, or add a fallback:\n' +
        UNRESOLVED_REPORT,
    ).toBe('');
  });
});
