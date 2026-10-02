import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StoriesList } from '@/components/react/StoriesList';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useAuthStore } from '@/stores/authStore';
import { listVersions } from '@/lib/versioning-api';
import { useTranslations } from '@/i18n/utils';
import type { Workspace } from '@/types/workspace';
import type { Project } from '@/types/project';
import type { UserStory } from '@/types/story';
import type { StoryVersion } from '@/types/story';

const t = useTranslations('en');

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

vi.mock('@/lib/versioning-api', () => ({
  listVersions: vi.fn(),
  createInvalidation: vi.fn(),
  listInvalidations: vi.fn(),
  revokeInvalidation: vi.fn(),
  fetchRepetition: vi.fn(),
}));

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

/* ── Delete dialog version count (0.9.0 slice b, W6-A) ── */

function makeVersion(overrides: Partial<StoryVersion> = {}): StoryVersion {
  return {
    id: 'ext-1',
    versionNumber: 1,
    status: 'completed',
    modelUsed: 'llama3.2',
    provider: 'ollama',
    temperature: 0.1,
    createdAt: '2026-09-30T10:00:00Z',
    completedAt: '2026-09-30T10:01:00Z',
    errorInfo: null,
    isCurrent: true,
    hasOutput: true,
    ...overrides,
  };
}

const deletableStory: UserStory = {
  id: 'story-1',
  projectId: 'project-a',
  actor: 'user',
  feature: 'log in',
  benefit: 'access my account',
  rawText: 'As a user, I want to log in, so that I can access my account',
  status: 'extracted',
  createdAt: '2026-01-01T00:00:00Z',
};

describe('StoriesList — delete dialog version count', () => {
  let deleteStorySpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    deleteStorySpy = vi.fn().mockResolvedValue(undefined);
    useProjectStore.setState({
      projects: [makeProject('project-a', 'Project A', 'ws-a')],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useStoryStore.setState({
      stories: [deletableStory],
      loading: false,
      saving: false,
      fetchStories: vi.fn().mockResolvedValue(undefined),
      deleteStory: deleteStorySpy as unknown as (id: string) => Promise<void>,
    });
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a')],
      currentWorkspace: makeWorkspace('ws-a'),
      loading: false,
      saving: false,
    });
    // The signed-in user is the workspace owner, so the delete control renders.
    useAuthStore.setState({ user: { id: 'user-1', email: 'u@example.com', name: 'User One' } });
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: 'ext-2', versionNumber: 2 }),
      makeVersion({ id: 'ext-1', versionNumber: 1, isCurrent: false }),
    ]);
  });

  it('fetches the version count when the dialog opens and names it', async () => {
    const user = userEvent.setup();
    render(<StoriesList locale="en" />);

    await user.click(await screen.findByRole('button', { name: t.common.delete }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(t.stories.delete_confirm_versions.replace('{count}', '2'))).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: t.common.delete })).toBeEnabled();
    expect(listVersions).toHaveBeenCalledWith('story-1');
  });

  it('keeps the confirm enabled with the fallback sentence when the version read fails', async () => {
    const user = userEvent.setup();
    vi.mocked(listVersions).mockRejectedValue(new Error('502 Bad Gateway'));
    render(<StoriesList locale="en" />);

    await user.click(await screen.findByRole('button', { name: t.common.delete }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(t.stories.delete_confirm_versions_unknown)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: t.common.delete })).toBeEnabled();
  });

  it('issues no delete request when the dialog is cancelled', async () => {
    const user = userEvent.setup();
    render(<StoriesList locale="en" />);

    await user.click(await screen.findByRole('button', { name: t.common.delete }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: t.common.cancel }));

    expect(deleteStorySpy).not.toHaveBeenCalled();
  });

  it('hides the delete control from a member who is neither owner nor admin', async () => {
    useWorkspaceStore.setState({
      currentWorkspace: { ...makeWorkspace('ws-a'), ownerId: 'owner-9', role: 'member' },
    });
    render(<StoriesList locale="en" />);

    await screen.findByText(deletableStory.actor);

    expect(screen.queryByRole('button', { name: t.common.delete })).not.toBeInTheDocument();
  });
});
