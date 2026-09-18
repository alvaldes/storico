// @vitest-environment node
//
// These guards read a Python file, so they need a real filesystem path: jsdom hands
// out `http://localhost/...` URLs for `import.meta.url`, and `readFileSync` refuses
// those. The node environment keeps this file out of the jsdom suite instead of
// making the path depend on the working directory.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

import {
  ADD_CUSTOM_PROVIDER_VALUE,
  KNOWN_PROVIDERS,
  PROVIDER_NAME_MAX_LENGTH,
} from '@/lib/llm-providers';

/**
 * The provider vocabulary is declared twice, in two languages.
 *
 * The backend (`backend/src/storico/api/schemas/custom_provider.py`) is authoritative
 * and the frontend cannot import it, so the three constants are kept in step by hand.
 * Every one of them drives something visible: the maximum drives the input's
 * `maxLength` and the counter, the built-in list drives the case-insensitive refusal,
 * and the control value is what keeps the select's "Add custom provider…" slot out of
 * the name space. A drift in any of them produces a field that accepts a name the API
 * refuses, or a name the select cannot represent.
 *
 * Each case asserts its extraction first: if a constant is renamed in the backend, the
 * failure lands there, on the missing match, instead of turning the comparison into a
 * mystery `undefined`.
 */
describe('hand-kept provider vocabulary mirrors', () => {
  const backendSource = readFileSync(
    new URL('../../../../backend/src/storico/api/schemas/custom_provider.py', import.meta.url),
    'utf8',
  );

  const extract = (pattern: RegExp): string | undefined => backendSource.match(pattern)?.[1];

  it('matches the backend maximum', () => {
    const declared = extract(/^NAME_MAX_LENGTH = (\d+)$/m);

    expect(declared, 'the backend declares NAME_MAX_LENGTH').not.toBeUndefined();
    expect(declared).toBe(String(PROVIDER_NAME_MAX_LENGTH));
  });

  it("matches the backend's list of built-in providers", () => {
    const declared = extract(/^KNOWN_PROVIDERS: tuple\[str, \.\.\.\] = \(([^)]*)\)$/m);

    expect(declared, 'the backend declares KNOWN_PROVIDERS').not.toBeUndefined();
    expect(declared?.match(/"([^"]*)"/g)?.map((quoted) => quoted.slice(1, -1))).toEqual([
      ...KNOWN_PROVIDERS,
    ]);
  });

  it("matches the backend's reserved select control value", () => {
    const declared = extract(/^SELECT_CONTROL_VALUE = "([^"]*)"$/m);

    expect(declared, 'the backend declares SELECT_CONTROL_VALUE').not.toBeUndefined();
    expect(declared).toBe(ADD_CUSTOM_PROVIDER_VALUE);
  });
});
