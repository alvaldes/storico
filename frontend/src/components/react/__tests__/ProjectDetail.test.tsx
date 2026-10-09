import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProjectDetail } from '@/components/react/ProjectDetail';
import { useProjectStore } from '@/stores/projectStore';
import type { Project } from '@/types/project';

// One focused test, so the heavy stories list never mounts.
vi.mock('@/components/react/StoriesList', () => ({
  StoriesList: () => <div data-testid="stories-list-stub" />,
}));

function makeProject(id: string, name: string): Project {
  return {
    id,
    name,
    description: '',
    workspaceId: 'ws-1',
    createdBy: 'user-1',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 0,
  };
}

describe('ProjectDetail — View in Kanban link (view-in-kanban, WU2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProjectStore.setState({
      projects: [makeProject('project-1', 'Project One')],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('links the header to the board with this project preselected', async () => {
    render(<ProjectDetail locale="en" projectId="project-1" userId="user-1" />);

    const link = await screen.findByRole('link', { name: 'View in Kanban' });

    expect(link).toHaveAttribute('href', '/en/kanban?project=project-1');
  });
});
