import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiRequestError } from '@/lib/api';

vi.mock('@/lib/tasks-api', () => ({
  startExtraction: vi.fn(),
  getExtractionStatus: vi.fn(),
  listTasks: vi.fn(),
  listTasksByWorkspace: vi.fn(),
  updateTask: vi.fn(),
  updateTaskStatus: vi.fn(),
}));

import * as api from '@/lib/tasks-api';
import { useTaskStore } from '@/stores/taskStore';

describe('taskStore — extraction error handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
    });
  });

  it('marks an HTTP 401 as unauthorized, never as failed', async () => {
    vi.mocked(api.startExtraction).mockRejectedValue(
      new ApiRequestError(401, 'Unauthorized', 'Session expired'),
    );

    await useTaskStore.getState().extractTasks('story-1', 'ws-1');

    const extraction = useTaskStore.getState().extractions['story-1'];
    expect(extraction.status).toBe('unauthorized');
    expect(extraction.status).not.toBe('failed');
    expect(extraction.errorCode).toBe('unauthorized');
    // The story must not be pushed into a failed-extraction state on auth errors.
    expect(extraction.userStoryStatus).toBeNull();
  });

  it('still marks non-auth failures as failed', async () => {
    vi.mocked(api.startExtraction).mockRejectedValue(
      new ApiRequestError(500, 'Server Error', 'boom'),
    );

    await useTaskStore.getState().extractTasks('story-2', 'ws-1');

    const extraction = useTaskStore.getState().extractions['story-2'];
    expect(extraction.status).toBe('failed');
    expect(extraction.errorCode).toBe('server');
    expect(extraction.userStoryStatus).toBe('failed_extraction');
  });
});
