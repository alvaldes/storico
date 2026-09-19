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
    // Compared as a set of names, not as a sequence: the backend only tests
    // membership (``name.lower() in KNOWN_PROVIDERS``), and each side renders its own
    // order, so a backend-only reorder is not a drift this guard should cry about.
    expect(declared?.match(/"([^"]*)"/g)?.map((quoted) => quoted.slice(1, -1)).sort()).toEqual(
      [...KNOWN_PROVIDERS].sort(),
    );
  });

  it("matches the backend's reserved select control value", () => {
    const declared = extract(/^SELECT_CONTROL_VALUE = "([^"]*)"$/m);

    expect(declared, 'the backend declares SELECT_CONTROL_VALUE').not.toBeUndefined();
    expect(declared).toBe(ADD_CUSTOM_PROVIDER_VALUE);
  });
});

/**
 * The third copy is the one that actually broke something.
 *
 * `KNOWN_PROVIDERS` and its frontend mirror are guarded above, and migration `0021`'s frozen copy
 * is deliberately separate. What had no guard at all was a *second* rendering of the same list
 * inside the API schemas: `LLMTestRequest.provider` was a `Literal[...]` of the four names, so
 * `POST /api/v1/llm/test` answered `422` for every workspace-registered name that
 * `_build_llm_port` routes to the OpenAI-compatible adapter — and the branch meant to handle those
 * names was unreachable.
 *
 * The field is a bounded `str` now, so a custom name reaches the route, and its bound is the shared
 * `NAME_MAX_LENGTH` rather than a hand-typed number that could drift from the column it mirrors.
 */
describe('the API schemas carry no second provider list', () => {
  const settingsSource = readFileSync(
    new URL('../../../../backend/src/storico/api/schemas/settings.py', import.meta.url),
    'utf8',
  );

  it('re-lists the built-in provider names in no Literal', () => {
    // One name inside a Literal is a coincidence; two is a list, and that is how the connection
    // test came to disagree with extraction about which providers exist.
    const offender = [...settingsSource.matchAll(/Literal\[([^\]]*)\]/g)]
      .map((match) => match[1])
      .find((body) => KNOWN_PROVIDERS.filter((name) => body.includes(`"${name}"`)).length >= 2);

    expect(
      offender,
      'a Literal in api/schemas/settings.py re-lists the built-in providers. The list belongs to KNOWN_PROVIDERS in api/schemas/custom_provider.py; a second copy refuses exactly the custom names every other surface routes.',
    ).toBeUndefined();
  });

  it('validates the connection-test provider with the registry rule', () => {
    // The field is a bare `str` on purpose: the bound and the emptiness rule live in a validator
    // that applies the registry's own rule, so this endpoint cannot accept a name the registry
    // refuses (a whitespace-only one) or refuse a padded name it accepts. A `Field` with a
    // hand-typed number would be a fourth copy of the bound, and this asserts the rule is
    // applied *inside* the validator rather than merely mentioned in a comment.
    expect(settingsSource).toMatch(/^\s*provider: str$/m);
    expect(settingsSource).not.toMatch(/^\s*provider: str = Field\(.*max_length=\d+/m);

    const validator = settingsSource.match(
      /@field_validator\("provider"\)[\s\S]*?return name/,
    )?.[0];

    expect(
      validator,
      'LLMTestRequest.provider has a validator applying the registry rule',
    ).not.toBeUndefined();
    expect(validator).toContain('normalize_provider_name(value)');
    expect(validator).toContain('NAME_MAX_LENGTH');
  });
});
