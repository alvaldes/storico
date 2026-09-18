// @vitest-environment node
//
// These guards read Python files, so they need a real filesystem path: jsdom hands out
// `http://localhost/...` URLs for `import.meta.url`, and `readFileSync` refuses those.
// The node environment keeps this file out of the jsdom suite instead of making the
// paths depend on the working directory.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

import {
  CUSTOM_PROVIDER_REQUIRED_FIELDS,
  LLM_CONFIG_INCOMPLETE_CODE,
  READINESS_FIELDS,
  REQUIRED_FIELDS_BY_PROVIDER,
  requiredFieldsFor,
} from '@/lib/llm-config-readiness';
import {
  LLM_API_KEY_MAX_LENGTH,
  LLM_ENDPOINT_MAX_LENGTH,
  LLM_MODEL_MAX_LENGTH,
} from '@/schemas/workspace';
import { KNOWN_PROVIDERS, PROVIDER_NAME_MAX_LENGTH } from '@/lib/llm-providers';

/**
 * The completeness rule and the field lengths are declared twice, in two languages.
 *
 * The backend is authoritative — `storico/domain/services/llm_config_readiness.py`
 * decides whether the API refuses an extraction, and
 * `api/schemas/workspace_llm_config.py` decides what the API accepts — and the
 * frontend cannot import either. A drift is not cosmetic on this surface: the settings
 * form would let an admin save a configuration the API refuses to extract with, or
 * block a save the API would have accepted, and the extraction button would promise a
 * run the API refuses before creating anything.
 *
 * Each case asserts its extraction first: if something is renamed in the backend, the
 * failure lands there, on the missing match, instead of turning the comparison into a
 * mystery `undefined`.
 */
describe('hand-kept LLM config mirrors', () => {
  const readinessSource = readFileSync(
    new URL(
      '../../../../backend/src/storico/domain/services/llm_config_readiness.py',
      import.meta.url,
    ),
    'utf8',
  );
  const requestSchemaSource = readFileSync(
    new URL(
      '../../../../backend/src/storico/api/schemas/workspace_llm_config.py',
      import.meta.url,
    ),
    'utf8',
  );

  const extract = (source: string, pattern: RegExp): string | undefined =>
    source.match(pattern)?.[1];

  /** Names inside a Python string tuple literal such as `("model", "api_key")`. */
  const namesOf = (literal: string | undefined): string[] | undefined =>
    literal?.match(/"([^"]*)"/g)?.map((quoted) => quoted.slice(1, -1));

  describe('the completeness rule', () => {
    it('matches the backend field vocabulary', () => {
      const declared = extract(readinessSource, /^READINESS_FIELDS[^=]*= \(([^)]*)\)/m);

      expect(declared, 'the backend declares READINESS_FIELDS').not.toBeUndefined();
      expect(namesOf(declared)).toEqual([...READINESS_FIELDS]);
    });

    it("matches the backend's per-provider requirements", () => {
      const declared = extract(
        readinessSource,
        /^REQUIRED_FIELDS_BY_PROVIDER[^=]*= \{([\s\S]*?)^\}/m,
      );

      expect(declared, 'the backend declares REQUIRED_FIELDS_BY_PROVIDER').not.toBeUndefined();

      const backend = Object.fromEntries(
        [...declared!.matchAll(/"([^"]+)": \(([^)]*)\)/g)].map(([, provider, fields]) => [
          provider,
          namesOf(fields),
        ]),
      );

      expect(backend).toEqual(
        Object.fromEntries(
          KNOWN_PROVIDERS.map((provider) => [provider, [...REQUIRED_FIELDS_BY_PROVIDER[provider]]]),
        ),
      );
    });

    it("matches the backend's custom-provider requirements", () => {
      const declared = extract(
        readinessSource,
        /^CUSTOM_PROVIDER_REQUIRED_FIELDS[^=]*= \(([^)]*)\)/m,
      );

      expect(declared, 'the backend declares CUSTOM_PROVIDER_REQUIRED_FIELDS').not.toBeUndefined();
      expect(namesOf(declared)).toEqual([...CUSTOM_PROVIDER_REQUIRED_FIELDS]);
    });

    it('matches the backend refusal code', () => {
      const declared = extract(readinessSource, /^LLM_CONFIG_INCOMPLETE_CODE = "([^"]*)"/m);

      expect(declared, 'the backend declares LLM_CONFIG_INCOMPLETE_CODE').not.toBeUndefined();
      expect(declared).toBe(LLM_CONFIG_INCOMPLETE_CODE);
    });

    it('routes a name the backend would not recognise to the custom requirements', () => {
      // The classification itself, not just the table: a name outside the four
      // built-ins is a custom OpenAI-compatible provider on both sides.
      expect(requiredFieldsFor('ollama')).toEqual([...REQUIRED_FIELDS_BY_PROVIDER.ollama]);
      expect(requiredFieldsFor('Groq')).toEqual([...CUSTOM_PROVIDER_REQUIRED_FIELDS]);
    });
  });

  describe('the accepted lengths', () => {
    /** The declared `max_length` of each request field, keyed by field name. */
    const declaredLengths = new Map(
      [
        ...requestSchemaSource.matchAll(
          // Indented inside the model class, so the anchor is the line start plus the
          // indentation rather than `^\w`; no line-end anchor, so trailing whitespace
          // cannot turn a real declaration into a missing one.
          /^[ \t]*(\w+): str \| None = Field\(None, max_length=(\d+)\)/gm,
        ),
      ].map(([, field, maxLength]) => [field, maxLength]),
    );

    it.each([
      ['provider', PROVIDER_NAME_MAX_LENGTH],
      ['model', LLM_MODEL_MAX_LENGTH],
      ['base_url', LLM_ENDPOINT_MAX_LENGTH],
      ['api_key', LLM_API_KEY_MAX_LENGTH],
    ])('matches the backend maximum for %s', (field, frontendValue) => {
      const declared = declaredLengths.get(field);

      expect(declared, `the backend declares a max_length for ${field}`).not.toBeUndefined();
      expect(declared).toBe(String(frontendValue));
    });
  });
});
