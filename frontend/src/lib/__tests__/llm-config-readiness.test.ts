import { describe, it, expect } from 'vitest';

import {
  CUSTOM_PROVIDER_REQUIRED_FIELDS,
  READINESS_FIELDS,
  REQUIRED_FIELDS_BY_PROVIDER,
  isLLMConfigComplete,
  missingLLMConfigFields,
  requiredFieldsFor,
} from '@/lib/llm-config-readiness';

/**
 * The completeness rule, before it is wired to anything.
 *
 * The same cases the backend pins in
 * `backend/tests/test_unit/test_llm_config_readiness.py`, because the two are meant to
 * answer identically — the API is the authority and this side has to agree, or the
 * form and the extraction button disagree with the refusal they are explaining.
 */
describe('requiredFieldsFor', () => {
  it('takes a known provider from its own declaration', () => {
    for (const provider of ['ollama', 'openai', 'anthropic', 'gemini'] as const) {
      expect(requiredFieldsFor(provider)).toEqual(REQUIRED_FIELDS_BY_PROVIDER[provider]);
    }
  });

  it("does not require Ollama's endpoint", () => {
    // Its host falls back to the configured default, so only the model is required.
    expect(requiredFieldsFor('ollama')).toEqual(['model']);
  });

  it('requires the workspace credential from each cloud provider', () => {
    for (const provider of ['openai', 'anthropic', 'gemini'] as const) {
      expect(requiredFieldsFor(provider)).toEqual(['model', 'api_key']);
    }
  });

  it('treats anything outside the four built-ins as a custom provider', () => {
    // `OLLAMA` is in this list on purpose: the comparison is exact, exactly like
    // routing's, so a mis-cased built-in is a custom provider and needs an endpoint.
    for (const provider of ['deepseek', 'My Gateway v2', '', 'OLLAMA']) {
      expect(requiredFieldsFor(provider)).toEqual([...CUSTOM_PROVIDER_REQUIRED_FIELDS]);
    }
  });

  it('does not require a credential from a custom provider', () => {
    // A self-hosted gateway commonly accepts unauthenticated requests.
    expect(requiredFieldsFor('deepseek')).toEqual(['model', 'base_url']);
  });
});

describe('missingLLMConfigFields', () => {
  it('reports nothing for a complete Ollama configuration', () => {
    expect(missingLLMConfigFields({ provider: 'ollama', model: 'llama3.2' })).toEqual([]);
  });

  it('reports a missing model on its own', () => {
    expect(missingLLMConfigFields({ provider: 'openai', apiKey: 'sk-test' })).toEqual(['model']);
  });

  it('reports both gaps in vocabulary order', () => {
    // READINESS_FIELDS order, not the provider row's order.
    expect(missingLLMConfigFields({ provider: 'anthropic' })).toEqual(['model', 'api_key']);
  });

  it('reports a missing key for each cloud provider', () => {
    for (const provider of ['openai', 'anthropic', 'gemini']) {
      expect(missingLLMConfigFields({ provider, model: 'some-model' })).toEqual(['api_key']);
    }
  });

  it('reports a custom provider without an endpoint', () => {
    expect(missingLLMConfigFields({ provider: 'deepseek', model: 'deepseek-chat' })).toEqual([
      'base_url',
    ]);
  });

  it('accepts a custom provider without a key', () => {
    expect(
      missingLLMConfigFields({
        provider: 'deepseek',
        model: 'deepseek-chat',
        baseUrl: 'https://api.deepseek.com/v1',
      }),
    ).toEqual([]);
  });

  it('counts a blank value as unset', () => {
    // The form holds `''` where the API would store `null`.
    for (const blank of ['', '   ', '\t\n']) {
      expect(missingLLMConfigFields({ provider: 'openai', model: blank, apiKey: blank })).toEqual([
        'model',
        'api_key',
      ]);
    }
  });

  it('accepts a padded value as set', () => {
    expect(missingLLMConfigFields({ provider: 'ollama', model: '  llama3.2  ' })).toEqual([]);
  });

  it('treats an unconfigured workspace as Ollama', () => {
    expect(missingLLMConfigFields({ provider: 'ollama' })).toEqual(['model']);
  });

  it('agrees with isLLMConfigComplete on every shape', () => {
    const cases = [
      { provider: 'ollama', model: 'llama3.2' },
      { provider: 'ollama' },
      { provider: 'openai', model: 'gpt-4o-mini', apiKey: 'sk-test' },
      { provider: 'openai', model: 'gpt-4o-mini' },
      { provider: 'gemini', apiKey: 'AIza-test' },
      { provider: 'deepseek', model: 'deepseek-chat', baseUrl: 'https://x.example/v1' },
      { provider: 'deepseek', model: 'deepseek-chat' },
    ];

    for (const values of cases) {
      expect(isLLMConfigComplete(values)).toBe(missingLLMConfigFields(values).length === 0);
    }
  });
});

describe('the vocabulary', () => {
  it('is exactly the three fields the API reports', () => {
    expect(READINESS_FIELDS).toEqual(['model', 'api_key', 'base_url']);
  });

  it('requires a model from every provider family', () => {
    // The extraction route narrows the model away from `str | None` by checking the
    // gap list, which is only sound while every family requires it.
    for (const fields of Object.values(REQUIRED_FIELDS_BY_PROVIDER)) {
      expect(fields).toContain('model');
    }
    expect(CUSTOM_PROVIDER_REQUIRED_FIELDS).toContain('model');
  });
});
