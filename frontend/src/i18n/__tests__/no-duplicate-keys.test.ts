// @vitest-environment node
//
// This guard reads the locale files as text, so it needs a real filesystem path: jsdom
// hands out `http://localhost/...` URLs for `import.meta.url`, and `readFileSync`
// refuses those.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

/**
 * Every object member a JSON document declares, as (object identity, key) pairs, read
 * from the raw text.
 *
 * `JSON.parse` cannot answer this question. By the time a reviver runs, the parser has
 * already collapsed a duplicate member and the last one has won — which is exactly the
 * silent shadowing this guard exists to catch. So the document is scanned as text.
 *
 * Each `{` gets its own identity. That is what keeps an array of objects — where the
 * same key legitimately repeats in every element — from reading as a duplicate, which a
 * check keyed by object *path* would report on every element.
 *
 * Names are compared as decoded text, so two different escapes spelling one key
 * (`\u0061` and `a`) would not compare equal — and that pair is a real duplicate this
 * guard reports as clean. Locale keys are plain ASCII, so the hole is not reachable in
 * these two files; it is written down because it is a hole, not a guarantee.
 */
function memberNames(text: string): { object: number; key: string }[] {
  const found: { object: number; key: string }[] = [];
  const open: number[] = [];
  let nextObject = 0;
  let index = 0;

  while (index < text.length) {
    const char = text[index];

    if (char === '"') {
      let end = index + 1;
      let value = '';
      while (end < text.length) {
        if (text[end] === '\\') {
          value += text[end + 1];
          end += 2;
          continue;
        }
        if (text[end] === '"') break;
        value += text[end];
        end += 1;
      }

      // A string directly followed by a colon is a member name; anywhere else it is a
      // value, including a value that happens to contain braces or colons.
      let after = end + 1;
      while (after < text.length && /\s/.test(text[after])) after += 1;
      if (text[after] === ':' && open.length > 0) {
        found.push({ object: open[open.length - 1], key: value });
      }

      index = end + 1;
      continue;
    }

    if (char === '{') {
      open.push(nextObject);
      nextObject += 1;
    } else if (char === '}') {
      open.pop();
    }
    index += 1;
  }

  return found;
}

/** The key names a document declares twice inside one object, in the order they repeat. */
function duplicateKeys(text: string): string[] {
  const seen = new Map<number, Set<string>>();
  const duplicates: string[] = [];

  for (const { object, key } of memberNames(text)) {
    const keys = seen.get(object) ?? new Set<string>();
    if (keys.has(key)) duplicates.push(key);
    keys.add(key);
    seen.set(object, keys);
  }

  return duplicates;
}

/**
 * The locale files must declare each key exactly once.
 *
 * A duplicate is not harmless: JSON keeps the last one, so the earlier copy is dead code
 * that reads as the live value. Both keys this guard originally found were read by the UI
 * (`StoriesList`, `KanbanBoard`), which means the next edit to the surviving copy would
 * have changed user-visible copy with nothing to catch it — and CI runs no JSON linter, so
 * nothing else would either.
 */
describe('locale files declare no key twice', () => {
  it.each(['en', 'es'] as const)('%s.json has no duplicate object key', (locale) => {
    const text = readFileSync(new URL(`../${locale}.json`, import.meta.url), 'utf8');

    expect(duplicateKeys(text)).toEqual([]);
  });
});

/**
 * The scanner is the guard's only logic, so it is pinned in both directions: what it must
 * catch, and the shapes that would make it cry wolf — a false positive here fails the
 * build on valid JSON, which is worse than the duplicate it was written to find.
 */
describe('the duplicate-key scanner', () => {
  it('catches a key declared twice in one object', () => {
    expect(duplicateKeys('{"a": 1, "a": 2}')).toEqual(['a']);
  });

  it('catches a duplicate inside a nested object', () => {
    expect(duplicateKeys('{"outer": {"a": 1, "a": 2}}')).toEqual(['a']);
  });

  it('catches a duplicate in the second element of an array', () => {
    expect(duplicateKeys('{"list": [{"a": 1}, {"b": 2, "b": 3}]}')).toEqual(['b']);
  });

  it('reports every repetition, not only the first', () => {
    expect(duplicateKeys('{"a": 1, "a": 2, "a": 3}')).toEqual(['a', 'a']);
  });

  it('accepts one key used in two different objects', () => {
    expect(duplicateKeys('{"x": {"a": 1}, "y": {"a": 2}}')).toEqual([]);
  });

  it('accepts an array of objects that repeats a key per element', () => {
    // The shape a check keyed by object path would wrongly report on every element, and
    // the reason each object carries its own identity.
    expect(duplicateKeys('{"list": [{"a": 1}, {"a": 2}, {"a": 3}]}')).toEqual([]);
  });

  it('is not fooled by a colon inside a value', () => {
    expect(duplicateKeys('{"a": "http://x", "b": "y"}')).toEqual([]);
  });

  it('is not fooled by an escaped quote inside a value', () => {
    expect(duplicateKeys('{"a": "he said \\"hi\\"", "b": "y"}')).toEqual([]);
  });

  it('is not fooled by braces inside a value', () => {
    // The closing brace lives inside the string, so a scanner that ignored string state
    // would leave the object and miss the duplicate that follows.
    expect(duplicateKeys('{"a": "{not an object}", "a": 2}')).toEqual(['a']);
  });

  it('reads a key that follows an array value', () => {
    expect(duplicateKeys('{"a": [1, 2], "b": 3, "b": 4}')).toEqual(['b']);
  });
});
