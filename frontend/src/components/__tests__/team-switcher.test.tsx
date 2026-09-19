import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TeamSwitcher } from '@/components/team-switcher';
import { SidebarProvider } from '@/components/ui/sidebar';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useProjectStore } from '@/stores/projectStore';
import * as workspaceApi from '@/lib/workspace-api';
import { navigate } from 'astro:transitions/client';
import type { Workspace } from '@/types/workspace';

// The team switcher calls the store actions, which call this module. Mocking the
// network layer keeps the test on the switcher's own navigation decisions.
vi.mock('@/lib/workspace-api', () => ({
  listWorkspaces: vi.fn(),
  createWorkspace: vi.fn(),
  updateWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(),
  getWorkspace: vi.fn(),
}));

// `astro:transitions/client` is an Astro virtual module (see vitest.config.ts).
// The specifier resolves to a test-only stub; here it is replaced by a spy so the
// test can observe the exact path the switcher asks the router to navigate to.
vi.mock('astro:transitions/client', () => ({
  navigate: vi.fn(),
}));

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

const teams = [
  { id: 'ws-a', name: 'Alpha', role: 'admin', icon: 'building-2' },
  { id: 'ws-b', name: 'Beta', role: 'member', icon: 'building-2' },
];

function renderSwitcher() {
  return render(
    <SidebarProvider>
      <TeamSwitcher teams={teams} locale="en" />
    </SidebarProvider>,
  );
}

/** Opens the workspace dropdown and clicks the named workspace menu item. */
async function openDropdownAndClick(user: ReturnType<typeof userEvent.setup>, name: RegExp) {
  await user.click(screen.getByRole('button', { name: /Alpha/ }));
  await user.click(await screen.findByRole('menuitem', { name }));
}

describe('TeamSwitcher — workspace navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState({}, '', '/en/dashboard');
    useProjectStore.setState({
      projects: [],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a', 'Alpha'), makeWorkspace('ws-b', 'Beta')],
      currentWorkspace: makeWorkspace('ws-a', 'Alpha'),
      loading: false,
      saving: false,
    });
  });

  it('navigates to the new workspace settings page after a successful create', async () => {
    const user = userEvent.setup();
    vi.mocked(workspaceApi.createWorkspace).mockResolvedValue(makeWorkspace('ws-new', 'New Team'));

    renderSwitcher();

    // Create from the dropdown, as a user with existing workspaces would.
    await user.click(screen.getByRole('button', { name: /Alpha/ }));
    await user.click(await screen.findByRole('menuitem', { name: 'New Workspace' }));
    await user.type(await screen.findByLabelText('Workspace name'), 'New Team');

    // Submitting is what triggers the navigation — nothing before it.
    expect(navigate).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(navigate).toHaveBeenCalledWith('/en/workspaces/ws-new/settings');
    });
  });

  it('does not navigate when switching workspace outside a workspace-scoped path', async () => {
    window.history.pushState({}, '', '/en/dashboard');
    const user = userEvent.setup();

    renderSwitcher();
    await openDropdownAndClick(user, /Beta/);

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-b');
    });
    // The store-driven page reloads itself; the switcher must not force a route.
    expect(navigate).not.toHaveBeenCalled();
  });

  it('keeps the same subpath with the new id when switching inside a workspace-scoped page', async () => {
    window.history.pushState({}, '', '/en/workspaces/ws-a/settings');
    const user = userEvent.setup();

    renderSwitcher();
    await openDropdownAndClick(user, /Beta/);

    await waitFor(() => {
      expect(navigate).toHaveBeenCalledWith('/en/workspaces/ws-b/settings');
    });
  });
});
