import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/projects-api', () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  getProject: vi.fn(),
}));

import * as api from '@/lib/projects-api';
import { useProjectStore } from '@/stores/projectStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { resetScopedWorkspace } from '@/lib/workspace-scope';
import type { Project } from '@/types/project';
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

function makeProject(id: string, workspaceId: string): Project {
  return {
    id,
    name: id,
    description: '',
    workspaceId,
    createdBy: 'user-1',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 0,
  };
}

function page(items: Project[]): PaginatedResponse<Project> {
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

const projectA = makeProject('project-a', 'ws-a');
const projectB = makeProject('project-b', 'ws-b');

describe('projectStore — workspace-scoped fetch guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
      currentWorkspace: makeWorkspace('ws-a'),
      loading: false,
      saving: false,
      error: null,
    });
    useProjectStore.setState({ projects: [], loading: false, saving: false, error: null });
  });

  it('keeps the newest workspace projects when a superseded response settles later', async () => {
    const pendingA = deferred<PaginatedResponse<Project>>();
    const pendingB = deferred<PaginatedResponse<Project>>();
    vi.mocked(api.listProjects).mockImplementation((workspaceId: string) =>
      workspaceId === 'ws-a' ? pendingA.promise : pendingB.promise,
    );

    // Workspace A's projects are requested and stay inflight.
    const first = useProjectStore.getState().fetchProjects();
    expect(api.listProjects).toHaveBeenNthCalledWith(1, 'ws-a', 1, 100);

    // The user switches to workspace B before A settles; the switch triggers B's fetch.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));
    expect(api.listProjects).toHaveBeenNthCalledWith(2, 'ws-b', 1, 100);

    // B resolves first...
    pendingB.resolve(page([projectB]));
    await vi.waitFor(() => expect(useProjectStore.getState().projects).toEqual([projectB]));

    // ...and the workspace the user just left resolves last. It must not win the race.
    pendingA.resolve(page([projectA]));
    await first;

    expect(useProjectStore.getState().projects).toEqual([projectB]);
    expect(useProjectStore.getState().loading).toBe(false);
  });

  it('ignores an inflight response from the workspace that was just discarded', async () => {
    const pendingA = deferred<PaginatedResponse<Project>>();
    vi.mocked(api.listProjects).mockImplementationOnce(() => pendingA.promise);

    const inflight = useProjectStore.getState().fetchProjects();
    // The switch discards the previous workspace's slice right away.
    useProjectStore.getState().reset();

    pendingA.resolve(page([projectA]));
    await inflight;

    expect(useProjectStore.getState().projects).toEqual([]);
    expect(useProjectStore.getState().loading).toBe(false);
  });

  it('ignores a superseded response that settles before the newest one', async () => {
    const pendingA = deferred<PaginatedResponse<Project>>();
    const pendingB = deferred<PaginatedResponse<Project>>();
    vi.mocked(api.listProjects).mockImplementation((workspaceId: string) =>
      workspaceId === 'ws-a' ? pendingA.promise : pendingB.promise,
    );

    const first = useProjectStore.getState().fetchProjects();
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    // The workspace the user left settles while the newest request is still inflight: it
    // must not write, and it must not release the spinner the newest request still owns.
    pendingA.resolve(page([projectA]));
    await first;

    expect(useProjectStore.getState().projects).toEqual([]);
    expect(useProjectStore.getState().loading).toBe(true);

    pendingB.resolve(page([projectB]));
    await vi.waitFor(() => expect(useProjectStore.getState().projects).toEqual([projectB]));
    expect(useProjectStore.getState().loading).toBe(false);
  });
});

describe('projectStore — created project scope guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
      currentWorkspace: makeWorkspace('ws-a'),
      loading: false,
      saving: false,
      error: null,
    });
    useProjectStore.setState({ projects: [], loading: false, saving: false, error: null });
  });

  it('does not append a project created in a workspace the user has left', async () => {
    const pendingCreate = deferred<Project>();
    const pendingList = deferred<PaginatedResponse<Project>>();
    vi.mocked(api.createProject).mockImplementationOnce(() => pendingCreate.promise);
    vi.mocked(api.listProjects).mockImplementationOnce(() => pendingList.promise);

    const inflight = useProjectStore
      .getState()
      .createProject({ name: 'New project', description: '' });
    expect(useProjectStore.getState().saving).toBe(true);

    // The user switches to ws-b while the POST is still inflight.
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    // ws-b's own list lands first and leaves the new workspace with its real, empty list.
    pendingList.resolve(page([]));
    await vi.waitFor(() => expect(useProjectStore.getState().loading).toBe(false));

    // Only now does the create response for the workspace the user left arrive, so it is
    // the last write and nothing can overwrite the leak away.
    pendingCreate.resolve(projectA);
    const created = await inflight;

    // The new workspace must not gain the project the user created in the old one...
    expect(useProjectStore.getState().projects).toEqual([]);
    // ...but the caller still gets it back, so the form can navigate to it.
    expect(created).toBe(projectA);
    expect(useProjectStore.getState().saving).toBe(false);
  });

  it('still appends the created project when the workspace did not change', async () => {
    vi.mocked(api.createProject).mockResolvedValue(projectA);

    const created = await useProjectStore
      .getState()
      .createProject({ name: 'New project', description: '' });

    expect(useProjectStore.getState().projects).toEqual([projectA]);
    expect(created).toBe(projectA);
    expect(useProjectStore.getState().saving).toBe(false);
  });
});
