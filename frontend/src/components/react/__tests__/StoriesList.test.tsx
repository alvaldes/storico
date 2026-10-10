import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StoriesList } from '@/components/react/StoriesList';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useAuthStore } from '@/stores/authStore';
import { listVersions } from '@/lib/versioning-api';
import { getTranslations } from '@/i18n/utils';
import type { Workspace } from '@/types/workspace';
import type { Project } from '@/types/project';
import type { UserStory } from '@/types/story';
import type { StoryVersion } from '@/types/story';

const t = getTranslations('en');

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

/* ── Story card version badge (versioning-visibility, WU3) ── */

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

async function renderStoryCard(story: UserStory) {
  useStoryStore.setState({
    stories: [story],
    loading: false,
    saving: false,
    fetchStories: vi.fn().mockResolvedValue(undefined),
  });
  render(<StoriesList locale="en" />);
  // The card's identity line (the actor) is the stable sign the row rendered.
  await screen.findByText(story.actor);
}

describe('StoriesList — story card version badge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
      fetchStories: vi.fn().mockResolvedValue(undefined),
    });
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a')],
      currentWorkspace: makeWorkspace('ws-a'),
      loading: false,
      saving: false,
    });
  });

  it('marks the current version and shows the count when a completed run exists', async () => {
    await renderStoryCard(
      makeStory({
        versionSummary: {
          count: 3,
          currentNumber: 2,
          latestNumber: 2,
          latestStatus: 'completed',
        },
      }),
    );

    expect(screen.getByText(`v2 · ${t.versionSelector.current}`)).toBeInTheDocument();
    expect(screen.getByText('3 versions')).toBeInTheDocument();
  });

  it('shows the newest version without the current marker when no run completed', async () => {
    await renderStoryCard(
      makeStory({
        status: 'failed_extraction',
        versionSummary: {
          count: 2,
          currentNumber: null,
          latestNumber: 2,
          latestStatus: 'failed',
        },
      }),
    );

    // The badge names the newest run, but never claims it is current: the
    // story-status badge next to it already carries the failure.
    expect(screen.getByText('v2')).toBeInTheDocument();
    expect(screen.queryByText(`v2 · ${t.versionSelector.current}`)).not.toBeInTheDocument();
    expect(screen.queryByText(t.versionSelector.current)).not.toBeInTheDocument();
  });

  it('invents no version badge or count for a story with no runs', async () => {
    await renderStoryCard(makeStory({ versionSummary: null }));

    expect(screen.queryByText(/^v\d/)).not.toBeInTheDocument();
    expect(screen.queryByText('1 version')).not.toBeInTheDocument();
    expect(screen.queryByText('2 versions')).not.toBeInTheDocument();
    // The rest of the card is untouched.
    expect(screen.getByText(t.stories.status_extracted)).toBeInTheDocument();
  });

  it('uses the singular count for exactly one version', async () => {
    await renderStoryCard(
      makeStory({
        versionSummary: {
          count: 1,
          currentNumber: 1,
          latestNumber: 1,
          latestStatus: 'completed',
        },
      }),
    );

    expect(screen.getByText('v1 · current')).toBeInTheDocument();
    expect(screen.getByText(t.stories.version_count_one)).toBeInTheDocument();
    expect(screen.queryByText('1 versions')).not.toBeInTheDocument();
  });
});

/* ── View in Kanban link (view-in-kanban, WU2) ── */

describe('StoriesList — View in Kanban link', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProjectStore.setState({
      projects: [makeProject('project-a', 'Project A', 'ws-a')],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useWorkspaceStore.setState({
      workspaces: [makeWorkspace('ws-a')],
      currentWorkspace: makeWorkspace('ws-a'),
      loading: false,
      saving: false,
    });
  });

  it('carries the story\'s project AND the story id in the board link', async () => {
    await renderStoryCard(makeStory({ id: 'story-1', projectId: 'project-a' }));

    // The board's cascade never seeds a child level without its parent, so the
    // story's project ALWAYS travels with it.
    const link = screen.getByRole('link', { name: 'Kanban' });
    expect(link).toHaveAttribute('href', '/en/kanban?project=project-a&story=story-1');
  });

  it('stops the click from racing the row\'s navigation to the story detail', async () => {
    const user = userEvent.setup();
    await renderStoryCard(makeStory({ id: 'story-1', projectId: 'project-a' }));

    // jsdom 29 keeps `window.location` unforgeable, so `window.location.assign`
    // itself cannot be spied. The row's handler runs while the click bubbles
    // through React's container, so a click that escapes the link is witnessed
    // by a bubbling listener on `document`: if it fires there, the row's
    // `window.location.assign('/en/stories/<id>')` ran on the way through.
    const escapedClick = vi.fn();
    document.addEventListener('click', escapedClick);

    try {
      await user.click(screen.getByRole('link', { name: 'Kanban' }));

      expect(escapedClick).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener('click', escapedClick);
    }
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
