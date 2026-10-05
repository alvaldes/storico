import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AppSidebar } from '@/components/app-sidebar';
import { SidebarProvider } from '@/components/ui/sidebar';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useProjectStore } from '@/stores/projectStore';
import { useAuthStore } from '@/stores/authStore';
import type { Project } from '@/types/project';
import type { Workspace } from '@/types/workspace';

// NavUser imports `signOut` from the auth-astro virtual client; mock it so the
// module resolves under vitest and no real sign-out path is reachable.
vi.mock('auth-astro/client', () => ({ signOut: vi.fn() }));

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

function makeProject(id: string, name: string): Project {
  return {
    id,
    name,
    description: '',
    workspaceId: 'ws-1',
    createdBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 0,
  };
}

function renderSidebar(currentPath = '/en/dashboard') {
  window.history.pushState({}, '', currentPath);
  return render(
    <SidebarProvider>
      <AppSidebar locale="en" currentPath={currentPath} />
    </SidebarProvider>,
  );
}

describe('AppSidebar — Projects entry shape', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: { id: '1', email: 'test@test.com', name: 'Test' },
      loading: false,
    });

    // Seed the store actions so the component's bootstrap effects stay inert.
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-1', 'Alpha')],
      currentWorkspace: makeWorkspace('ws-1', 'Alpha'),
      loading: false,
      saving: false,
      fetchWorkspaces: vi.fn().mockResolvedValue(undefined),
      setCurrentWorkspace: vi.fn(),
      createWorkspace: vi.fn(),
      updateWorkspace: vi.fn(),
      deleteWorkspace: vi.fn(),
    });
    useProjectStore.setState({
      projects: [],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('renders Projects as a flat link (no collapsible trigger) when the workspace has no projects', () => {
    renderSidebar('/en/dashboard');

    // Flat entry: a link named exactly "Projects" pointing at the projects page.
    const link = screen.getByRole('link', { name: 'Projects' });
    expect(link).toHaveAttribute('href', '/en/projects');

    // No collapsible trigger: the "All Projects" sub-link would only exist in the
    // collapsible branch, and the exact-name match avoids matching it.
    expect(screen.queryByRole('button', { name: 'Projects' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'All Projects' })).toBeNull();
  });

  it('marks the flat Projects link active on /projects', () => {
    renderSidebar('/en/projects');

    const link = screen.getByRole('link', { name: 'Projects' });
    expect(link).toHaveAttribute('href', '/en/projects');
    // Base UI maps the button's `active` state to a bare data attribute.
    expect(link).toHaveAttribute('data-active');
  });

  it('marks the flat Projects link active on /projects/{id}', () => {
    renderSidebar('/en/projects/proj-1');

    const link = screen.getByRole('link', { name: 'Projects' });
    expect(link).toHaveAttribute('data-active');
  });

  it('renders Projects as a flat link when the sidebar is collapsed (icon mode)', () => {
    // With a project seeded, the expanded sidebar WOULD render the collapsible;
    // collapsed, the submenu is hidden by CSS, so the item must degrade to a link.
    useProjectStore.setState({ projects: [makeProject('proj-1', 'ACME Website')] });

    window.history.pushState({}, '', '/en/dashboard');
    render(
      <SidebarProvider defaultOpen={false}>
        <AppSidebar locale="en" currentPath="/en/dashboard" />
      </SidebarProvider>,
    );

    const link = screen.getByRole('link', { name: 'Projects' });
    expect(link).toHaveAttribute('href', '/en/projects');
    expect(screen.queryByRole('button', { name: 'Projects' })).toBeNull();
  });

  it('renders Projects as a collapsible with the project sub-entry when the workspace has projects', () => {
    useProjectStore.setState({ projects: [makeProject('proj-1', 'ACME Website')] });

    // A project-scoped path keeps the collapsible open, so the sub-link is visible.
    renderSidebar('/en/projects/proj-1');

    expect(screen.getByRole('button', { name: 'Projects' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'All Projects' })).toBeInTheDocument();

    const projectLink = screen.getByRole('link', { name: 'ACME Website' });
    expect(projectLink).toHaveAttribute('href', '/en/projects/proj-1');
  });
});
