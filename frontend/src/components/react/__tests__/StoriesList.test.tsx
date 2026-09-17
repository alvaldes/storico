import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StoriesList } from '@/components/react/StoriesList';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import type { Workspace } from '@/types/workspace';
import type { Project } from '@/types/project';

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

function makeProject(id: string, name: string, workspaceId: string): Project {
  return {
    id,
    name,
    description: '',
    workspaceId,
    createdBy: 'user-1',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 0,
  };
}

let fetchStories: ReturnType<typeof vi.fn>;

describe('StoriesList — workspace scoping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchStories = vi.fn().mockResolvedValue(undefined);
    useProjectStore.setState({
      projects: [makeProject('project-a', 'Project A', 'ws-a')],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useStoryStore.setState({
      stories: [],
      loading: false,
      saving: false,
      error: null,
      fetchStories: fetchStories as unknown as (
        projectId?: string,
        workspaceId?: string,
      ) => Promise<void>,
    });
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a'), makeWorkspace('ws-b')],
      currentWorkspace: makeWorkspace('ws-a'),
      loading: false,
      saving: false,
      error: null,
    });
  });

  it('fetches stories scoped to the current workspace', async () => {
    render(<StoriesList locale="en" />);

    await waitFor(() => expect(fetchStories).toHaveBeenCalledWith(undefined, 'ws-a'));
  });

  it('refetches stories scoped to the new workspace after a switch', async () => {
    render(<StoriesList locale="en" />);
    await waitFor(() => expect(fetchStories).toHaveBeenCalledWith(undefined, 'ws-a'));
    fetchStories.mockClear();

    act(() => {
      useWorkspaceStore.setState({ currentWorkspace: makeWorkspace('ws-b') });
    });

    await waitFor(() => expect(fetchStories).toHaveBeenCalledWith(undefined, 'ws-b'));
  });

  it('drops the project filter chosen in the previous workspace', async () => {
    const user = userEvent.setup();
    render(<StoriesList locale="en" />);
    await waitFor(() => expect(fetchStories).toHaveBeenCalledWith(undefined, 'ws-a'));

    // Select a project filter while workspace A is current.
    await user.click(screen.getAllByRole('combobox')[0]);
    await user.click(await screen.findByRole('option', { name: 'Project A' }));
    await waitFor(() => expect(fetchStories).toHaveBeenCalledWith('project-a', 'ws-a'));
    fetchStories.mockClear();

    act(() => {
      useWorkspaceStore.setState({ currentWorkspace: makeWorkspace('ws-b') });
    });

    // The previous workspace's project filter must not scope the new workspace query.
    await waitFor(() => expect(fetchStories).toHaveBeenCalledWith(undefined, 'ws-b'));
  });
});
