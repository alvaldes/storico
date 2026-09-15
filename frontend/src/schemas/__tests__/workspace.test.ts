import { describe, it, expect } from 'vitest';
import { promptConfigSchema } from '@/schemas/workspace';

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
