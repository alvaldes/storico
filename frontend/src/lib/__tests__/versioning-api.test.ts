import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  listVersions,
  listStoryInvalidations,
  createInvalidation,
  listInvalidations,
  revokeInvalidation,
  fetchRepetition,
} from '@/lib/versioning-api';
import { api } from '@/lib/api';

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

/** A response row in the wire shape `GET /stories/{id}/versions` sends (snake_case). */
const rawCompletedVersion = {
  id: 'ext-2',
  version_number: 2,
  status: 'completed',
  model_used: 'llama3.2',
  provider: 'ollama',
  temperature: 0.1,
  created_at: '2026-10-01T10:00:00Z',
  completed_at: '2026-10-01T10:01:00Z',
  error_info: null,
  is_current: true,
  has_output: true,
};

const rawFailedVersion = {
  id: 'ext-1',
  version_number: 1,
  status: 'failed',
  model_used: 'llama3.2',
  provider: 'ollama',
  temperature: 0.1,
  created_at: '2026-09-30T10:00:00Z',
  completed_at: null,
  error_info: 'Ollama unreachable',
  is_current: false,
  has_output: false,
};

const rawMark = {
  id: 'mark-1',
  reason: 'duplicates a task from v1',
  marked_by: 'user-1',
  marked_at: '2026-10-02T09:00:00Z',
  revoked_by: null,
  revoked_at: null,
};

describe('versioning-api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listVersions', () => {
    it('hits the story versions path and maps the array onto the camelCase type', async () => {
      vi.mocked(api.get).mockResolvedValue([rawFailedVersion, rawCompletedVersion]);

      const versions = await listVersions('story-1');

      expect(api.get).toHaveBeenCalledWith('/api/v1/stories/story-1/versions');
      expect(versions).toEqual([
        {
          id: 'ext-1',
          versionNumber: 1,
          status: 'failed',
          modelUsed: 'llama3.2',
          provider: 'ollama',
          temperature: 0.1,
          createdAt: '2026-09-30T10:00:00Z',
          completedAt: null,
          errorInfo: 'Ollama unreachable',
          isCurrent: false,
          hasOutput: false,
        },
        {
          id: 'ext-2',
          versionNumber: 2,
          status: 'completed',
          modelUsed: 'llama3.2',
          provider: 'ollama',
          temperature: 0.1,
          createdAt: '2026-10-01T10:00:00Z',
          completedAt: '2026-10-01T10:01:00Z',
          errorInfo: null,
          isCurrent: true,
          hasOutput: true,
        },
      ]);
    });
  });

  describe('listStoryInvalidations', () => {
    it('hits the story invalidations path and maps task_id onto taskId', async () => {
      vi.mocked(api.get).mockResolvedValue([
        { ...rawMark, task_id: 'task-1' },
        { ...rawMark, id: 'mark-2', task_id: 'task-2', reason: 'second mark' },
      ]);

      const marks = await listStoryInvalidations('story-1');

      expect(api.get).toHaveBeenCalledWith('/api/v1/stories/story-1/invalidations');
      expect(marks).toEqual([
        {
          id: 'mark-1',
          taskId: 'task-1',
          reason: 'duplicates a task from v1',
          markedBy: 'user-1',
          markedAt: '2026-10-02T09:00:00Z',
          revokedBy: null,
          revokedAt: null,
        },
        {
          id: 'mark-2',
          taskId: 'task-2',
          reason: 'second mark',
          markedBy: 'user-1',
          markedAt: '2026-10-02T09:00:00Z',
          revokedBy: null,
          revokedAt: null,
        },
      ]);
    });
  });

  describe('createInvalidation', () => {
    it('posts the reason to the task invalidations path and maps the mark', async () => {
      vi.mocked(api.post).mockResolvedValue(rawMark);

      const mark = await createInvalidation('task-1', 'duplicates a task from v1');

      expect(api.post).toHaveBeenCalledWith('/api/v1/tasks/task-1/invalidations', {
        reason: 'duplicates a task from v1',
      });
      expect(mark).toEqual({
        id: 'mark-1',
        reason: 'duplicates a task from v1',
        markedBy: 'user-1',
        markedAt: '2026-10-02T09:00:00Z',
        revokedBy: null,
        revokedAt: null,
      });
    });
  });

  describe('listInvalidations', () => {
    it('hits the mark history path and maps every entry', async () => {
      vi.mocked(api.get).mockResolvedValue([rawMark]);

      const marks = await listInvalidations('task-1');

      expect(api.get).toHaveBeenCalledWith('/api/v1/tasks/task-1/invalidations');
      expect(marks).toEqual([
        {
          id: 'mark-1',
          reason: 'duplicates a task from v1',
          markedBy: 'user-1',
          markedAt: '2026-10-02T09:00:00Z',
          revokedBy: null,
          revokedAt: null,
        },
      ]);
    });
  });

  describe('revokeInvalidation', () => {
    it('issues the revoke verb on the current-mark path', async () => {
      vi.mocked(api.delete).mockResolvedValue(undefined);

      await revokeInvalidation('task-1');

      expect(api.delete).toHaveBeenCalledWith('/api/v1/tasks/task-1/invalidations/current');
    });
  });

  describe('fetchRepetition', () => {
    it('hits the repetition read and maps its matches', async () => {
      vi.mocked(api.get).mockResolvedValue({
        matches: [{ version_number: 1, reason: 'same title, earlier version', marked_at: '2026-10-02T09:00:00Z' }],
      });

      const response = await fetchRepetition('task-1');

      expect(api.get).toHaveBeenCalledWith('/api/v1/tasks/task-1/invalidations/repetition');
      expect(response).toEqual({
        matches: [{ versionNumber: 1, reason: 'same title, earlier version', markedAt: '2026-10-02T09:00:00Z' }],
      });
    });
  });
});
