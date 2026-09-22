// @vitest-environment node
//
// This guard reads a Python file, so it needs a real filesystem path: jsdom hands out
// `http://localhost/...` URLs for `import.meta.url`, and `readFileSync` refuses those. The
// node environment keeps this file out of the jsdom suite instead of making the path depend
// on the working directory.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

/**
 * The export formats the product actually supports live in the backend's `ExportSettings`:
 * `default_format: Literal["json", "markdown"]` is the accepted set, and `RETIRED_EXPORT_FORMATS`
 * holds the values a previous schema version accepted and the API now refuses. A format on the
 * retired list is a promise the product cannot keep, so any catalog string that names it is false
 * copy — the "export to Trello" promise survived in five keys across three unrelated sections
 * precisely because nothing connected the copy to the schema.
 *
 * Both sides are derived from the backend by regex against the source (not by importing Python),
 * so retiring a format in `RETIRED_EXPORT_FORMATS` is the only step needed for this guard to
 * start flagging copy that still promises it.
 */
const settingsSource = readFileSync(
  new URL('../../../../backend/src/storico/api/schemas/settings.py', import.meta.url),
  'utf8',
);

/** Formats the API refuses, read from the keys of `RETIRED_EXPORT_FORMATS`. */
const RETIRED_FORMATS = (() => {
  const literal = settingsSource.match(/RETIRED_EXPORT_FORMATS[^=]*= \{([^}]*)\}/)?.[1];
  const names = literal?.match(/"([^"]+)":/g)?.map((quoted) => quoted.slice(1, -2)) ?? [];
  return names;
})();

/** Formats the API accepts, read from the members of `default_format: Literal[...]`. */
const ACCEPTED_FORMATS = (() => {
  const literal = settingsSource.match(/default_format:\s*Literal\[([^\]]*)\]/)?.[1];
  const names = literal?.match(/"([^"]+)"/g)?.map((quoted) => quoted.slice(1, -1)) ?? [];
  return names;
})();

const CATALOGS = { en: en as Record<string, unknown>, es: es as Record<string, unknown> };

/**
 * Formats the string names from `formats`.
 *
 * Case-insensitive whole-word matching, because the prose capitalises format names its own way
 * (`Trello`, `JSON`) while the backend holds the lowercase wire spelling — and a substring match
 * would fire on unrelated words that merely contain one.
 */
export function mentionedFormats(text: string, formats: readonly string[]): string[] {
  const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  return formats.filter((format) => new RegExp(`\\b${escapeRegExp(format)}\\b`, 'i').test(text));
}

/** Every string value in the catalog, with its dotted key path — not a curated list of keys. */
function stringEntries(
  node: unknown,
  path = '',
  entries: { path: string; value: string }[] = [],
): { path: string; value: string }[] {
  if (typeof node === 'string') {
    entries.push({ path, value: node });
  } else if (typeof node === 'object' && node !== null) {
    for (const [key, child] of Object.entries(node)) {
      stringEntries(child, path ? `${path}.${key}` : key, entries);
    }
  }
  return entries;
}

describe('export copy', () => {
  it('derives the retired and accepted export formats from the backend schema', () => {
    // Both extractions must be non-empty before any case below is trusted: an empty match means
    // the regex stopped matching, not that the schema became clean — assert on the extraction.
    expect(
      RETIRED_FORMATS,
      'the backend declares RETIRED_EXPORT_FORMATS with at least one retired format',
    ).toEqual(expect.arrayContaining([expect.any(String)]));
    expect(RETIRED_FORMATS.length).toBeGreaterThan(0);

    expect(
      ACCEPTED_FORMATS,
      'the backend declares default_format as a Literal with at least one accepted format',
    ).toEqual(expect.arrayContaining([expect.any(String)]));
    expect(ACCEPTED_FORMATS.length).toBeGreaterThan(0);

    // A format can be refused or accepted, never both.
    const overlap = RETIRED_FORMATS.filter((format) => ACCEPTED_FORMATS.includes(format));
    expect(overlap, 'no format is both retired and accepted').toEqual([]);
  });

  it('flags a planted promise of a retired format, so a broken detector cannot pass silently', () => {
    expect(mentionedFormats('Export your tasks to Trello, JSON, or Markdown.', RETIRED_FORMATS)).toContain(
      'trello',
    );
    expect(mentionedFormats('Export your tasks to JSON or Markdown.', RETIRED_FORMATS)).toEqual([]);
  });

  describe.each(Object.entries(CATALOGS))('the %s catalog', (locale, catalog) => {
    it('names no retired export format in any string', () => {
      const offenders = stringEntries(catalog).flatMap(({ path, value }) =>
        mentionedFormats(value, RETIRED_FORMATS).map((format) => `${path}: promises "${format}"`),
      );

      expect(
        offenders,
        `the ${locale} catalog must not promise a format the API refuses`,
      ).toEqual([]);
    });
  });
});
