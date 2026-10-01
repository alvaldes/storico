// @vitest-environment node
//
// These guards read a Python file and the raw i18n JSON, so they need a real
// filesystem path: jsdom hands out `http://localhost/...` URLs for
// `import.meta.url`, and `readFileSync` refuses those. The node environment
// keeps this file out of the jsdom suite instead of making the path depend on
// the working directory.
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

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
 * covers two raise sites — so the map holds `EXPECTED_REGISTRY_COUNT` + 5 keys.
 * Stated as the rule rather than a total on purpose: the assertion below derives
 * that number, so any literal here goes stale the next time the registry grows —
 * and it already did three times (WU1's two 410-retirement codes, WU2's
 * `TASK_VERSION_FROZEN`, W4-T2's version-allocation / vector-store / gate codes).
 * The history, in case the numbers matter later: WU3a added the five
 * access-control codes and WU3b the fifteen route codes to the registry and to
 * this map, each in one commit.
 */
const ROUTE_ERROR_CODES = [
  'INVALID_STATE_TRANSITION',
  'LLM_CONFIG_INCOMPLETE',
  'IMPORT_FILE_REJECTED',
  'IMPORT_FILE_TOO_LARGE',
  'IMPORT_VALIDATION_FAILED',
] as const;

const EXPECTED_REGISTRY_COUNT = 42;

/**
 * The one code emitted through a named constant rather than a literal or a
 * registry entry. Listed here so the literal scan above can subtract it and
 * still demand an exact match; the next case pins its actual value.
 */
const DOMAIN_CONSTANT_CODES: readonly string[] = ['LLM_CONFIG_INCOMPLETE'];

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

  it('finds every code the backend emits as a literal and keeps the allowlist honest', () => {
    // The registry check above only sees names declared in `error_codes.py`. A
    // raise site can also write `error_code="SOMETHING"` inline — WU4 left five
    // of them that way (`INVALID_STATE_TRANSITION`, `LLM_CONFIG_INCOMPLETE`, the
    // three `IMPORT_*`), because those constants live in route and domain files
    // the registry does not own. Without this case the mirror would pass while a
    // newly inlined code degraded to generic copy, and `ROUTE_ERROR_CODES` would
    // quietly rot into a list of what someone remembered.
    const apiDir = fileURLToPath(new URL('../../../../backend/src/storico/api', import.meta.url));
    const literals = new Set<string>();
    for (const entry of readdirSync(apiDir, { recursive: true })) {
      const file = String(entry);
      if (!file.endsWith('.py')) continue;
      const source = readFileSync(new URL(`../../../../backend/src/storico/api/${file}`, import.meta.url), 'utf8');
      for (const match of source.matchAll(/error_code\s*=\s*"([A-Z][A-Z0-9_]*)"/g)) {
        literals.add(match[1]);
      }
      for (const match of source.matchAll(/"error_code":\s*"([A-Z][A-Z0-9_]*)"/g)) {
        literals.add(match[1]);
      }
    }

    expect(
      literals.size > 0,
      'no inline `error_code="…"` literal was found anywhere under backend/src/storico/api — the scan is broken, not the backend',
    ).toBe(true);

    for (const code of literals) {
      expect(
        code in en.errorCodes && code in es.errorCodes,
        `the backend emits ${code} inline but the map has no key for it, so that error shows generic copy`,
      ).toBe(true);
    }

    // The allowlist must be exactly the literals found — minus the one code the
    // backend emits through a named constant instead of a literal, which the
    // next case pins by reading that constant's definition. A code cannot slip
    // in as a new literal without naming it here, and one that stops being
    // emitted cannot stay in `ROUTE_ERROR_CODES` pretending the backend sends it.
    const literalAllowlist = ROUTE_ERROR_CODES.filter(
      (code) => !DOMAIN_CONSTANT_CODES.includes(code),
    );
    expect([...literals].sort()).toEqual([...literalAllowlist].sort());
  });

  it('pins the code the backend emits through a domain constant, not a literal', () => {
    // `extraction.py` raises `error_code=LLM_CONFIG_INCOMPLETE_CODE`, and that
    // constant is defined in `domain/services/llm_config_readiness.py` — outside
    // both the registry and the literal scan above. This is the case that makes
    // the exception real rather than a hole: it reads the constant's own
    // definition, so renaming the value or moving the file fails here.
    const source = readFileSync(
      new URL(
        '../../../../backend/src/storico/domain/services/llm_config_readiness.py',
        import.meta.url,
      ),
      'utf8',
    );
    const found = source.match(/^LLM_CONFIG_INCOMPLETE_CODE = "([A-Z][A-Z0-9_]*)"/m);

    expect(
      found,
      'LLM_CONFIG_INCOMPLETE_CODE is no longer a top-level string constant in domain/services/llm_config_readiness.py — the third source of error codes moved',
    ).not.toBeNull();
    expect(found?.[1]).toEqual('LLM_CONFIG_INCOMPLETE');

    for (const locale of ['en', 'es'] as const) {
      expect(
        found?.[1] && found[1] in tableFor(locale),
        `the backend emits ${found?.[1]} but ${locale}.json has no key for it`,
      ).toBe(true);
    }
  });
});

describe('errorCodeHeadline', () => {
  it('translates a mapped code into the locale’s copy', () => {
    expect(errorCodeHeadline('ENTITY_NOT_FOUND', 'en')).toBe(en.errorCodes.ENTITY_NOT_FOUND);
    expect(errorCodeHeadline('ENTITY_NOT_FOUND', 'es')).toBe(es.errorCodes.ENTITY_NOT_FOUND);
  });

  it('returns undefined for an unmapped code, so the caller keeps its own message', () => {
    // The example must be a code the registry can never contain: a marker a
    // caller invents for itself (WU3a moved it here from
    // WORKSPACE_SLUG_TAKEN, which WU3b has since mapped — the mirror doing its
    // job one layer up, again).
    expect(errorCodeHeadline('BOARD_UNAVAILABLE', 'en')).toBeUndefined();
    expect(errorCodeHeadline('BOARD_UNAVAILABLE', 'es')).toBeUndefined();
  });

  it('returns undefined when there is no code at all', () => {
    expect(errorCodeHeadline(undefined, 'en')).toBeUndefined();
  });
});
