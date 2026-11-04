import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkspaceSettings } from '@/components/react/WorkspaceSettings';
import { useAuthStore } from '@/stores/authStore';
import { useProjectStore } from '@/stores/projectStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import * as workspaceApi from '@/lib/workspace-api';
import type { Workspace } from '@/types/workspace';

vi.mock('@/lib/workspace-api', () => ({
  listWorkspaces: vi.fn(),
  createWorkspace: vi.fn(),
  updateWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(),
  getWorkspace: vi.fn(),
}));

// The heavy children run their own API work and are not what this test observes;
// the subject is the URL-id/store agreement effect.
vi.mock('@/components/react/MemberManagement', () => ({
  MemberManagement: () => <div data-testid="member-management" />,
}));
vi.mock('@/components/react/LLMConfigEditor', () => ({
  LLMConfigEditor: () => <div data-testid="llm-config-editor" />,
}));
vi.mock('@/components/react/PromptConfigEditor', () => ({
  PromptConfigEditor: () => <div data-testid="prompt-config-editor" />,
}));
// Same reason as its neighbours: the form fetches the Trello status on mount, and
// that fetch has nowhere to go in jsdom. Left real, it renders its load-error line
// here and the assertions below would be reading a state this test never set up.
// Its own behaviour is covered in TrelloCredentialsForm.test.tsx.
vi.mock('@/components/react/TrelloCredentialsForm', () => ({
  TrelloCredentialsForm: () => <div data-testid="trello-credentials-form" />,
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

// Captured once, before any test replaces it: the spy below must still perform the
// real switch so the assertions observe real store state, not just call records.
const realSetCurrentWorkspace = useWorkspaceStore.getState().setCurrentWorkspace;

let setCurrentWorkspaceSpy: ReturnType<typeof vi.fn<typeof realSetCurrentWorkspace>>;

describe('WorkspaceSettings — URL id adoption', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setCurrentWorkspaceSpy = vi.fn(realSetCurrentWorkspace);
    useAuthStore.setState({
      user: { id: '1', email: 'test@test.com', name: 'Test' },
      loading: false,
      isFirstLogin: false,
    });
    useProjectStore.setState({
      projects: [],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,
      setCurrentWorkspace: setCurrentWorkspaceSpy as unknown as typeof realSetCurrentWorkspace,
    });
    vi.mocked(workspaceApi.getWorkspace).mockResolvedValue(makeWorkspace('ws-b'));
  });

  it('adopts the URL workspace id when it differs from the store', async () => {
    const workspaceA = makeWorkspace('ws-a', 'Alpha');
    const workspaceB = makeWorkspace('ws-b', 'Beta');
    useWorkspaceStore.setState({
      workspaces: [workspaceA, workspaceB],
      currentWorkspace: workspaceA,
    });

    render(<WorkspaceSettings locale="en" workspaceId="ws-b" />);

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentWorkspace).toEqual(workspaceB);
    });
    expect(setCurrentWorkspaceSpy).toHaveBeenCalledWith(workspaceB);
  });

  it('does not call setCurrentWorkspace again when URL id and store already agree', async () => {
    const workspaceB = makeWorkspace('ws-b', 'Beta');
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a', 'Alpha'), workspaceB],
      currentWorkspace: workspaceB,
    });

    render(<WorkspaceSettings locale="en" workspaceId="ws-b" />);

    // Re-selecting the same workspace on every render would restart its data load.
    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentWorkspace?.id).toBe('ws-b');
    });
    expect(setCurrentWorkspaceSpy).not.toHaveBeenCalled();
  });

  it('leaves the store untouched when the URL id is not in the loaded workspaces', async () => {
    const workspaceA = makeWorkspace('ws-a', 'Alpha');
    useWorkspaceStore.setState({
      workspaces: [workspaceA],
      currentWorkspace: workspaceA,
    });

    render(<WorkspaceSettings locale="en" workspaceId="ws-unknown" />);

    await waitFor(() => {
      expect(workspaceApi.getWorkspace).toHaveBeenCalledWith('ws-unknown');
    });
    expect(setCurrentWorkspaceSpy).not.toHaveBeenCalled();
    expect(useWorkspaceStore.getState().currentWorkspace).toEqual(workspaceA);
  });
});

/* ── The tabs (S11) ──
 *
 * The page is organized in four reachable areas — LLM, Prompts, Integrations,
 * Members — as tabs, with the workspace identity card above them and the danger
 * zone at the end of Members. Tab switching is client state only: no routing, no
 * URL sync. Each tab's component owns its own loading state, so a tab whose data
 * has not settled shows its own spinner, never a broken empty form.
 */
describe('WorkspaceSettings — tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The owner sees the danger zone; its placement is what these tests pin.
    useAuthStore.setState({
      user: { id: 'user-1', email: 'test@test.com', name: 'Test' },
      loading: false,
      isFirstLogin: false,
    });
    useProjectStore.setState({
      projects: [],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,
    });
    vi.mocked(workspaceApi.getWorkspace).mockResolvedValue(makeWorkspace('ws-b'));
  });

  it('renders the four tabs with LLM first and selected', async () => {
    render(<WorkspaceSettings locale="en" workspaceId="ws-b" />);

    expect(await screen.findByTestId('llm-config-editor')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'LLM' })).toHaveAttribute('aria-selected', 'true');
    for (const name of ['Prompts', 'Integrations', 'Members']) {
      expect(screen.getByRole('tab', { name })).toHaveAttribute('aria-selected', 'false');
    }
  });

  it('switching tabs shows the right area and hides the others', async () => {
    const user = userEvent.setup();
    render(<WorkspaceSettings locale="en" workspaceId="ws-b" />);
    await screen.findByTestId('llm-config-editor');

    await user.click(screen.getByRole('tab', { name: 'Prompts' }));
    expect(screen.getByTestId('prompt-config-editor')).toBeVisible();
    expect(screen.getByTestId('llm-config-editor')).not.toBeVisible();

    await user.click(screen.getByRole('tab', { name: 'Integrations' }));
    expect(screen.getByTestId('trello-credentials-form')).toBeVisible();
    expect(screen.getByTestId('prompt-config-editor')).not.toBeVisible();

    await user.click(screen.getByRole('tab', { name: 'Members' }));
    expect(screen.getByTestId('member-management')).toBeVisible();
    expect(screen.getByTestId('trello-credentials-form')).not.toBeVisible();
  });

  it('keeps the danger zone at the end of the Members tab, hidden elsewhere', async () => {
    const user = userEvent.setup();
    render(<WorkspaceSettings locale="en" workspaceId="ws-b" />);
    await screen.findByTestId('llm-config-editor');

    // While another tab is up, the danger zone is not on the page: the button is
    // hidden along with its panel (role queries need `hidden: true` to see it).
    expect(
      screen.getByRole('button', { name: 'Delete workspace', hidden: true }),
    ).not.toBeVisible();

    await user.click(screen.getByRole('tab', { name: 'Members' }));

    expect(screen.getByTestId('member-management')).toBeVisible();
    expect(
      screen.getByText('Delete workspace', { selector: '[data-slot=card-title]' }),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Delete workspace' })).toBeVisible();
  });

  it('keeps the workspace identity above the tabs', async () => {
    render(<WorkspaceSettings locale="en" workspaceId="ws-b" />);
    await screen.findByTestId('llm-config-editor');

    // The identity card is the one holding the workspace name input; the tablist
    // must follow it in document order and never live inside it.
    const identityCard = screen.getByDisplayValue('ws-b').closest('[data-slot=card]');
    const tablist = screen.getByRole('tablist');
    expect(identityCard).not.toBeNull();
    expect(identityCard!.contains(tablist)).toBe(false);
    expect(
      identityCard!.compareDocumentPosition(tablist) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
