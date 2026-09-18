import { describe, it, expect, vi, beforeEach } from 'vitest';

import { getLLMConfigStatus } from '@/lib/llm-config-api';
import { api } from '@/lib/api';

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const WORKSPACE_ID = 'ws-1';

/**
 * The readiness answer the extraction gate blocks on.
 *
 * It is the one route in the settings module a member may read, so these tests pin
 * both halves of that contract: the path (which encodes the workspace it is about) and
 * that only field codes travel — never the credential or the endpoint behind them.
 */
describe('getLLMConfigStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reads the member-readable status path for its workspace', async () => {
    vi.mocked(api.get).mockResolvedValue({
      configured: false,
      provider: 'ollama',
      missing: ['model'],
    });

    await getLLMConfigStatus(WORKSPACE_ID);

    expect(api.get).toHaveBeenCalledWith(
      `/api/v1/workspaces/${WORKSPACE_ID}/settings/llm/status`,
    );
  });

  it('passes a complete answer through unchanged', async () => {
    vi.mocked(api.get).mockResolvedValue({
      configured: true,
      provider: 'gemini',
      missing: [],
    });

    expect(await getLLMConfigStatus(WORKSPACE_ID)).toEqual({
      configured: true,
      provider: 'gemini',
      missing: [],
    });
  });

  it('keeps the field codes in the order the API reported them', async () => {
    vi.mocked(api.get).mockResolvedValue({
      configured: false,
      provider: 'openai',
      missing: ['model', 'api_key'],
    });

    // Order is the API's promise, and the UI renders it as written.
    expect((await getLLMConfigStatus(WORKSPACE_ID)).missing).toEqual(['model', 'api_key']);
  });

  it('drops a field code this client cannot label', async () => {
    // A code with no copy to render has no place in a typed field list; leaving it in
    // would give the UI a value no branch handles.
    vi.mocked(api.get).mockResolvedValue({
      configured: false,
      provider: 'openai',
      missing: ['model', 'future_field'],
    });

    expect((await getLLMConfigStatus(WORKSPACE_ID)).missing).toEqual(['model']);
  });

  it('reports a configuration with no gaps as configured', async () => {
    vi.mocked(api.get).mockResolvedValue({
      configured: true,
      provider: 'deepseek',
      missing: [],
    });

    expect((await getLLMConfigStatus(WORKSPACE_ID)).configured).toBe(true);
  });
});
