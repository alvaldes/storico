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

vi.mock('@/lib/stories-api', () => ({
  listStories: vi.fn(),
  createStory: vi.fn(),
  getStory: vi.fn(),
  updateStory: vi.fn(),
  deleteStory: vi.fn(),
}));

vi.mock('@/lib/workspace-api', () => ({
  listWorkspaces: vi.fn(),
  createWorkspace: vi.fn(),
  updateWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(),
  getWorkspace: vi.fn(),
}));

vi.mock('@/lib/projects-api', () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  getProject: vi.fn(),
}));

import * as api from '@/lib/tasks-api';
import * as storiesApi from '@/lib/stories-api';
import * as projectsApi from '@/lib/projects-api';
import * as workspaceApi from '@/lib/workspace-api';
import { useTaskStore } from '@/stores/taskStore';
import { useProjectStore } from '@/stores/projectStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import {
  setScopedWorkspaceId,
  getScopedWorkspaceId,
  resetScopedWorkspace,
} from '@/lib/workspace-scope';
import type { Task } from '@/types/task';
import type { UserStory } from '@/types/story';
import type { Workspace } from '@/types/workspace';

function makeWorkspace(id: string): Workspace {
  return {
    id,
    name: id,
    slug: id,
    ownerId: 'user-1',
    role: 'admin',
    memberCount: 1,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  };
}

const task: Task = {
  id: 'task-1',
  storyId: 'story-2',
  title: 'Build the login endpoint',
  description: 'Expose POST /login',
  status: 'todo',
  priority: 'high',
  labels: ['api'],
  dependencies: [],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

const story: UserStory = {
  id: 'story-2',
  projectId: 'project-1',
  actor: 'user',
  feature: 'log in',
  benefit: 'access',
  rawText: 'As a user, I want to log in, so that I can access my account',
  status: 'extracted',
  createdAt: '2026-01-01T00:00:00Z',
};

/** A promise the test resolves or rejects by hand, to hold one request inflight on purpose. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('taskStore — extraction error handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    vi.mocked(api.listTasks).mockResolvedValue([]);
    vi.mocked(projectsApi.listProjects).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 100,
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
    });
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,
      error: null,
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

  it('categorizes an HTTP 504 as a timeout, not a generic server failure', async () => {
    vi.mocked(api.startExtraction).mockRejectedValue(
      new ApiRequestError(504, 'Gateway Timeout', 'the model took too long'),
    );

    await useTaskStore.getState().extractTasks('story-3', 'ws-1');

    const extraction = useTaskStore.getState().extractions['story-3'];
    // A timeout is still a failure, but the code lets the view pick its own copy.
    expect(extraction.status).toBe('failed');
    expect(extraction.errorCode).toBe('timeout');
    expect(extraction.userStoryStatus).toBe('failed_extraction');
  });
});

describe('taskStore — stale workspace continuations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    vi.mocked(api.listTasks).mockResolvedValue([]);
    vi.mocked(projectsApi.listProjects).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 100,
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
    });
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,
      error: null,
    });
  });

  it('drops a completed poll that lands after the workspace was discarded', async () => {
    const pendingStatus = deferred<Awaited<ReturnType<typeof api.getExtractionStatus>>>();
    vi.mocked(api.getExtractionStatus).mockImplementationOnce(() => pendingStatus.promise);

    // The store is scoped to ws-a and holds a pending extraction for the story.
    setScopedWorkspaceId('ws-a');
    useTaskStore.setState({
      extractions: {
        'story-1': {
          extractionId: 'ext-1',
          status: 'pending',
          userStoryStatus: 'extracting',
          error: null,
          errorCode: null,
        },
      },
    });
    useWorkspaceStore.setState({
      currentWorkspace: makeWorkspace('ws-a'),
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
    });

    const poll = useTaskStore.getState().pollExtraction('story-1', 'ws-a', 'ext-1');

    // The user switches workspace while the poll is inflight: the switch clears the
    // workspace-scoped slices and moves the scope to ws-b.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    pendingStatus.resolve({
      id: 'ext-1',
      userStoryId: 'story-1',
      modelUsed: 'llama3',
      status: 'completed',
      userStoryStatus: 'extracted',
      errorInfo: null,
      confidenceScore: null,
    });
    await poll;
    // Drain the projects fetch the switch triggered, so no promise leaks into the next test.
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // The discarded workspace's tasks must not be fetched at all...
    expect(api.listTasksByWorkspace).not.toHaveBeenCalled();
    expect(api.listTasks).not.toHaveBeenCalled();
    // ...and the cleared extraction entry must not be resurrected.
    expect(useTaskStore.getState().extractions['story-1']).toBeUndefined();
    expect(storiesApi.getStory).not.toHaveBeenCalled();
  });

  it('drops an extraction start whose response lands after deleting the last workspace', async () => {
    const pendingStart = deferred<Awaited<ReturnType<typeof api.startExtraction>>>();
    vi.mocked(api.startExtraction).mockImplementationOnce(() => pendingStart.promise);
    vi.mocked(workspaceApi.deleteWorkspace).mockResolvedValue(undefined);

    // The user is in ws-a, the only workspace they have (a real switch, so the scope is
    // observed as ws-a rather than left unobserved).
    useWorkspaceStore.setState({ workspaces: [makeWorkspace('ws-a')] });
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-a'));

    const inflight = useTaskStore.getState().extractTasks('story-1', 'ws-a');
    expect(useTaskStore.getState().extractions['story-1'].status).toBe('pending');

    // The user deletes that last workspace while the POST is still inflight. No workspace
    // remains, so "no workspace" is the scope from here on — not the unobserved state.
    await useWorkspaceStore.getState().deleteWorkspace('ws-a');

    pendingStart.resolve({ extractionId: 'ext-1', status: 'pending', modelUsed: 'llama3' });
    await inflight;
    // Drain the projects fetch the switch triggered, so no promise leaks into the next test.
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // No workspace remains, so the continuation has nowhere to land: it must not
    // resurrect the deleted workspace's extraction...
    expect(useTaskStore.getState().extractions['story-1']).toBeUndefined();
    // ...and nothing may keep it alive: no poll to settle it, no workspace-wide fetch
    // for a workspace that no longer exists, no story refresh.
    expect(api.getExtractionStatus).not.toHaveBeenCalled();
    expect(api.listTasksByWorkspace).not.toHaveBeenCalled();
    expect(storiesApi.getStory).not.toHaveBeenCalled();
  });

  it('drops a completed poll whose response lands after deleting the last workspace', async () => {
    vi.mocked(workspaceApi.deleteWorkspace).mockResolvedValue(undefined);

    useWorkspaceStore.setState({ workspaces: [makeWorkspace('ws-a')] });
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-a'));
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    const pendingStatus = deferred<Awaited<ReturnType<typeof api.getExtractionStatus>>>();
    vi.mocked(api.getExtractionStatus).mockImplementationOnce(() => pendingStatus.promise);
    useTaskStore.setState({
      extractions: {
        'story-1': {
          extractionId: 'ext-1',
          status: 'pending',
          userStoryStatus: 'extracting',
          error: null,
          errorCode: null,
        },
      },
    });
    vi.mocked(api.listTasksByWorkspace).mockResolvedValue([task]);
    vi.mocked(storiesApi.getStory).mockResolvedValue(story);

    const poll = useTaskStore.getState().pollExtraction('story-1', 'ws-a', 'ext-1');

    // The user deletes that last workspace while the poll is inflight.
    await useWorkspaceStore.getState().deleteWorkspace('ws-a');

    pendingStatus.resolve({
      id: 'ext-1',
      userStoryId: 'story-1',
      modelUsed: 'llama3',
      status: 'completed',
      userStoryStatus: 'extracted',
      errorInfo: null,
      confidenceScore: null,
    });
    await poll;
    // Drain the projects fetch the switch triggered, so no promise leaks into the next test.
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // A completed poll for a deleted workspace must not write the workspace-scoped slice...
    expect(api.listTasksByWorkspace).not.toHaveBeenCalled();
    expect(api.listTasks).not.toHaveBeenCalled();
    expect(useTaskStore.getState().workspaceTasks).toEqual([]);
    // ...nor resurrect the cleared extraction entry, nor refresh the story.
    expect(useTaskStore.getState().extractions['story-1']).toBeUndefined();
    expect(storiesApi.getStory).not.toHaveBeenCalled();
  });

  it('still refreshes workspace tasks and the story for the current workspace', async () => {
    vi.mocked(api.getExtractionStatus).mockResolvedValue({
      id: 'ext-2',
      userStoryId: 'story-2',
      modelUsed: 'llama3',
      status: 'completed',
      userStoryStatus: 'extracted',
      errorInfo: null,
      confidenceScore: null,
    });
    vi.mocked(api.listTasksByWorkspace).mockResolvedValue([task]);
    vi.mocked(storiesApi.getStory).mockResolvedValue(story);

    // A switch has already been observed and it landed on the poll's own workspace: the
    // user only navigated away from the story view, so nothing may be over-blocked.
    setScopedWorkspaceId('ws-a');

    await useTaskStore.getState().pollExtraction('story-2', 'ws-a', 'ext-2');

    expect(api.listTasksByWorkspace).toHaveBeenCalledWith('ws-a');
    expect(api.listTasks).toHaveBeenCalledWith('story-2');
    expect(useTaskStore.getState().workspaceTasks).toEqual([task]);
    expect(useTaskStore.getState().extractions['story-2'].status).toBe('completed');
    expect(storiesApi.getStory).toHaveBeenCalledWith('story-2');
  });

  it('drops tasks fetched for a discarded workspace and releases the spinner', async () => {
    const pendingTasks = deferred<Task[]>();
    vi.mocked(api.listTasksByWorkspace).mockImplementationOnce(() => pendingTasks.promise);

    setScopedWorkspaceId('ws-a');
    const inflight = useTaskStore.getState().fetchTasksForWorkspace('ws-a');
    // The workspace is discarded while the request is inflight; no newer request exists.
    useTaskStore.getState().setScopeWorkspace('ws-b');

    pendingTasks.resolve([task]);
    await inflight;

    expect(useTaskStore.getState().workspaceTasks).toEqual([]);
    expect(useTaskStore.getState().allowedTransitions).toEqual({});
    expect(useTaskStore.getState().loading).toBe(false);
  });

  it('accepts a completed poll while no switch has been observed yet', async () => {
    vi.mocked(api.getExtractionStatus).mockResolvedValue({
      id: 'ext-3',
      userStoryId: 'story-2',
      modelUsed: 'llama3',
      status: 'completed',
      userStoryStatus: 'extracted',
      errorInfo: null,
      confidenceScore: null,
    });
    vi.mocked(api.listTasksByWorkspace).mockResolvedValue([task]);
    vi.mocked(storiesApi.getStory).mockResolvedValue(story);

    expect(getScopedWorkspaceId()).toBeUndefined();

    await useTaskStore.getState().pollExtraction('story-2', 'ws-a', 'ext-3');

    expect(useTaskStore.getState().extractions['story-2'].status).toBe('completed');
    expect(api.listTasks).toHaveBeenCalledWith('story-2');
    expect(useTaskStore.getState().workspaceTasks).toEqual([task]);
  });

  it('leaves no idle entry behind when the unmount cleanup runs after the switch cleared the slice', () => {
    setScopedWorkspaceId('ws-a');
    useTaskStore.setState({
      extractions: {
        'story-1': {
          extractionId: 'ext-1',
          status: 'pending',
          userStoryStatus: 'extracting',
          error: null,
          errorCode: null,
        },
      },
    });

    // The switch empties the workspace-scoped slice and moves the scope...
    useTaskStore.getState().setScopeWorkspace('ws-b');
    // ...and only then does the story view's unmount cleanup run.
    useTaskStore.getState().resetExtraction('story-1');

    // No entry may be added for the story of the workspace the user left.
    expect(useTaskStore.getState().extractions).toEqual({});
  });

  it('still drops a settled extraction entry so the next visit starts clean', () => {
    useTaskStore.setState({
      extractions: {
        'story-1': {
          extractionId: 'ext-1',
          status: 'failed',
          userStoryStatus: 'failed_extraction',
          error: null,
          errorCode: 'server',
        },
      },
    });

    useTaskStore.getState().resetExtraction('story-1');

    expect(useTaskStore.getState().extractions['story-1']).toBeUndefined();
    expect(useTaskStore.getState().extractions).toEqual({});
  });

  it('does not publish a discarded workspace task into the workspace-wide slice', async () => {
    const pendingUpdate = deferred<Task>();
    vi.mocked(api.updateTask).mockImplementationOnce(() => pendingUpdate.promise);

    setScopedWorkspaceId('ws-a');
    useTaskStore.setState({ tasks: { 'story-2': [task] }, workspaceTasks: [task] });

    // The optimistic write lands before the PUT is awaited...
    const inflight = useTaskStore.getState().updateTask('task-1', { title: 'Renamed' });
    // ...and the user switches while the PUT is still inflight, which empties `workspaceTasks`.
    useTaskStore.getState().setScopeWorkspace('ws-b');

    pendingUpdate.resolve({ ...task, title: 'Renamed' });
    await inflight;

    // `tasks` is story-keyed and deliberately kept, so the server value may land there.
    // `workspaceTasks` is workspace-scoped: the response must not resurrect the entry.
    expect(useTaskStore.getState().workspaceTasks).toEqual([]);
    expect(useTaskStore.getState().updatingTaskId).toBeNull();
  });
});

const failedStatus = {
  id: 'ext-2',
  userStoryId: 'story-2',
  modelUsed: 'llama3',
  status: 'failed',
  userStoryStatus: 'extracted',
  errorInfo: 'boom',
  confidenceScore: null,
};

describe('taskStore — extraction started in a workspace that was discarded', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    vi.mocked(api.listTasks).mockResolvedValue([]);
    vi.mocked(storiesApi.getStory).mockResolvedValue(story);
    vi.mocked(projectsApi.listProjects).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 100,
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
    });
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,
      error: null,
    });
  });

  it('drops an extraction whose start response lands after a real workspace switch', async () => {
    const pendingStart = deferred<Awaited<ReturnType<typeof api.startExtraction>>>();
    vi.mocked(api.startExtraction).mockImplementationOnce(() => pendingStart.promise);

    // The user is in ws-a (a real switch, so the scope is ws-a and not "unobserved").
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
    });
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-a'));

    const inflight = useTaskStore.getState().extractTasks('story-1', 'ws-a');

    // The user switches to ws-b while the POST is still inflight.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    pendingStart.resolve({ extractionId: 'ext-1', status: 'pending', modelUsed: 'llama3' });
    await inflight;
    // Drain the projects fetch the switch triggered, so no promise leaks into the next test.
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // The departed workspace's extraction must not be resurrected as pending...
    expect(useTaskStore.getState().extractions['story-1']).toBeUndefined();
    // ...and no poll may keep it alive in the new workspace.
    expect(api.getExtractionStatus).not.toHaveBeenCalled();
  });

  it('drops a failed start response that lands after a real workspace switch', async () => {
    const pendingStart = deferred<Awaited<ReturnType<typeof api.startExtraction>>>();
    vi.mocked(api.startExtraction).mockImplementationOnce(() => pendingStart.promise);

    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
    });
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-a'));

    const inflight = useTaskStore.getState().extractTasks('story-1', 'ws-a');

    // The user switches to ws-b while the POST is still inflight.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    pendingStart.reject(new ApiRequestError(500, 'Server Error', 'boom'));
    await inflight;
    // Drain the projects fetch the switch triggered, so no promise leaks into the next test.
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // A rejection of the departed workspace's request must not leave its failure entry
    // behind in the new workspace's slices either.
    expect(useTaskStore.getState().extractions['story-1']).toBeUndefined();
  });

  it('does not even mark pending when the request is issued for a workspace that is not current', async () => {
    vi.mocked(api.startExtraction).mockResolvedValue({
      extractionId: 'ext-9',
      status: 'pending',
      modelUsed: 'llama3',
    });

    // A real switch already landed on ws-b...
    useWorkspaceStore.setState({ workspaces: [makeWorkspace('ws-b')] });
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // ...and a stale caller still asks for ws-a's story.
    await useTaskStore.getState().extractTasks('story-1', 'ws-a');

    expect(useTaskStore.getState().extractions['story-1']).toBeUndefined();
    expect(api.getExtractionStatus).not.toHaveBeenCalled();
  });

  it('still marks pending and starts polling when the workspace did not change', async () => {
    vi.mocked(api.startExtraction).mockResolvedValue({
      extractionId: 'ext-2',
      status: 'pending',
      modelUsed: 'llama3',
    });
    vi.mocked(api.getExtractionStatus).mockResolvedValue(failedStatus);

    const inflight = useTaskStore.getState().extractTasks('story-2', 'ws-a');

    // The optimistic entry is written before the POST is awaited.
    expect(useTaskStore.getState().extractions['story-2'].status).toBe('pending');
    expect(useTaskStore.getState().extractions['story-2'].extractionId).toBeNull();

    await inflight;
    await vi.waitFor(() => expect(api.getExtractionStatus).toHaveBeenCalledWith('ext-2'));
    // The poll's own write lands, which proves the extraction id was stored and polled.
    await vi.waitFor(() =>
      expect(useTaskStore.getState().extractions['story-2'].extractionId).toBe('ext-2'),
    );
  });
});
