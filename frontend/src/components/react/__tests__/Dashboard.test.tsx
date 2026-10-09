import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { useAuthStore } from '@/stores/authStore';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { Dashboard } from '@/components/react/Dashboard';
import type { Workspace } from '@/types/workspace';
import type { Project } from '@/types/project';
import type { UserStory } from '@/types/story';

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

/* ── Recent-stories version badge (versioning-visibility, WU3b) ── */

function makeProject(id: string, name: string): Project {
  return {
    id,
    name,
    description: '',
    workspaceId: WORKSPACE.id,
    createdBy: 'user-1',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 0,
  };
}

function makeStory(overrides: Partial<UserStory> = {}): UserStory {
  return {
    id: 'story-1',
    projectId: 'project-a',
    actor: 'user',
    feature: 'log in',
    benefit: 'access my account',
    rawText: 'As a user, I want to log in, so that I can access my account',
    status: 'extracted',
    createdAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('Dashboard — recent-stories version badge', () => {
  function seedDashboard(projects: Project[], stories: UserStory[]) {
    useProjectStore.setState({
      projects,
      loading: false,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useStoryStore.setState({
      stories,
      loading: false,
      fetchStories: vi.fn().mockResolvedValue(undefined),
    });
  }

  beforeEach(() => {
    useAuthStore.setState({
      user: { id: '1', email: 'test@test.com', name: 'Test' },
      loading: false,
      isFirstLogin: false,
    });
    useWorkspaceStore.setState({ currentWorkspace: WORKSPACE });
  });

  it('shows the version badge and count for a story with a version summary', async () => {
    seedDashboard([makeProject('project-a', 'Project A')], [
      makeStory({
        versionSummary: {
          count: 3,
          currentNumber: 2,
          latestNumber: 2,
          latestStatus: 'completed',
        },
      }),
    ]);

    render(<Dashboard locale="en" />);

    expect(await screen.findByText('v2 · current')).toBeInTheDocument();
    expect(screen.getByText('3 versions')).toBeInTheDocument();
    // The badge and count lead the row, before the project name and date.
    expect(screen.getByText('Project A')).toBeInTheDocument();
  });

  it('invents no version badge or count for a story with no runs', async () => {
    seedDashboard([makeProject('project-a', 'Project A')], [
      makeStory({ versionSummary: null }),
    ]);

    render(<Dashboard locale="en" />);

    await screen.findByText('As a user, I want to log in, so that I can access my account');
    expect(screen.queryByText(/^v\d/)).not.toBeInTheDocument();
    expect(screen.queryByText(/version/i)).not.toBeInTheDocument();
    // The rest of the row is untouched.
    expect(screen.getByText('Project A')).toBeInTheDocument();
  });
});
