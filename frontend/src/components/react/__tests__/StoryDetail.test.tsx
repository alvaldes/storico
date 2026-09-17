import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { toast } from 'sonner';
import { StoryDetail } from '@/components/react/StoryDetail';
import { useTaskStore, type ExtractionState } from '@/stores/taskStore';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useTranslations, type Locale } from '@/i18n/utils';
import type { Project } from '@/types/project';
import type { UserStory } from '@/types/story';
import type { Workspace } from '@/types/workspace';

// The store consumes these; the component's mount effects must settle without a backend.
vi.mock('@/lib/tasks-api', () => ({
  startExtraction: vi.fn(),
  getExtractionStatus: vi.fn(),
  listTasks: vi.fn(),
  listTasksByWorkspace: vi.fn(),
  updateTask: vi.fn(),
  updateTaskStatus: vi.fn(),
}));

vi.mock('@/lib/projects-api', () => ({
  getProject: vi.fn(),
  listProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
}));

// `toast.error` is the component's only user-facing failure channel, so the test
// spies on it directly instead of asserting on rendered markup.
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const LOCALE: Locale = 'en';
const t = useTranslations(LOCALE);
const STORY_ID = 'story-1';

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

const story: UserStory = {
  id: STORY_ID,
  projectId: 'project-1',
  actor: 'user',
  feature: 'log in',
  benefit: 'access my account',
  rawText: 'As a user, I want to log in, so that I can access my account',
  status: 'pending_extraction',
  createdAt: '2026-01-01T00:00:00Z',
};

const project: Project = {
  id: 'project-1',
  name: 'Project One',
  description: '',
  workspaceId: 'ws-1',
  createdBy: 'user-1',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  storyCount: 0,
};

/** Replace the whole slice: `undefined` means "no entry for the story at all". */
function setExtraction(extraction: ExtractionState | undefined) {
  useTaskStore.setState({ extractions: extraction ? { [STORY_ID]: extraction } : {} });
}

function idleExtraction(): ExtractionState {
  return {
    extractionId: null,
    status: 'idle',
    userStoryStatus: null,
    error: null,
    errorCode: null,
  };
}

function pendingExtraction(): ExtractionState {
  return {
    extractionId: 'ext-1',
    status: 'pending',
    userStoryStatus: 'extracting',
    error: null,
    errorCode: null,
  };
}

/** The extract control's observable state: its accessible label and enabled flag. */
function extractControlState(button: HTMLElement) {
  const el = button as HTMLButtonElement;
  return { label: el.textContent, disabled: el.disabled };
}

describe('StoryDetail — extract control and failure toast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      // The mount effects fetch; stub the actions so nothing reaches the network.
      fetchTasks: vi.fn().mockResolvedValue(undefined),
      extractTasks: vi.fn().mockResolvedValue(undefined),
    });
    useStoryStore.setState({
      stories: [story],
      loading: false,
      saving: false,
      fetchStory: vi.fn().mockResolvedValue(undefined),
    });
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: makeWorkspace('ws-1'),
      loading: false,
      saving: false,
      error: null,
    });
    // A cached project keeps the contextual-back-link effect synchronous.
    useProjectStore.setState({ projects: [project], loading: false, error: null });
  });

  it('renders the same extract control for a missing extraction entry and an idle one', async () => {
    // `resetExtraction` deletes the entry, so "no entry at all" is a state this
    // component renders in normal use. It must be indistinguishable from an entry
    // explicitly marked `idle`, which is the equivalence the deletion relies on.
    const withoutEntryView = render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    const withoutEntry = await screen.findByRole('button', { name: t.stories.detail_extract });
    withoutEntryView.unmount();

    setExtraction(idleExtraction());
    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    const withIdleEntry = await screen.findByRole('button', { name: t.stories.detail_extract });

    // Same accessible label and same enabled state, so both states are one state.
    expect(extractControlState(withIdleEntry)).toEqual(extractControlState(withoutEntry));
    expect(withIdleEntry).toBeEnabled();
  });

  it('toasts the timeout copy only when a pending extraction settles as failed with the timeout code', async () => {
    setExtraction(pendingExtraction());
    const timeoutView = render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    // The effect only toasts on the transition out of an observed `pending`.
    await screen.findByRole('button', { name: t.stories.extraction_pending });

    act(() => {
      setExtraction({
        ...pendingExtraction(),
        status: 'failed',
        error: {
          friendlyMessage: 'Extraction failed',
          rawDetail: 'gateway timeout',
          status: 504,
        },
        errorCode: 'timeout',
      });
    });

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(t.stories.extractionTimeout));
    timeoutView.unmount();

    // A `failed` extraction with any other code must not reuse the timeout copy.
    vi.mocked(toast.error).mockClear();
    setExtraction(pendingExtraction());
    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    await screen.findByRole('button', { name: t.stories.extraction_pending });

    act(() => {
      setExtraction({
        ...pendingExtraction(),
        status: 'failed',
        error: { friendlyMessage: 'Extraction failed', rawDetail: 'boom', status: 500 },
        errorCode: 'server',
      });
    });

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Extraction failed'));
    expect(toast.error).not.toHaveBeenCalledWith(t.stories.extractionTimeout);
  });
});
