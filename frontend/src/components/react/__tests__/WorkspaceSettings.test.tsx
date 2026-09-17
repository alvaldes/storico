import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
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
      error: null,
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
