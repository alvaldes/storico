// @vitest-environment node
//
// These guards read a Python file and the raw i18n JSON, so they need a real
// filesystem path: jsdom hands out `http://localhost/...` URLs for
// `import.meta.url`, and `readFileSync` refuses those. The node environment
// keeps this file out of the jsdom suite instead of making the path depend on
// the working directory.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

import { errorCodeHeadline } from '@/lib/error-codes';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

/**
 * The error-code vocabulary is declared twice, in two languages.
 *
 * The backend (`backend/src/storico/api/error_codes.py`) is authoritative and
 * the frontend cannot import it, so the code-to-copy map is kept in step by
 * hand. The whole point of WU5 is that a code degrades into *specific*
 * translated copy instead of the surface's generic headline — so when WU3 adds
 * the next batch of registry codes, a missing key here must be loud, not a
 * silent fallback. A drift in the reverse direction is equally real: a key the
 * backend never emits is copy for an error the user can never see.
 *
 * Each case asserts its extraction first: if `__all__` is renamed or moved in
 * the Python registry, the failure lands there, on "the extraction found
 * nothing", instead of turning the comparison into "16 keys missing".
 */

const registrySource = readFileSync(
  new URL('../../../../backend/src/storico/api/error_codes.py', import.meta.url),
  'utf8',
);

/** Pull the names out of the registry's `__all__` list. */
function extractRegistryNames(source: string): string[] {
  const body = source.match(/^__all__ = \[([\s\S]*?)^\]/m)?.[1] ?? '';
  return [...body.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
}

/**
 * Codes the backend emits today but that do not (yet) come from the registry:
 * they travel nested inside `detail` on six route sites (`tasks.py`,
 * `extraction.py`, `stories.py` import) and WU4 will move them to the
 * top-level canonical envelope. They are mapped here *now* so the frontend
 * tolerates both shapes during the deploy window; the backend never agreed to
 * rename them, so they belong in the map even though the registry does not
 * list them.
 *
 * Count note: that is 5 distinct codes over 6 sites — `IMPORT_FILE_TOO_LARGE`
 * covers two raise sites — so the map holds 21 + 5 = 26 keys (WU3 added the
 * five access-control codes to the registry and to this map in one commit).
 */
const ROUTE_ERROR_CODES = [
  'INVALID_STATE_TRANSITION',
  'LLM_CONFIG_INCOMPLETE',
  'IMPORT_FILE_REJECTED',
  'IMPORT_FILE_TOO_LARGE',
  'IMPORT_VALIDATION_FAILED',
] as const;

const EXPECTED_REGISTRY_COUNT = 21;

function tableFor(locale: 'en' | 'es'): Record<string, string> {
  return locale === 'en' ? en.errorCodes : es.errorCodes;
}

describe('the errorCodes map mirrors the backend registry', () => {
  it('reads the backend registry and maps every name it declares, in both locales', () => {
    const names = extractRegistryNames(registrySource);

    expect(
      names.length > 0,
      'the extraction of __all__ from backend/src/storico/api/error_codes.py found nothing — the registry moved or was renamed, so the mirror has nothing to compare against',
    ).toBe(true);

    for (const locale of ['en', 'es'] as const) {
      const missing = names.filter((code) => !(code in tableFor(locale)));
      expect(
        missing,
        `errorCodes in ${locale}.json is missing backend registry codes; each one degrades to generic copy`,
      ).toEqual([]);
    }
  });

  it('invents no code the backend does not emit', () => {
    const names = extractRegistryNames(registrySource);

    expect(
      names.length > 0,
      'the extraction of __all__ from backend/src/storico/api/error_codes.py found nothing — the registry moved or was renamed, so the mirror has nothing to compare against',
    ).toBe(true);

    const emitted = new Set<string>([...names, ...ROUTE_ERROR_CODES]);
    for (const locale of ['en', 'es'] as const) {
      const invented = Object.keys(tableFor(locale)).filter((code) => !emitted.has(code));
      expect(
        invented,
        `errorCodes in ${locale}.json maps codes the backend never emits — copy for errors no user can hit`,
      ).toEqual([]);
    }
  });

  it('pins the expected counts so drift is loud on both sides', () => {
    const names = extractRegistryNames(registrySource);

    expect(
      names,
      'the backend registry grew or shrank: update EXPECTED_REGISTRY_COUNT and the map together',
    ).toHaveLength(EXPECTED_REGISTRY_COUNT);

    for (const locale of ['en', 'es'] as const) {
      expect(Object.keys(tableFor(locale))).toHaveLength(
        EXPECTED_REGISTRY_COUNT + ROUTE_ERROR_CODES.length,
      );
    }
  });
});

describe('errorCodeHeadline', () => {
  it('translates a mapped code into the locale’s copy', () => {
    expect(errorCodeHeadline('ENTITY_NOT_FOUND', 'en')).toBe(en.errorCodes.ENTITY_NOT_FOUND);
    expect(errorCodeHeadline('ENTITY_NOT_FOUND', 'es')).toBe(es.errorCodes.ENTITY_NOT_FOUND);
  });

  it('returns undefined for an unmapped code, so the caller keeps its own message', () => {
    // WORKSPACE_SLUG_TAKEN arrives with WU3b; until then an unmapped code must
    // degrade to the caller's headline, never to `undefined` rendered as text.
    expect(errorCodeHeadline('WORKSPACE_SLUG_TAKEN', 'en')).toBeUndefined();
    expect(errorCodeHeadline('WORKSPACE_SLUG_TAKEN', 'es')).toBeUndefined();
  });

  it('returns undefined when there is no code at all', () => {
    expect(errorCodeHeadline(undefined, 'en')).toBeUndefined();
  });
});
