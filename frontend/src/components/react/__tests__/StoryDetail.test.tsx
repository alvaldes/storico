import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { StoryDetail } from '@/components/react/StoryDetail';
import { getLLMConfigStatus } from '@/lib/llm-config-api';
import { listVersions } from '@/lib/versioning-api';
import * as versioningApi from '@/lib/versioning-api';
import { useTaskStore, type ExtractionState } from '@/stores/taskStore';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useAuthStore } from '@/stores/authStore';
import { useTranslations, type Locale } from '@/i18n/utils';
import * as tasksApi from '@/lib/tasks-api';
import type { Project } from '@/types/project';
import type { Task } from '@/types/task';
import type { UserStory } from '@/types/story';
import type { StoryVersion } from '@/types/story';
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

// The version selector read: the mount effect fetches it, and every test states
// its own answer (an empty history by default, so pre-existing cases are unaffected).
vi.mock('@/lib/versioning-api', () => ({
  listVersions: vi.fn(),
  listStoryInvalidations: vi.fn(),
  createInvalidation: vi.fn(),
  listInvalidations: vi.fn(),
  revokeInvalidation: vi.fn(),
  fetchRepetition: vi.fn(),
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
    versionNumber: null,
  };
}

function pendingExtraction(): ExtractionState {
  return {
    extractionId: 'ext-1',
    status: 'pending',
    userStoryStatus: 'extracting',
    error: null,
    errorCode: null,
    versionNumber: 2,
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
  // The signed-in user: the owner-or-admin gate (`canManageVersions`) reads it.
  // `user-1` is the fixture workspaces' owner, so the default state can manage.
  useAuthStore.setState({ user: { id: 'user-1', email: 'u@example.com', name: 'User One' } });
  // Default: the version read answers an empty history, which hides the
  // selector and leaves every pre-existing case exactly as it was.
  vi.mocked(listVersions).mockResolvedValue([]);
  // The story-scoped marks read is the card flag's source; default to "no mark"
  // so every pre-existing case keeps its unmarked cards.
  vi.mocked(versioningApi.listStoryInvalidations).mockResolvedValue([]);
  // The mark-flow editor reads the task's marks on open; default to unmarked so
  // every pre-existing case is unaffected. The editor's D16 repetition read is
  // likewise defaulted to "no match".
  vi.mocked(versioningApi.listInvalidations).mockResolvedValue([]);
  vi.mocked(versioningApi.fetchRepetition).mockResolvedValue({ matches: [] });
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

/* ── Version-aware actions (0.9.0 slice b, W6-A) ── */

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
    isCurrent: false,
    hasOutput: true,
    ...overrides,
  };
}

const cardTask: Task = {
  id: 'task-1',
  storyId: STORY_ID,
  title: 'Set up database schema',
  description: 'Create the tables',
  labels: [],
  dependencies: [],
  status: 'backlog',
  priority: 'medium',
  createdAt: '2026-09-30T10:01:00Z',
  updatedAt: '2026-09-30T10:01:00Z',
};

describe('StoryDetail — version selector and version-aware actions', () => {
  let extractTasksSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    resetStores();
    extractTasksSpy = vi.fn().mockResolvedValue(undefined);
    useTaskStore.setState({ extractTasks: extractTasksSpy as never });
  });

  it('shows and selects the pending version of the run in progress, never the no-output card', async () => {
    setExtraction({
      extractionId: 'ext-2',
      status: 'pending',
      userStoryStatus: 'extracting',
      error: null,
      errorCode: null,
      versionNumber: 2,
    });
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: 'ext-2', versionNumber: 2, status: 'pending', hasOutput: false }),
      makeVersion({ id: 'ext-1', versionNumber: 1, isCurrent: true }),
    ]);
    useTaskStore.setState({ tasks: { [STORY_ID]: [] } });

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    // The combobox is there even though the run has not finished, and it holds the
    // version the run minted — not the still-current previous one.
    const selector = (await screen.findByRole('combobox', {
      name: t.versionSelector.label,
    })) as HTMLSelectElement;
    await waitFor(() => expect(selector.value).toBe('ext-2'));
    expect(screen.getByText(t.stories.extraction_tasks_in_progress)).toBeInTheDocument();
    // A pending version has no output yet, but it is not a failed one: the
    // no-output card belongs to a run that ended.
    expect(screen.queryByText(t.versionSelector.no_output_title)).not.toBeInTheDocument();
  });

  it('lists every version with exactly the current one marked', async () => {
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: 'ext-3', versionNumber: 3, status: 'failed', hasOutput: false, errorInfo: 'Ollama unreachable' }),
      makeVersion({ id: 'ext-2', versionNumber: 2, isCurrent: true }),
      makeVersion({ id: 'ext-1', versionNumber: 1 }),
    ]);

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    const selector = await screen.findByRole('combobox', { name: t.versionSelector.label });
    const options = [...selector.querySelectorAll('option')];
    expect(options).toHaveLength(3);
    const marked = options.filter((o) => o.textContent?.includes(t.versionSelector.current));
    expect(marked).toHaveLength(1);
    expect(marked[0]?.textContent).toContain('2');
  });

  it('renders a localized no-output state for a failed-only story, never the empty board', async () => {
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: 'ext-1', status: 'failed', hasOutput: false, errorInfo: 'Ollama unreachable' }),
    ]);

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    expect(await screen.findByText(t.versionSelector.no_output_title)).toBeInTheDocument();
    expect(
      screen.getByText(
        t.versionSelector.no_output_desc
          .replace('{model}', 'llama3.2')
          .replace('{error}', 'Ollama unreachable'),
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(t.stories.detail_tasks_empty)).not.toBeInTheDocument();
  });

  it('names the frozen and the new version in the extract confirmation, and cancel issues no request', async () => {
    const user = userEvent.setup();
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: 'ext-2', versionNumber: 2, isCurrent: true }),
      makeVersion({ id: 'ext-1', versionNumber: 1 }),
    ]);

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    await user.click(await screen.findByRole('button', { name: t.stories.detail_extract }));

    const dialog = await screen.findByRole('alertdialog');
    const expected = t.stories.extract_confirm_body
      .replace('{newVersion}', '3')
      .replace('{currentVersion}', '2');
    expect(within(dialog).getByText(expected)).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: t.common.cancel }));

    expect(extractTasksSpy).not.toHaveBeenCalled();
  });

  it('extracts once when the confirmation is accepted', async () => {
    const user = userEvent.setup();
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: 'ext-2', versionNumber: 2, isCurrent: true }),
      makeVersion({ id: 'ext-1', versionNumber: 1 }),
    ]);

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    await user.click(await screen.findByRole('button', { name: t.stories.detail_extract }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: t.stories.detail_extract }));

    expect(extractTasksSpy).toHaveBeenCalledTimes(1);
    expect(extractTasksSpy).toHaveBeenCalledWith(STORY_ID, 'ws-1');
  });

  it('short-circuits with a localized prompt and no request when no workspace is selected', async () => {
    const user = userEvent.setup();
    useWorkspaceStore.setState({ currentWorkspace: null });

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    await user.click(await screen.findByRole('button', { name: t.stories.detail_extract }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(t.stories.select_workspace_required),
    );
    expect(extractTasksSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('renders the localized authorization copy for a MEMBER 403, never a raw status text', async () => {
    setExtraction({
      ...idleExtraction(),
      status: 'failed',
      error: {
        friendlyMessage: 'Forbidden',
        rawDetail: { error_code: 'WORKSPACE_OWNER_OR_ADMIN_REQUIRED' },
        status: 403,
        errorCode: 'WORKSPACE_OWNER_OR_ADMIN_REQUIRED',
      },
      errorCode: 'server',
    });

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    expect(
      await screen.findByText(t.errorCodes.WORKSPACE_OWNER_OR_ADMIN_REQUIRED),
    ).toBeInTheDocument();
    expect(screen.queryByText('Forbidden')).not.toBeInTheDocument();
  });

  it('hides the gated controls for a member who is neither owner nor admin', async () => {
    useWorkspaceStore.setState({
      currentWorkspace: { ...makeWorkspace('ws-1', 'member'), ownerId: 'owner-9' },
    });

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    expect(await screen.findByRole('button', { name: t.stories.detail_extract })).toBeDisabled();
    expect(screen.queryByRole('button', { name: t.stories.mark_invalid })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.common.delete })).not.toBeInTheDocument();
  });

  it('opens the mark control beside the edit control on the task card, and both issue no request', async () => {
    const user = userEvent.setup();
    useTaskStore.setState({ tasks: { [STORY_ID]: [cardTask] } });

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    const mark = await screen.findByRole('button', { name: t.stories.mark_invalid });
    const edit = screen.getByRole('button', { name: t.taskEditor.title });
    // "Beside Editar": the two controls share one container on the card.
    expect(mark.parentElement).toBe(edit.parentElement);

    await user.click(mark);
    const editor = await screen.findByRole('dialog');
    expect(within(editor).getByText(cardTask.title)).toBeInTheDocument();
    expect(extractTasksSpy).not.toHaveBeenCalled();

    await user.click(within(editor).getByRole('button', { name: t.taskEditor.cancel }));
    expect(extractTasksSpy).not.toHaveBeenCalled();
  });

  it('opens the editor with the mark checkbox checked and the focus in the reason field, issuing no request until save (6.3 deferred clause)', async () => {
    const user = userEvent.setup();
    useTaskStore.setState({ tasks: { [STORY_ID]: [cardTask] } });

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    await user.click(await screen.findByRole('button', { name: t.stories.mark_invalid }));

    const editor = await screen.findByRole('dialog');
    const checkbox = within(editor).getByRole('checkbox', { name: t.taskEditor.mark_label });
    expect(checkbox).toBeChecked();

    const reason = within(editor).getByLabelText(t.taskEditor.mark_reason_label);
    // The dialog's own focus handling runs first; the editor's deferred focus
    // then lands in the reason field, ready to type.
    await waitFor(() => expect(document.activeElement).toBe(reason));

    // Nothing is applied until save: no mark write, no revoke, no PUT, no extract.
    expect(versioningApi.createInvalidation).not.toHaveBeenCalled();
    expect(versioningApi.revokeInvalidation).not.toHaveBeenCalled();
    expect(extractTasksSpy).not.toHaveBeenCalled();
  });

  it('shows the card flag as pressed for a marked task and unpressed for an unmarked one', async () => {
    const otherTask: Task = { ...cardTask, id: 'task-2', title: 'Second task' };
    useTaskStore.setState({ tasks: { [STORY_ID]: [cardTask, otherTask] } });
    vi.mocked(versioningApi.listStoryInvalidations).mockResolvedValue([
      {
        id: 'mark-1',
        taskId: cardTask.id,
        reason: 'Duplicates the v1 task',
        markedBy: 'user-1',
        markedAt: '2026-10-05T12:00:00Z',
        revokedBy: null,
        revokedAt: null,
      },
    ]);

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    const flags = await screen.findAllByRole('button', { name: t.stories.mark_invalid });
    await waitFor(() => expect(flags[0]).toHaveAttribute('aria-pressed', 'true'));
    expect(flags[1]).toHaveAttribute('aria-pressed', 'false');
  });

  it('flips the card flag after a confirmed mark, with no further story read', async () => {
    const user = userEvent.setup();
    useTaskStore.setState({ tasks: { [STORY_ID]: [cardTask] } });
    vi.mocked(versioningApi.createInvalidation).mockResolvedValue({
      id: 'mark-1',
      reason: 'Duplicates the v1 task',
      markedBy: 'user-1',
      markedAt: '2026-10-05T12:00:00Z',
      revokedBy: null,
      revokedAt: null,
    });
    vi.mocked(tasksApi.updateTask).mockResolvedValue(cardTask);

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    const flag = await screen.findByRole('button', { name: t.stories.mark_invalid });
    expect(flag).toHaveAttribute('aria-pressed', 'false');
    await user.click(flag);

    const editor = await screen.findByRole('dialog');
    await user.type(
      within(editor).getByLabelText(t.taskEditor.mark_reason_label),
      'Duplicates the v1 task',
    );
    await user.click(within(editor).getByRole('button', { name: t.taskEditor.save }));

    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: t.taskEditor.mark_confirm_accept }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: t.stories.mark_invalid })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    );
    // One mount read, nothing after the save: the flip came from the confirmed write.
    expect(vi.mocked(versioningApi.listStoryInvalidations)).toHaveBeenCalledTimes(1);
  });

  it('reads the selected frozen version\'s own tasks through its extraction_id', async () => {
    const user = userEvent.setup();
    const fetchTasksSpy = vi.fn().mockResolvedValue(undefined);
    useTaskStore.setState({ fetchTasks: fetchTasksSpy as never, tasks: {} });
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: 'ext-2', versionNumber: 2, isCurrent: true }),
      makeVersion({ id: 'ext-1', versionNumber: 1 }),
    ]);

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);

    // The initial read is the current version (no extraction_id)...
    await waitFor(() => {
      expect(fetchTasksSpy).toHaveBeenCalledWith(STORY_ID, undefined);
    });

    // ...and selecting the frozen v1 re-reads v1's own tasks.
    await user.selectOptions(
      await screen.findByRole('combobox', { name: t.versionSelector.label }),
      'ext-1',
    );
    await waitFor(() => {
      expect(fetchTasksSpy).toHaveBeenLastCalledWith(STORY_ID, 'ext-1');
    });
  });

  it('names the version count in the story-delete dialog and keeps the confirm enabled', async () => {
    const user = userEvent.setup();
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: 'ext-2', versionNumber: 2, isCurrent: true }),
      makeVersion({ id: 'ext-1', versionNumber: 1 }),
    ]);

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    await user.click(await screen.findByRole('button', { name: t.common.delete }));

    const dialog = await screen.findByRole('alertdialog');
    expect(
      within(dialog).getByText(t.stories.delete_confirm_versions.replace('{count}', '2')),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: t.common.delete })).toBeEnabled();
  });

  it('keeps the delete confirm enabled with the neutral fallback sentence when the version read fails', async () => {
    const user = userEvent.setup();
    vi.mocked(listVersions).mockRejectedValue(new Error('502 Bad Gateway'));

    render(<StoryDetail locale={LOCALE} storyId={STORY_ID} />);
    await user.click(await screen.findByRole('button', { name: t.common.delete }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(t.stories.delete_confirm_versions_unknown)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: t.common.delete })).toBeEnabled();
  });
});
