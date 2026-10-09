import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProjectsList } from '@/components/react/ProjectsList';
import { useProjectStore } from '@/stores/projectStore';
import type { Project } from '@/types/project';

function makeProject(id: string, name: string): Project {
  return {
    id,
    name,
    description: '',
    workspaceId: 'ws-a',
    createdBy: 'user-1',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 0,
  };
}

describe('ProjectsList — View in Kanban link (view-in-kanban, WU2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProjectStore.setState({
      projects: [makeProject('project-a', 'Project A'), makeProject('project-b', 'Project B')],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('exposes one Kanban deep link per card, each carrying that card\'s project id', async () => {
    render(<ProjectsList locale="en" />);

    await screen.findByText('Project A');

    const links = screen.getAllByRole('link', { name: 'View in Kanban' });
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute('href', '/en/kanban?project=project-a');
    expect(links[1]).toHaveAttribute('href', '/en/kanban?project=project-b');
  });

  it('stops the click from racing the card\'s own navigation to the project detail', async () => {
    const user = userEvent.setup();
    render(<ProjectsList locale="en" />);
    await screen.findByText('Project A');

    // jsdom 29 keeps `window.location` unforgeable, so `window.location.assign`
    // itself cannot be spied. The card's handler runs while the click bubbles
    // through React's container, so a click that escapes the link is witnessed
    // by a bubbling listener on `document`: if it fires there, the card's
    // `window.location.assign('/en/projects/<id>')` ran on the way through.
    const escapedClick = vi.fn();
    document.addEventListener('click', escapedClick);

    try {
      const links = screen.getAllByRole('link', { name: 'View in Kanban' });
      expect(links).toHaveLength(2);
      expect(links[0]).toHaveAttribute('href', '/en/kanban?project=project-a');
      await user.click(links[0]);

      expect(escapedClick).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener('click', escapedClick);
    }
  });
});
