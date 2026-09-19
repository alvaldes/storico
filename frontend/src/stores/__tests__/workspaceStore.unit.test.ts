import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/workspace-api', () => ({
  listWorkspaces: vi.fn(),
  createWorkspace: vi.fn(),
  updateWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(),
  getWorkspace: vi.fn(),
}));

import * as api from '@/lib/workspace-api';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useTaskStore } from '@/stores/taskStore';
import {
  getScopedWorkspaceId,
  isScopedWorkspace,
  resetScopedWorkspace,
} from '@/lib/workspace-scope';
import type { Workspace } from '@/types/workspace';
import type { Project } from '@/types/project';
import type { UserStory } from '@/types/story';
import type { Task } from '@/types/task';

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

const project: Project = {
  id: 'project-1',
  name: 'Project 1',
  description: '',
  workspaceId: 'ws-a',
  createdBy: 'user-1',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  storyCount: 1,
};

const story: UserStory = {
  id: 'story-1',
  projectId: 'project-1',
  actor: 'user',
  feature: 'log in',
  benefit: 'access',
  rawText: 'As a user, I want to log in, so that I can access my account',
  status: 'extracted',
  createdAt: '2026-01-01T00:00:00Z',
};

const task: Task = {
  id: 'task-1',
  storyId: 'story-1',
  title: 'Build the login endpoint',
  description: 'Expose POST /login',
  status: 'todo',
  priority: 'high',
  labels: ['api'],
  dependencies: [],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

let fetchProjects: ReturnType<typeof vi.fn>;

describe('workspaceStore — workspace switching hygiene', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    fetchProjects = vi.fn().mockResolvedValue(undefined);
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,
    });
    useProjectStore.setState({
      projects: [project],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: fetchProjects as unknown as () => Promise<void>,
    });
    useStoryStore.setState({
      stories: [story],
      loading: false,
      saving: false,
    });
    useTaskStore.setState({
      tasks: { 'story-1': [task] },
      workspaceTasks: [task],
      extractions: {
        'story-1': {
          extractionId: 'extraction-1',
          status: 'pending',
          userStoryStatus: 'extracting',
          error: null,
          errorCode: null,
        },
      },
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: { 'task-1': ['todo', 'in_progress'] },
    });
  });

  it('clears the previous workspace slices when switching to a different workspace', () => {
    useWorkspaceStore.setState({ currentWorkspace: makeWorkspace('ws-a') });

    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-b');
    expect(useProjectStore.getState().projects).toEqual([]);
    expect(useStoryStore.getState().stories).toEqual([]);
    expect(useTaskStore.getState().workspaceTasks).toEqual([]);
    expect(useTaskStore.getState().extractions).toEqual({});
    expect(fetchProjects).toHaveBeenCalledTimes(1);
  });

  it('keeps the story-keyed task slices that are refetched per story', () => {
    useWorkspaceStore.setState({ currentWorkspace: makeWorkspace('ws-a') });

    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    expect(useTaskStore.getState().tasks).toEqual({ 'story-1': [task] });
    expect(useTaskStore.getState().allowedTransitions).toEqual({
      'task-1': ['todo', 'in_progress'],
    });
  });

  it('does not wipe other stores when re-selecting the same workspace', () => {
    useWorkspaceStore.setState({ currentWorkspace: makeWorkspace('ws-a') });

    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-a', 'Renamed'));

    expect(useWorkspaceStore.getState().currentWorkspace?.name).toBe('Renamed');
    expect(useProjectStore.getState().projects).toEqual([project]);
    expect(useStoryStore.getState().stories).toEqual([story]);
    expect(useTaskStore.getState().workspaceTasks).toEqual([task]);
    expect(fetchProjects).toHaveBeenCalledTimes(1);
  });

  it('switches to a newly created workspace and clears the previous workspace data', async () => {
    useWorkspaceStore.setState({
      currentWorkspace: makeWorkspace('ws-a'),
      workspaces: [makeWorkspace('ws-a')],
    });
    vi.mocked(api.createWorkspace).mockResolvedValue(makeWorkspace('ws-new'));

    const created = await useWorkspaceStore.getState().createWorkspace({
      name: 'New',
      icon: 'building-2',
    });

    expect(created.id).toBe('ws-new');
    expect(useWorkspaceStore.getState().workspaces.map((w) => w.id)).toEqual(['ws-a', 'ws-new']);
    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-new');
    expect(useProjectStore.getState().projects).toEqual([]);
    expect(useStoryStore.getState().stories).toEqual([]);
    expect(useTaskStore.getState().workspaceTasks).toEqual([]);
    expect(fetchProjects).toHaveBeenCalledTimes(1);
  });

  it('routes the replacement through the switch when deleting the current workspace', async () => {
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
      currentWorkspace: makeWorkspace('ws-b'),
    });
    vi.mocked(api.deleteWorkspace).mockResolvedValue(undefined);

    await useWorkspaceStore.getState().deleteWorkspace('ws-b');

    expect(useWorkspaceStore.getState().workspaces.map((w) => w.id)).toEqual(['ws-a']);
    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-a');
    expect(useProjectStore.getState().projects).toEqual([]);
    expect(useStoryStore.getState().stories).toEqual([]);
    expect(useTaskStore.getState().workspaceTasks).toEqual([]);
    expect(fetchProjects).toHaveBeenCalledTimes(1);
  });

  it('observes an explicit "no workspace" scope when the last workspace is deleted', async () => {
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a')],
      currentWorkspace: makeWorkspace('ws-a'),
    });
    vi.mocked(api.deleteWorkspace).mockResolvedValue(undefined);

    await useWorkspaceStore.getState().deleteWorkspace('ws-a');

    expect(useWorkspaceStore.getState().currentWorkspace).toBeNull();
    expect(useWorkspaceStore.getState().workspaces).toEqual([]);
    // "No workspace remains" is an observed scope, not the unobserved state: the deleted
    // workspace's id is denied from here on, so no continuation can still apply.
    expect(getScopedWorkspaceId()).toBeNull();
    expect(isScopedWorkspace('ws-a')).toBe(false);
  });

  it('clears stale data when hydration auto-selects a different workspace', async () => {
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: makeWorkspace('ws-a'),
    });
    vi.mocked(api.listWorkspaces).mockResolvedValue({ workspaces: [makeWorkspace('ws-b')] });

    await useWorkspaceStore.getState().fetchWorkspaces();

    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-b');
    expect(useProjectStore.getState().projects).toEqual([]);
    expect(useStoryStore.getState().stories).toEqual([]);
    expect(fetchProjects).toHaveBeenCalledTimes(1);
  });

  it('keeps the current workspace data when hydration resolves the same workspace', async () => {
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: makeWorkspace('ws-a'),
    });
    vi.mocked(api.listWorkspaces).mockResolvedValue({ workspaces: [makeWorkspace('ws-a')] });

    await useWorkspaceStore.getState().fetchWorkspaces();

    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-a');
    expect(useProjectStore.getState().projects).toEqual([project]);
    expect(useStoryStore.getState().stories).toEqual([story]);
    expect(fetchProjects).toHaveBeenCalledTimes(1);
  });
});

describe('projectStore / storyStore reset', () => {
  beforeEach(() => {
    useProjectStore.setState({
      projects: [project],
      loading: true,
      saving: false,
      error: { friendlyMessage: 'boom', rawDetail: 'boom' },
    });
    useStoryStore.setState({
      stories: [story],
      loading: true,
      saving: false,
    });
  });

  it('projectStore.reset clears projects, loading and error', () => {
    useProjectStore.getState().reset();

    expect(useProjectStore.getState().projects).toEqual([]);
    expect(useProjectStore.getState().loading).toBe(false);
    expect(useProjectStore.getState().error).toBeNull();
  });

  it('storyStore.reset clears stories and loading', () => {
    useStoryStore.getState().reset();

    expect(useStoryStore.getState().stories).toEqual([]);
    expect(useStoryStore.getState().loading).toBe(false);
  });
});

describe('workspaceStore — the scoped workspace id follows currentWorkspace', () => {
  // `projectStore.isScopedWorkspace(ws.id)` and `isScopeUnchanged` both assume the module-level
  // scope inside `workspace-scope` always agrees with `currentWorkspace.id`. Nothing else asserts
  // it, so every path that moves the scope is pinned here: a future path that forgets to move it
  // fails on one of these tests instead of silently accepting another workspace's writes.
  beforeEach(() => {
    vi.clearAllMocks();
    resetScopedWorkspace();
    fetchProjects = vi.fn().mockResolvedValue(undefined);
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,
    });
    useProjectStore.setState({
      projects: [],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: fetchProjects as unknown as () => Promise<void>,
    });
    useStoryStore.setState({ stories: [], loading: false, saving: false });
    useTaskStore.setState({ workspaceTasks: [], extractions: {}, loading: false });
  });

  // The invariant, stated once so each test only has to say which path it drives and the
  // comparison itself cannot drift between tests.
  function expectScopeMatchesCurrentWorkspace(): void {
    expect(getScopedWorkspaceId()).toBe(useWorkspaceStore.getState().currentWorkspace?.id ?? null);
  }

  // Move to `id` through the real switch, so the scope is observed before the path under test.
  function observeScope(id: string): void {
    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace(id));
    expectScopeMatchesCurrentWorkspace();
  }

  it('setCurrentWorkspace: the different-id switch observes the new id', () => {
    observeScope('ws-a');
    expect(getScopedWorkspaceId()).toBe('ws-a');

    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-b'));

    expectScopeMatchesCurrentWorkspace();
    expect(getScopedWorkspaceId()).toBe('ws-b');
  });

  it('setCurrentWorkspace: the same-id rename short-circuit keeps the observed id', () => {
    observeScope('ws-a');

    useWorkspaceStore.getState().setCurrentWorkspace(makeWorkspace('ws-a', 'Renamed'));

    expect(useWorkspaceStore.getState().currentWorkspace?.name).toBe('Renamed');
    expectScopeMatchesCurrentWorkspace();
    expect(getScopedWorkspaceId()).toBe('ws-a');
  });

  it('createWorkspace: observes the workspace it switches to', async () => {
    observeScope('ws-a');
    vi.mocked(api.createWorkspace).mockResolvedValue(makeWorkspace('ws-new'));

    await useWorkspaceStore.getState().createWorkspace({ name: 'New', icon: 'building-2' });

    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-new');
    expectScopeMatchesCurrentWorkspace();
    expect(getScopedWorkspaceId()).toBe('ws-new');
  });

  it('deleteWorkspace: observes the replacement workspace', async () => {
    useWorkspaceStore.setState({ workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')] });
    observeScope('ws-a');
    vi.mocked(api.deleteWorkspace).mockResolvedValue(undefined);

    await useWorkspaceStore.getState().deleteWorkspace('ws-a');

    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-b');
    expectScopeMatchesCurrentWorkspace();
    expect(getScopedWorkspaceId()).toBe('ws-b');
  });

  it('deleteWorkspace: observes an explicit null when the last workspace is deleted', async () => {
    useWorkspaceStore.setState({ workspaces: [makeWorkspace('ws-a')] });
    observeScope('ws-a');
    vi.mocked(api.deleteWorkspace).mockResolvedValue(undefined);

    await useWorkspaceStore.getState().deleteWorkspace('ws-a');

    expect(useWorkspaceStore.getState().currentWorkspace).toBeNull();
    expectScopeMatchesCurrentWorkspace();
    expect(getScopedWorkspaceId()).toBeNull();
  });

  it('fetchWorkspaces: keeps the observed id when hydration finds it still present', async () => {
    observeScope('ws-a');
    vi.mocked(api.listWorkspaces).mockResolvedValue({ workspaces: [makeWorkspace('ws-a')] });

    await useWorkspaceStore.getState().fetchWorkspaces();

    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-a');
    expectScopeMatchesCurrentWorkspace();
    expect(getScopedWorkspaceId()).toBe('ws-a');
  });

  it('fetchWorkspaces: observes the auto-selected workspace when the persisted id is gone', async () => {
    observeScope('ws-a');
    vi.mocked(api.listWorkspaces).mockResolvedValue({ workspaces: [makeWorkspace('ws-b')] });

    await useWorkspaceStore.getState().fetchWorkspaces();

    expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-b');
    expectScopeMatchesCurrentWorkspace();
    expect(getScopedWorkspaceId()).toBe('ws-b');
  });

  it('fetchWorkspaces: observes an explicit null when the persisted id is gone and nothing remains', async () => {
    observeScope('ws-a');
    vi.mocked(api.listWorkspaces).mockResolvedValue({ workspaces: [] });

    await useWorkspaceStore.getState().fetchWorkspaces();

    expect(useWorkspaceStore.getState().currentWorkspace).toBeNull();
    expectScopeMatchesCurrentWorkspace();
    expect(getScopedWorkspaceId()).toBeNull();
  });
});
