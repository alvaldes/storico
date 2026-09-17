import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { useAuthStore } from '@/stores/authStore';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { Dashboard } from '@/components/react/Dashboard';
import type { Workspace } from '@/types/workspace';

const WORKSPACE: Workspace = {
  id: 'ws-a',
  name: 'Alpha',
  slug: 'alpha',
  ownerId: 'user-1',
  role: 'admin',
  memberCount: 1,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

describe('Dashboard', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: '1', email: 'test@test.com', name: 'Test' },
      loading: false,
      isFirstLogin: false,
    });

    useProjectStore.setState({
      projects: [],
      loading: false,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });

    useStoryStore.setState({
      stories: [],
      loading: false,
      fetchStories: vi.fn().mockResolvedValue(undefined),
    });

    useWorkspaceStore.setState({ currentWorkspace: WORKSPACE });
  });

  it('renders dashboard content without error', async () => {
    render(<Dashboard locale="en" />);

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });
  });

  it('scopes the story query to the current workspace, not to a project filter', async () => {
    // The dashboard lists every story of the current workspace. Passing the
    // workspace id as the `projectId` argument makes the API reject the request
    // (no such project), so the dashboard silently showed zero stories.
    const fetchStories = useStoryStore.getState().fetchStories;

    render(<Dashboard locale="en" />);

    await waitFor(() => {
      expect(fetchStories).toHaveBeenCalledWith(undefined, WORKSPACE.id);
    });
  });
});
