import { describe, it, expect } from 'vitest';
import {
  LLM_API_KEY_MAX_LENGTH,
  LLM_MAX_TOKENS_RANGE,
  LLM_MODEL_MAX_LENGTH,
  LLM_TEMPERATURE_RANGE,
  llmConfigDraftSchema,
  llmConfigSchema,
  promptConfigSchema,
} from '@/schemas/workspace';
import { PROVIDER_NAME_MAX_LENGTH } from '@/lib/llm-providers';

/** A complete Ollama draft — the shape the settings form holds when nothing is missing. */
const completeDraft = {
  provider: 'ollama',
  model: 'llama3.2',
  temperature: 0.1,
  maxTokens: 2048,
  baseUrl: 'http://localhost:11434',
  apiKey: '',
};

/** The message of every issue raised for one field, in order. */
function messagesFor(
  result: ReturnType<typeof llmConfigDraftSchema.safeParse>,
  field: string,
): string[] {
  if (result.success) return [];
  return result.error.issues.filter((issue) => issue.path[0] === field).map((issue) => issue.message);
}

describe('promptConfigSchema - few-shot config fields', () => {
  it('accepts default config', () => {
    const result = promptConfigSchema.safeParse({});

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.fewShotEnabled).toBeUndefined();
      expect(result.data.fewShotLimit).toBeUndefined();
      expect(result.data.fewShotThreshold).toBeUndefined();
    }
  });

  it('accepts valid config values', () => {
    const result = promptConfigSchema.safeParse({
      fewShotEnabled: false,
      fewShotLimit: 5,
      fewShotThreshold: 0.9,
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.fewShotEnabled).toBe(false);
      expect(result.data.fewShotLimit).toBe(5);
      expect(result.data.fewShotThreshold).toBe(0.9);
    }
  });

  it('rejects limit below 1', () => {
    const result = promptConfigSchema.safeParse({ fewShotLimit: 0 });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(['fewShotLimit']);
    }
  });

  it('rejects limit above 10', () => {
    const result = promptConfigSchema.safeParse({ fewShotLimit: 11 });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(['fewShotLimit']);
    }
  });

  it('rejects threshold below 0', () => {
    const result = promptConfigSchema.safeParse({ fewShotThreshold: -0.1 });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(['fewShotThreshold']);
    }
  });

  it('rejects threshold above 1', () => {
    const result = promptConfigSchema.safeParse({ fewShotThreshold: 1.1 });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(['fewShotThreshold']);
    }
  });

  it('allows config alongside other prompt fields', () => {
    const result = promptConfigSchema.safeParse({
      systemPrompt: 'You are an expert...',
      instructionTemplate: 'Break this user story...',
      fewShotEnabled: true,
      fewShotLimit: 3,
      fewShotThreshold: 0.85,
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.systemPrompt).toBe('You are an expert...');
      expect(result.data.fewShotLimit).toBe(3);
    }
  });
});

describe('llmConfigSchema - the PUT payload contract', () => {
  it('accepts a bare provider, which is all onboarding sends', () => {
    // Onboarding saves the selection and nothing else; the route merges it onto the
    // stored row. Making any other field required here would break that call.
    const result = llmConfigSchema.safeParse({ provider: 'openai' });

    expect(result.success).toBe(true);
  });

  it('accepts a complete payload', () => {
    const result = llmConfigSchema.safeParse({
      provider: 'openai',
      model: 'gpt-4o-mini',
      temperature: 0.2,
      maxTokens: 4096,
      baseUrl: 'https://api.openai.com/v1',
      apiKey: 'sk-test',
    });

    expect(result.success).toBe(true);
  });

  it('accepts an absent model, which is how a cleared field is sent', () => {
    // The editor maps `''` to `undefined` before sending: the route reads an absent
    // field as "not part of this update", never as "set it to empty".
    const result = llmConfigSchema.safeParse({ provider: 'ollama', model: undefined });

    expect(result.success).toBe(true);
  });

  it('rejects a provider over the stored length', () => {
    const result = llmConfigSchema.safeParse({
      provider: 'a'.repeat(PROVIDER_NAME_MAX_LENGTH + 1),
    });

    expect(result.success).toBe(false);
  });

  it('rejects a model over the stored length', () => {
    const result = llmConfigSchema.safeParse({ model: 'a'.repeat(LLM_MODEL_MAX_LENGTH + 1) });

    expect(result.success).toBe(false);
  });

  it('rejects a temperature outside the control range', () => {
    expect(llmConfigSchema.safeParse({ temperature: LLM_TEMPERATURE_RANGE.max + 1 }).success).toBe(
      false,
    );
    expect(llmConfigSchema.safeParse({ temperature: LLM_TEMPERATURE_RANGE.min - 1 }).success).toBe(
      false,
    );
  });

  it('rejects max tokens outside the control range', () => {
    expect(
      llmConfigSchema.safeParse({ maxTokens: LLM_MAX_TOKENS_RANGE.max + 1 }).success,
    ).toBe(false);
    expect(
      llmConfigSchema.safeParse({ maxTokens: LLM_MAX_TOKENS_RANGE.min - 1 }).success,
    ).toBe(false);
  });

  it('rejects a non-integer max tokens', () => {
    expect(llmConfigSchema.safeParse({ maxTokens: 1024.5 }).success).toBe(false);
  });

  it('rejects an api key over the stored length', () => {
    const result = llmConfigSchema.safeParse({ apiKey: 'k'.repeat(LLM_API_KEY_MAX_LENGTH + 1) });

    expect(result.success).toBe(false);
  });
});

describe('llmConfigDraftSchema - what the settings form must satisfy to save', () => {
  it('accepts a complete Ollama draft', () => {
    expect(llmConfigDraftSchema.safeParse(completeDraft).success).toBe(true);
  });

  it('accepts a complete cloud draft', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      provider: 'openai',
      model: 'gpt-4o-mini',
      apiKey: 'sk-test',
      baseUrl: '',
    });

    expect(result.success).toBe(true);
  });

  it('accepts an empty endpoint, which means "use the provider default"', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      provider: 'openai',
      apiKey: 'sk-test',
      baseUrl: '',
    });

    expect(result.success).toBe(true);
  });

  it('accepts a custom provider with no credential', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      provider: 'deepseek',
      model: 'deepseek-chat',
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: '',
    });

    expect(result.success).toBe(true);
  });

  it('reports a missing model where the model input is', () => {
    const result = llmConfigDraftSchema.safeParse({ ...completeDraft, model: '' });

    expect(result.success).toBe(false);
    expect(messagesFor(result, 'model')).toEqual(['required']);
  });

  it('reports a missing cloud credential on the apiKey path', () => {
    // The wire code is `api_key`; the path has to be the form's own field name, or the
    // message lands nowhere.
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      provider: 'openai',
      apiKey: '',
    });

    expect(result.success).toBe(false);
    expect(messagesFor(result, 'apiKey')).toEqual(['required']);
  });

  it('reports a missing custom endpoint on the baseUrl path', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      provider: 'deepseek',
      model: 'deepseek-chat',
      baseUrl: '',
    });

    expect(result.success).toBe(false);
    expect(messagesFor(result, 'baseUrl')).toEqual(['required']);
  });

  it('reports one issue per missing field, in vocabulary order', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      provider: 'gemini',
      model: '',
      apiKey: '',
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.map((issue) => issue.path[0])).toEqual(['model', 'apiKey']);
    }
  });

  it('reports an endpoint that is not an absolute http(s) URL', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      baseUrl: 'localhost:11434',
    });

    expect(messagesFor(result, 'baseUrl')).toEqual(['invalid_url']);
  });

  it('reports an overlong model with its own code', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      model: 'a'.repeat(LLM_MODEL_MAX_LENGTH + 1),
    });

    expect(messagesFor(result, 'model')).toEqual(['too_long']);
  });

  it('reports a temperature outside the control range with its own code', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      temperature: LLM_TEMPERATURE_RANGE.max + 1,
    });

    expect(messagesFor(result, 'temperature')).toEqual(['out_of_range']);
  });

  it('reports max tokens outside the control range with its own code', () => {
    const result = llmConfigDraftSchema.safeParse({
      ...completeDraft,
      maxTokens: LLM_MAX_TOKENS_RANGE.min - 1,
    });

    expect(messagesFor(result, 'maxTokens')).toEqual(['out_of_range']);
  });

  it('counts a whitespace-only model as missing, like the API does', () => {
    const result = llmConfigDraftSchema.safeParse({ ...completeDraft, model: '   ' });

    expect(messagesFor(result, 'model')).toEqual(['required']);
  });
});
