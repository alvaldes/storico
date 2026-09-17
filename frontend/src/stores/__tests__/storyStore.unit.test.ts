import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/stories-api', () => ({
  listStories: vi.fn(),
  createStory: vi.fn(),
  getStory: vi.fn(),
  updateStory: vi.fn(),
  deleteStory: vi.fn(),
}));

vi.mock('@/lib/projects-api', () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  getProject: vi.fn(),
}));

import * as api from '@/lib/stories-api';
import * as projectsApi from '@/lib/projects-api';
import { useStoryStore } from '@/stores/storyStore';
import { useProjectStore } from '@/stores/projectStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { getScopedWorkspaceId, resetScopedWorkspace } from '@/lib/workspace-scope';
import type { UserStory } from '@/types/story';
import type { Workspace } from '@/types/workspace';
import type { PaginatedResponse } from '@/lib/projects-api';

function makeWorkspace(id: string, name = id): Workspace {
  return {
    id,
    name,
    slug: id,
    ownerId: 'user-1',
    role: 'admin',
    memberCount: 1,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  };
}

function makeStory(id: string, projectId = 'p1'): UserStory {
  return {
    id,
    projectId,
    actor: 'user',
    feature: `feature ${id}`,
    benefit: 'a benefit',
    rawText: `As a user, I want feature ${id}, so that I get a benefit`,
    status: 'extracted',
    createdAt: '2026-01-01T00:00:00Z',
  };
}

function page(items: UserStory[]): PaginatedResponse<UserStory> {
  return { items, total: items.length, page: 1, size: 100 };
}

/** A promise the test resolves by hand, to hold one request inflight on purpose. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const storyA = makeStory('story-ws-a');
const storyB = makeStory('story-ws-b');

describe('storyStore — workspace-scoped inflight fetches', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useStoryStore.setState({ stories: [], loading: false, saving: false });
  });

  it('issues one request per workspace even when the project filter is identical', async () => {
    const pendingA = deferred<PaginatedResponse<UserStory>>();
    vi.mocked(api.listStories)
      .mockImplementationOnce(() => pendingA.promise)
      .mockImplementationOnce(() => Promise.resolve(page([storyB])));

    // Same project, different workspace: two different queries.
    const first = useStoryStore.getState().fetchStories('p1', 'ws-a');
    const second = useStoryStore.getState().fetchStories('p1', 'ws-b');

    expect(api.listStories).toHaveBeenCalledTimes(2);
    expect(api.listStories).toHaveBeenNthCalledWith(1, 'p1', 1, 100, 'ws-a');
    expect(api.listStories).toHaveBeenNthCalledWith(2, 'p1', 1, 100, 'ws-b');

    // Drain both so no inflight slot leaks into the next test.
    pendingA.resolve(page([storyA]));
    await Promise.all([first, second]);
  });

  it('keeps the newest workspace stories when a superseded response settles later', async () => {
    const pendingA = deferred<PaginatedResponse<UserStory>>();
    vi.mocked(api.listStories)
      .mockImplementationOnce(() => pendingA.promise)
      .mockImplementationOnce(() => Promise.resolve(page([storyB])));

    const first = useStoryStore.getState().fetchStories('p1', 'ws-a');
    const second = useStoryStore.getState().fetchStories('p1', 'ws-b');

    await second;
    expect(useStoryStore.getState().stories).toEqual([storyB]);

    // The workspace the user just left resolves last — it must not win the race.
    pendingA.resolve(page([storyA]));
    await first;

    expect(useStoryStore.getState().stories).toEqual([storyB]);
  });

  it('ignores an inflight response from the workspace that was just discarded', async () => {
    const pendingA = deferred<PaginatedResponse<UserStory>>();
    vi.mocked(api.listStories).mockImplementationOnce(() => pendingA.promise);

    const inflight = useStoryStore.getState().fetchStories('p1', 'ws-a');
    // The workspace switch discards the previous workspace's slice right away.
    useStoryStore.getState().reset();

    pendingA.resolve(page([storyA]));
    await inflight;

    expect(useStoryStore.getState().stories).toEqual([]);
    expect(useStoryStore.getState().loading).toBe(false);
  });

  it('does not re-add a single story whose fetchStory response lands after reset', async () => {
    const pending = deferred<UserStory>();
    vi.mocked(api.getStory).mockImplementationOnce(() => pending.promise);

    const inflight = useStoryStore.getState().fetchStory('story-ws-a');
    // The workspace switch discards the previous workspace's slice right away.
    useStoryStore.getState().reset();

    pending.resolve(storyA);
    await inflight;

    expect(useStoryStore.getState().stories).toEqual([]);
    expect(useStoryStore.getState().loading).toBe(false);
  });
});

describe('storyStore — created story scope guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    vi.mocked(projectsApi.listProjects).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 100,
    });
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
      currentWorkspace: makeWorkspace('ws-a'),
      loading: false,
      saving: false,
      error: null,
    });
    useStoryStore.setState({ stories: [], loading: false, saving: false });
  });

  it('does not append a story created in a workspace the user has left', async () => {
    const pendingCreate = deferred<UserStory>();
    vi.mocked(api.createStory).mockImplementationOnce(() => pendingCreate.promise);

    const inflight = useStoryStore.getState().createStory({
      projectId: '11111111-1111-1111-1111-111111111111',
      actor: 'user',
      feature: 'log in',
      benefit: 'access',
      rawText: '',
    });
    expect(useStoryStore.getState().saving).toBe(true);

    // The user switches to ws-b while the POST is still inflight.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    pendingCreate.resolve(storyA);
    const created = await inflight;
    // Drain the projects fetch the switch triggered, so no promise leaks into the next test.
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // The new workspace must not gain the story the user created in the old one...
    expect(useStoryStore.getState().stories).toEqual([]);
    // ...but the caller still gets it back, so the form can navigate to it.
    expect(created).toBe(storyA);
    expect(useStoryStore.getState().saving).toBe(false);
  });

  it('still appends the created story when the workspace did not change', async () => {
    vi.mocked(api.createStory).mockResolvedValue(storyA);

    const created = await useStoryStore.getState().createStory({
      projectId: '11111111-1111-1111-1111-111111111111',
      actor: 'user',
      feature: 'log in',
      benefit: 'access',
      rawText: '',
    });

    expect(useStoryStore.getState().stories).toEqual([storyA]);
    expect(created).toBe(storyA);
    expect(useStoryStore.getState().saving).toBe(false);
  });

  it('still releases saving when a create failure lands after the workspace was left', async () => {
    const pendingCreate = deferred<UserStory>();
    vi.mocked(api.createStory).mockImplementationOnce(() => pendingCreate.promise);

    const inflight = useStoryStore.getState().createStory({
      projectId: '11111111-1111-1111-1111-111111111111',
      actor: 'user',
      feature: 'log in',
      benefit: 'access',
      rawText: '',
    });

    // The user switches to ws-b while the POST is still inflight.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    pendingCreate.reject(new Error('boom'));
    // The failure still reaches the caller, whether or not the scope moved.
    await expect(inflight).rejects.toThrow('boom');
    // Drain the projects fetch the switch triggered, so no promise leaks into the next test.
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // `saving` says a mutation is in flight, and this one settled: the scope decides where the
    // result belongs, never whether the request finished.
    expect(useStoryStore.getState().saving).toBe(false);
  });

  it('still rejects a create failure to the caller when the workspace did not change', async () => {
    vi.mocked(api.createStory).mockRejectedValueOnce(new Error('boom'));

    await expect(
      useStoryStore.getState().createStory({
        projectId: '11111111-1111-1111-1111-111111111111',
        actor: 'user',
        feature: 'log in',
        benefit: 'access',
        rawText: '',
      }),
    ).rejects.toThrow('boom');

    // The rejection is the whole caller-facing contract; the flag clears here too.
    expect(useStoryStore.getState().saving).toBe(false);
  });
});

describe('storyStore — updated/deleted story scope guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    vi.mocked(projectsApi.listProjects).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 100,
    });
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
      currentWorkspace: makeWorkspace('ws-a'),
      loading: false,
      saving: false,
      error: null,
    });
    useStoryStore.setState({ stories: [], loading: false, saving: false });
  });

  it('still releases saving when an update failure lands after the workspace was left', async () => {
    // The switch triggers a projects fetch; drain it so no promise leaks into the next test.
    const pendingUpdate = deferred<UserStory>();
    vi.mocked(api.updateStory).mockImplementationOnce(() => pendingUpdate.promise);

    const inflight = useStoryStore.getState().updateStory('story-ws-a', { actor: 'updated' });

    // The user switches to ws-b while the PUT is still inflight.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    pendingUpdate.reject(new Error('boom'));
    // The failure still reaches the caller, whether or not the scope moved.
    await expect(inflight).rejects.toThrow('boom');
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // `saving` says a mutation is in flight, and this one settled: the scope decides where the
    // result belongs, never whether the request finished.
    expect(useStoryStore.getState().saving).toBe(false);
  });

  it('still releases saving when a delete failure lands after the workspace was left', async () => {
    // Same as the update case: the switch triggers a projects fetch that must land cleanly.
    const pendingDelete = deferred<void>();
    vi.mocked(api.deleteStory).mockImplementationOnce(() => pendingDelete.promise);

    const inflight = useStoryStore.getState().deleteStory('story-ws-a');

    // The user switches to ws-b while the DELETE is still inflight.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    pendingDelete.reject(new Error('boom'));
    // The failure still reaches the caller, whether or not the scope moved.
    await expect(inflight).rejects.toThrow('boom');
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // `saving` says a mutation is in flight, and this one settled: the scope decides where the
    // result belongs, never whether the request finished.
    expect(useStoryStore.getState().saving).toBe(false);
  });

  it('still rejects an update failure to the caller when the workspace did not change', async () => {
    vi.mocked(api.updateStory).mockRejectedValueOnce(new Error('boom'));

    await expect(
      useStoryStore.getState().updateStory('story-ws-a', { actor: 'updated' }),
    ).rejects.toThrow('boom');

    // The rejection is the whole caller-facing contract; the flag clears here too.
    expect(useStoryStore.getState().saving).toBe(false);
  });

  it('still rejects a delete failure to the caller when the workspace did not change', async () => {
    vi.mocked(api.deleteStory).mockRejectedValueOnce(new Error('boom'));

    await expect(useStoryStore.getState().deleteStory('story-ws-a')).rejects.toThrow('boom');

    // The rejection is the whole caller-facing contract; the flag clears here too.
    expect(useStoryStore.getState().saving).toBe(false);
  });
});

describe('storyStore — created story append guard with a real observed scope', () => {
  // The describes above start from `resetScopedWorkspace()`, so `scopeAtCall` is `undefined` and
  // the guard takes its fail-open branch. These tests observe a real id first — the branch
  // production is always in after the first switch — so `scopeAtCall` is a concrete id and the
  // comparison has to tell "same id" from "different id" by itself.
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    vi.mocked(projectsApi.listProjects).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 100,
    });
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
      currentWorkspace: null,
      loading: false,
      saving: false,
      error: null,
    });
    useStoryStore.setState({ stories: [], loading: false, saving: false });
  });

  // Observe `id` through the real switch path, then drain its projects fetch so it cannot land
  // after the mutation under test.
  async function observeScope(id: string): Promise<void> {
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace(id));
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));
  }

  it('appends the created story when a real observed scope did not move', async () => {
    await observeScope('ws-a');
    vi.mocked(api.createStory).mockResolvedValue(storyA);

    const created = await useStoryStore.getState().createStory({
      projectId: '11111111-1111-1111-1111-111111111111',
      actor: 'user',
      feature: 'log in',
      benefit: 'access',
      rawText: '',
    });

    expect(getScopedWorkspaceId()).toBe('ws-a');
    expect(useStoryStore.getState().stories).toEqual([storyA]);
    expect(created).toBe(storyA);
    expect(useStoryStore.getState().saving).toBe(false);
  });

  it('drops the created story when a real observed scope moved', async () => {
    await observeScope('ws-a');
    const pendingCreate = deferred<UserStory>();
    vi.mocked(api.createStory).mockImplementationOnce(() => pendingCreate.promise);

    const inflight = useStoryStore.getState().createStory({
      projectId: '11111111-1111-1111-1111-111111111111',
      actor: 'user',
      feature: 'log in',
      benefit: 'access',
      rawText: '',
    });
    // The scope was observed before the call, so the guard compares the real id 'ws-a'.
    expect(getScopedWorkspaceId()).toBe('ws-a');
    expect(useStoryStore.getState().saving).toBe(true);

    // The user switches to ws-b while the POST is still inflight.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));
    expect(getScopedWorkspaceId()).toBe('ws-b');

    pendingCreate.resolve(storyA);
    const created = await inflight;
    // Drain the projects fetch the switch triggered, so no promise leaks into the next test.
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    expect(useStoryStore.getState().stories).toEqual([]);
    // The caller still gets the story back, so the form can navigate to it.
    expect(created).toBe(storyA);
    expect(useStoryStore.getState().saving).toBe(false);
  });
});
