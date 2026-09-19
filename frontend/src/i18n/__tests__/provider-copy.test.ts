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
import { KNOWN_PROVIDERS } from '@/lib/llm-providers';

/**
 * Four prose keys enumerate the providers the product supports. They are the only place the
 * *set* of providers is written out for a human, which is what makes them the place a fifth
 * provider is forgotten: nothing else in the frontend turns red when the backend grows one,
 * so a name lands in `KNOWN_PROVIDERS` and the marketing copy, the privacy page and the
 * status table keep naming four.
 *
 * "Cloud" is read from the backend rather than declared here: a provider that cannot be
 * called without an `api_key` is a cloud provider, and the completeness rule already says
 * which those are. The provider list comes from `KNOWN_PROVIDERS`, so the two sides of the
 * drift — the vocabulary and the rule that classifies it — are both the backend's.
 */
const readinessSource = readFileSync(
  new URL(
    '../../../../backend/src/storico/domain/services/llm_config_readiness.py',
    import.meta.url,
  ),
  'utf8',
);

const REQUIRED_FIELDS_BY_PROVIDER = (() => {
  const literal = readinessSource.match(/^REQUIRED_FIELDS_BY_PROVIDER[^=]*= \{([\s\S]*?)^\}/m)?.[1];
  if (literal === undefined) return undefined;

  return Object.fromEntries(
    [...literal.matchAll(/"([^"]+)": \(([^)]*)\)/g)].map(([, provider, fields]) => [
      provider,
      fields.match(/"([^"]*)"/g)?.map((quoted) => quoted.slice(1, -1)) ?? [],
    ]),
  );
})();

/** Providers the backend cannot call without a credential. */
const CLOUD_PROVIDERS = KNOWN_PROVIDERS.filter((provider) =>
  REQUIRED_FIELDS_BY_PROVIDER?.[provider]?.includes('api_key'),
);

/** Providers it can call without one. */
const LOCAL_PROVIDERS = KNOWN_PROVIDERS.filter((provider) => !CLOUD_PROVIDERS.includes(provider));

/** Copy that is deciding between running locally and sending data to a cloud provider. */
const CLOUD_ONLY_KEYS = [
  'landing.faq.a6',
  'pages.privacy.collection_llm',
  'pages.privacy.transfers_body',
];

/**
 * The one key that lists the runners a deployment can be pointed at, so it names the local
 * provider alongside the cloud ones. That is what the string already does — Ollama is in it
 * today — and requiring all of them is not over-constraining a list of runners. The local
 * side is still read from the rule rather than typed out, so the two requirements come from
 * one classification.
 */
const ALL_PROVIDER_KEYS = ['pages.status.llm_runner_desc'];

const CATALOGS = { en: en as Record<string, unknown>, es: es as Record<string, unknown> };

/** The value at a dotted key path, or `undefined` when the catalog does not declare it. */
function readPath(catalog: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((node, key) => {
    if (typeof node !== 'object' || node === null) return undefined;
    return (node as Record<string, unknown>)[key];
  }, catalog);
}

/**
 * Provider names the string does not mention.
 *
 * Case-insensitive substring matching, because the prose capitalises the names its own way
 * (`OpenAI`, `Anthropic`, `Gemini`) while `KNOWN_PROVIDERS` holds the lowercase wire spelling.
 * `OpenAI-compatible` counts as naming OpenAI, which is the reading a human takes too.
 */
function missingProviders(text: string, providers: readonly string[]): string[] {
  const haystack = text.toLowerCase();
  return providers.filter((provider) => !haystack.includes(provider.toLowerCase()));
}

describe('provider copy', () => {
  it('derives the cloud providers from the backend rule', () => {
    expect(
      REQUIRED_FIELDS_BY_PROVIDER,
      'the backend declares REQUIRED_FIELDS_BY_PROVIDER',
    ).not.toBeUndefined();
    expect(Object.keys(REQUIRED_FIELDS_BY_PROVIDER!).sort()).toEqual([...KNOWN_PROVIDERS].sort());

    // Both halves have to be populated, or every case below passes on an empty requirement.
    expect(CLOUD_PROVIDERS.length).toBeGreaterThan(0);
    expect(LOCAL_PROVIDERS.length).toBeGreaterThan(0);
  });

  describe.each(Object.entries(CATALOGS))('the %s catalog', (locale, catalog) => {
    it.each(CLOUD_ONLY_KEYS)('names every cloud provider in %s', (key) => {
      const value = readPath(catalog, key);
      expect(value, `the ${locale} catalog declares ${key}`).toBeTypeOf('string');

      const missing = missingProviders(value as string, CLOUD_PROVIDERS);
      expect(
        missing,
        `${locale} ${key} must name every cloud provider; missing: ${missing.join(', ')}`,
      ).toEqual([]);
    });

    it.each(ALL_PROVIDER_KEYS)('names every provider, local included, in %s', (key) => {
      const value = readPath(catalog, key);
      expect(value, `the ${locale} catalog declares ${key}`).toBeTypeOf('string');

      const missing = missingProviders(value as string, KNOWN_PROVIDERS);
      expect(
        missing,
        `${locale} ${key} must name every provider; missing: ${missing.join(', ')}`,
      ).toEqual([]);
    });
  });
});
