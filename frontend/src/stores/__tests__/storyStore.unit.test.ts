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
import { resetScopedWorkspace } from '@/lib/workspace-scope';
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
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const storyA = makeStory('story-ws-a');
const storyB = makeStory('story-ws-b');

describe('storyStore — workspace-scoped inflight fetches', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useStoryStore.setState({ stories: [], loading: false, saving: false, error: null });
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
    useStoryStore.setState({ stories: [], loading: false, saving: false, error: null });
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
});
