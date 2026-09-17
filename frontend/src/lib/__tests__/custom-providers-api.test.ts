import { describe, it, expect, vi, beforeEach } from 'vitest';

import {
  createCustomProvider,
  listCustomProviders,
  renameCustomProvider,
} from '@/lib/custom-providers-api';
import {
  ADD_CUSTOM_PROVIDER_VALUE,
  KNOWN_PROVIDERS,
  isKnownProvider,
  isValidProviderName,
  normalizeProviderName,
} from '@/lib/llm-providers';
import { customProviderNameSchema } from '@/schemas/workspace';
import { api } from '@/lib/api';

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

const WORKSPACE_ID = 'ws-1';
const PROVIDER_ID = 'cp-1';

/** A response row in the wire shape the backend sends (snake_case). */
const rawProvider = {
  id: PROVIDER_ID,
  workspace_id: WORKSPACE_ID,
  name: 'deepseek',
  created_at: '2026-09-18T10:00:00Z',
  updated_at: '2026-09-18T10:00:00Z',
};

describe('custom-providers-api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listCustomProviders', () => {
    it('reads the workspace registry path', async () => {
      vi.mocked(api.get).mockResolvedValue([rawProvider]);

      await listCustomProviders(WORKSPACE_ID);

      expect(api.get).toHaveBeenCalledWith(`/api/v1/workspaces/${WORKSPACE_ID}/settings/providers`);
    });

    it('maps the snake_case response onto the camelCase type', async () => {
      vi.mocked(api.get).mockResolvedValue([rawProvider]);

      const providers = await listCustomProviders(WORKSPACE_ID);

      // `workspaceId` is the field the UI reads; a mapping that only renames the
      // list would leave it undefined and the registry unrenderable.
      expect(providers).toEqual([
        {
          id: PROVIDER_ID,
          workspaceId: WORKSPACE_ID,
          name: 'deepseek',
          createdAt: '2026-09-18T10:00:00Z',
          updatedAt: '2026-09-18T10:00:00Z',
        },
      ]);
    });

    it('returns an empty list for a workspace with no providers', async () => {
      vi.mocked(api.get).mockResolvedValue([]);

      expect(await listCustomProviders(WORKSPACE_ID)).toEqual([]);
    });
  });

  describe('createCustomProvider', () => {
    it('posts the name in the snake_case wire shape', async () => {
      vi.mocked(api.post).mockResolvedValue(rawProvider);

      await createCustomProvider(WORKSPACE_ID, { name: 'deepseek' });

      expect(api.post).toHaveBeenCalledWith(
        `/api/v1/workspaces/${WORKSPACE_ID}/settings/providers`,
        { name: 'deepseek' },
      );
    });

    it('returns the created provider mapped to camelCase', async () => {
      vi.mocked(api.post).mockResolvedValue(rawProvider);

      const created = await createCustomProvider(WORKSPACE_ID, { name: 'deepseek' });

      expect(created.workspaceId).toBe(WORKSPACE_ID);
      expect(created.name).toBe('deepseek');
    });
  });

  describe('renameCustomProvider', () => {
    it('patches the provider by id with the new name', async () => {
      vi.mocked(api.patch).mockResolvedValue({ ...rawProvider, name: 'groq' });

      await renameCustomProvider(WORKSPACE_ID, PROVIDER_ID, { name: 'groq' });

      expect(api.patch).toHaveBeenCalledWith(
        `/api/v1/workspaces/${WORKSPACE_ID}/settings/providers/${PROVIDER_ID}`,
        { name: 'groq' },
      );
    });

    it('returns the renamed provider', async () => {
      vi.mocked(api.patch).mockResolvedValue({ ...rawProvider, name: 'groq' });

      const renamed = await renameCustomProvider(WORKSPACE_ID, PROVIDER_ID, { name: 'groq' });

      expect(renamed.name).toBe('groq');
      expect(renamed.id).toBe(PROVIDER_ID);
    });
  });
});

describe('provider vocabulary', () => {
  it('treats only the four first-class names as known', () => {
    for (const provider of KNOWN_PROVIDERS) {
      expect(isKnownProvider(provider)).toBe(true);
    }
    expect(isKnownProvider('deepseek')).toBe(false);
    expect(isKnownProvider('')).toBe(false);
  });

  it('normalizes a submitted name the way the backend does', () => {
    expect(normalizeProviderName('  Groq  ')).toBe('groq');
    expect(normalizeProviderName('DEEPSEEK')).toBe('deepseek');
  });

  it.each(['deepseek', 'groq', 'a', 'my-gateway', 'vendor.v2', 'local_llm'])(
    'accepts the slug %s',
    (name) => {
      expect(isValidProviderName(name)).toBe(true);
    },
  );

  it('accepts a trailing separator', () => {
    // The rule constrains the character set, length and first character, not the
    // last one. Tightening that is a backend decision this copy must not make alone.
    expect(isValidProviderName('my-gateway-')).toBe(true);
  });

  it.each(['', '   ', 'DeepSeek', 'has space', '-leading', 'a'.repeat(51), 'ünicode'])(
    'rejects %s',
    (name) => {
      expect(isValidProviderName(name)).toBe(false);
    },
  );

  it('keeps the add option out of the name space', () => {
    // The sentinel travels through the select's value, so it must be impossible for
    // a registered provider to collide with it.
    expect(isValidProviderName(ADD_CUSTOM_PROVIDER_VALUE)).toBe(false);
  });
});

describe('customProviderNameSchema', () => {
  it('normalizes the submitted name', () => {
    expect(customProviderNameSchema.parse({ name: '  Groq  ' })).toEqual({ name: 'groq' });
  });

  it.each(['', '   ', 'has space', '-leading', 'a'.repeat(51)])(
    'rejects %s before the round trip',
    (name) => {
      expect(customProviderNameSchema.safeParse({ name }).success).toBe(false);
    },
  );

  it('accepts a name that only becomes valid after normalization', () => {
    // The backend normalizes before validating, so the frontend must too; otherwise
    // a user typing `Groq` would be told the name is invalid.
    expect(customProviderNameSchema.safeParse({ name: 'Groq' }).success).toBe(true);
  });
});
