import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, within } from '@testing-library/react';
import { toast } from 'sonner';
import { StoryDetail } from '@/components/react/StoryDetail';
import { getLLMConfigStatus } from '@/lib/llm-config-api';
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

// The configuration gate asks the API; every test states its own answer.
vi.mock('@/lib/llm-config-api', () => ({
  getLLMConfigStatus: vi.fn(),
}));

// `toast.error` is the component's only user-facing failure channel, so the test
// spies on it directly instead of asserting on rendered markup.
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const LOCALE: Locale = 'en';
const t = useTranslations(LOCALE);
const STORY_ID = 'story-1';

function makeWorkspace(id: string, role: 'admin' | 'member' = 'admin'): Workspace {
  return {
    id,
    name: id,
    slug: id,
    ownerId: 'user-1',
    role,
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

/**
 * Put every store the component reads into its loaded, network-free state.
 *
 * Both describes below need it, and the gate tests differ from the rest only in the
 * answer the status route gives.
 */
function resetStores() {
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
  });
  // A cached project keeps the contextual-back-link effect synchronous.
  useProjectStore.setState({ projects: [project], loading: false, error: null });
  // Default: this workspace can extract. Only the gate tests move it.
  vi.mocked(getLLMConfigStatus).mockResolvedValue({
    configured: true,
    provider: 'ollama',
    missing: [],
  });
}

describe('StoryDetail — extract control and failure toast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetStores();
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

describe('StoryDetail — configuration gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetStores();
  });

  /** Let the status request settle before asserting on a gate that depends on it. */
  async function settleStatus() {
    await act(async () => {});
  }

  it('disables the extraction and links an admin to the fix when the configuration is incomplete', async () => {
    vi.mocked(getLLMConfigStatus).mockResolvedValue({
      configured: false,
      provider: 'openai',
      missing: ['model', 'api_key'],
    });

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    // The alert only exists once the status has settled, which is what makes the
    // disabled assertion below ordered rather than a race.
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(t.stories.extractionBlockedTitle)).toBeInTheDocument();
    expect(within(alert).getByText(t.stories.extractionBlockedDesc)).toBeInTheDocument();
    expect(within(alert).getByText('Still undefined: Model, API Key')).toBeInTheDocument();
    expect(within(alert).getByRole('link')).toHaveAttribute(
      'href',
      `/${LOCALE}/workspaces/ws-1/settings`,
    );

    expect(screen.getByRole('button', { name: t.stories.detail_extract })).toBeDisabled();
  });

  it('tells a member to ask an admin instead of linking a page they cannot use', async () => {
    vi.mocked(getLLMConfigStatus).mockResolvedValue({
      configured: false,
      provider: 'openai',
      missing: ['api_key'],
    });
    useWorkspaceStore.setState({ currentWorkspace: makeWorkspace('ws-1', 'member') });

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(t.stories.extractionBlockedAskAdmin)).toBeInTheDocument();
    expect(within(alert).getByText('Still undefined: API Key')).toBeInTheDocument();
    // The settings page is admin-only, so a member gets the sentence and no link.
    expect(within(alert).queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.stories.detail_extract })).toBeDisabled();
  });

  it('leaves the extraction enabled when the configuration is complete', async () => {
    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    const button = await screen.findByRole('button', { name: t.stories.detail_extract });

    await settleStatus();

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(button).toBeEnabled();
  });

  it('leaves the extraction enabled when the status cannot be read', async () => {
    // A hiccup in the answer must not lock the user out of the attempt: the API still
    // refuses a configuration that cannot work, so this gate fails open on purpose.
    vi.mocked(getLLMConfigStatus).mockRejectedValue(new Error('502 Bad Gateway'));

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    const button = await screen.findByRole('button', { name: t.stories.detail_extract });

    await settleStatus();

    expect(button).toBeEnabled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('reports a refusal by the API with the configuration copy, not a generic failure', async () => {
    setExtraction(pendingExtraction());
    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    await screen.findByRole('button', { name: t.stories.extraction_pending });

    act(() => {
      setExtraction({
        ...pendingExtraction(),
        status: 'failed',
        error: {
          friendlyMessage: 'Bad Request',
          rawDetail: { error_code: 'LLM_CONFIG_INCOMPLETE' },
          status: 400,
          errorCode: 'LLM_CONFIG_INCOMPLETE',
        },
        errorCode: 'config',
      });
    });

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(t.stories.extractionNeedsConfig));
    // The API's own words are the status text ("Bad Request"), which is the copy the
    // user cannot act on: reaching the config branch is what this asserts.
    expect(toast.error).not.toHaveBeenCalledWith('Bad Request');
  });
});
