import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KanbanBoard } from '@/components/react/KanbanBoard';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useTranslations } from '@/i18n/utils';
import { shortProjectTitle, shortUUID } from '@/lib/utils';
import type { Task } from '@/types/task';
import type { Workspace } from '@/types/workspace';

const t = useTranslations('en');

// Mock the api module — the store consumes these mocks.
vi.mock('@/lib/tasks-api', () => ({
  updateTask: vi.fn(),
  listTasksByWorkspace: vi.fn(),
}));

// The board reads the story list and version history directly (WU4: it must not
// write into `useStoryStore`, which the stories page owns), so both reads are
// mocked at their modules.
vi.mock('@/lib/stories-api', () => ({
  listStories: vi.fn(),
}));
vi.mock('@/lib/versioning-api', () => ({
  listVersions: vi.fn(),
}));

// The board's project select feeds from `useProjectStore.fetchProjects`; give it a
// quiet resolution so tests that seed the store themselves never hit the network.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  // Prototype-preserving clone: `get` lives on the ApiClient prototype, so a plain
  // spread would drop every method but the one being replaced.
  const mockedApi = Object.create(Object.getPrototypeOf(actual.api)) as typeof actual.api;
  Object.assign(mockedApi, actual.api);
  mockedApi.get = vi.fn().mockResolvedValue({ items: [] });
  return { ...actual, api: mockedApi };
});

import { listTasksByWorkspace } from '@/lib/tasks-api';
import { listStories } from '@/lib/stories-api';
import { listVersions } from '@/lib/versioning-api';
import { api } from '@/lib/api';
import { useProjectStore } from '@/stores/projectStore';
import type { Project } from '@/types/project';
import type { PaginatedResponse } from '@/lib/projects-api';
import type { StoryVersion, UserStory } from '@/types/story';

// The real store action, captured before any test replaces it: the 6.7 cases drive the
// board's actual fetch path (store → `listTasksByWorkspace`) instead of stubbing it.
const realFetchTasksForWorkspace = useTaskStore.getState().fetchTasksForWorkspace;

// The story select's row for the `story-1` fixture every describe shares: the
// story's id, then the human label shortened by the one cap both surfaces use.
// Composed here once so a change to either rule fails in one place instead of
// four — and note the id is never truncated, only the label after it.
const STORY_OPTION_LABEL = 'story-1 · user: to log...';

const mockTasks: Task[] = [
  {
    id: 'task-1',
    storyId: 'story-1',
    title: 'DB schema',
    description: 'Create the database schema',
    status: 'todo',
    priority: 'high',
    labels: ['db', 'backend'],
    dependencies: ['task-0'],
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    extractionId: null,
    versionNumber: null,
  },
  {
    id: 'task-2',
    storyId: 'story-1',
    title: 'API endpoint',
    description: 'Build a REST API endpoint',
    status: 'in_progress',
    priority: 'medium',
    labels: ['api'],
    dependencies: [],
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    extractionId: null,
    versionNumber: null,
  },
];

describe('KanbanBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Seed the stores the board reads from.
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useTaskStore.setState({
      workspaceTasks: mockTasks,
      loading: false,
      error: null,
      updatingTaskId: null,
      // Stub the actions: the board fetches on mount and there is no backend here.
      fetchTasksForWorkspace: vi.fn().mockResolvedValue(undefined),
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
      allowedTransitions: {},
    });
    useProjectStore.setState({ projects: [], loading: false, error: null });
  });

  it('renders column titles correctly', async () => {
    render(<KanbanBoard locale="en" />);

    // The board renders its columns once the mount fetch settles.
    await waitFor(() => {
      expect(screen.getByText('Backlog')).toBeInTheDocument();
      expect(screen.getByText('To Do')).toBeInTheDocument();
      expect(screen.getByText('In Progress')).toBeInTheDocument();
      expect(screen.getByText('Review')).toBeInTheDocument();
      expect(screen.getByText('Done')).toBeInTheDocument();
    });
  });

  it('shows a distinct empty state when the workspace has no tasks', async () => {
    useTaskStore.setState({ workspaceTasks: [] });
    render(<KanbanBoard locale="en" />);

    await waitFor(() => {
      expect(screen.getByText('No tasks in this workspace yet')).toBeInTheDocument();
      expect(
        screen.getByText('Extract tasks from a user story to see them here.'),
      ).toBeInTheDocument();
    });
  });

  it('locks a card (spinner + no drag handle) while its status update is in flight', async () => {
    useTaskStore.setState({ updatingTaskId: 'task-1' });
    render(<KanbanBoard locale="en" />);

    // The locked card shows a subtle loading indicator.
    await waitFor(() => {
      expect(screen.getByLabelText('Loading...')).toBeInTheDocument();
    });
    // Only the locked card is busy.
    expect(screen.getAllByLabelText('Loading...')).toHaveLength(1);
    // The locked card has no drag handle, so it cannot be re-dragged.
    const handles = document.querySelectorAll('[data-rfd-drag-handle-draggable-id]');
    expect(handles).toHaveLength(mockTasks.length - 1);
  });

  it('does not raise the board veil while a drag-and-drop status update is in flight (D4)', async () => {
    // The drag path is optimistic: the card locks with its own spinner
    // (`updatingTaskId`) and failure is reported by toast. It never raises the
    // board's read state (the store's `loading` is the tasks read alone), so the
    // full-screen veil must stay down — asserted here explicitly, not inferred.
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    useTaskStore.setState({
      updatingTaskId: 'task-1',
      updateTaskStatus: vi.fn().mockReturnValue(pending),
    });

    render(<KanbanBoard locale="en" />);

    // The board itself is settled and the card-level spinner is up...
    expect(await screen.findByText('DB schema')).toBeInTheDocument();
    expect(screen.getByLabelText('Loading...')).toBeInTheDocument();
    // ...and the veil never is, nor the internal board loader (D6: a card move
    // raises none of the board's loading levels — level 4, pinned).
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();

    release();
  });

  it('shows an announced error and a retry when the board cannot load', async () => {
    const user = userEvent.setup();
    // Mimic the real store action, which never rejects: it records the failure in `error`.
    // Driving this path through a rejected promise is what the old board did, and it is why
    // the branch was unreachable — nothing could ever reject.
    const fetchTasksForWorkspace = vi.fn().mockImplementation(async () => {
      useTaskStore.setState({
        error: {
          friendlyMessage: 'the board is unavailable',
          rawDetail: { detail: 'the board is unavailable' },
          status: 503,
          errorCode: 'BOARD_UNAVAILABLE',
        },
        loading: false,
      });
    });
    useTaskStore.setState({ fetchTasksForWorkspace, error: null });

    render(<KanbanBoard locale="en" />);

    // This state replaces the whole page, so before the component rendered something a
    // failed load left the board empty with no explanation at all.
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('the board is unavailable');
    // The status and the machine code reach the user now: the store keeps what the API layer
    // captured, where it used to record only a message and the page had nothing to disclose.
    expect(alert).toHaveTextContent('HTTP 503');
    expect(alert).toHaveTextContent('BOARD_UNAVAILABLE');
    expect(screen.queryByText('Backlog')).not.toBeInTheDocument();

    // And the board can be brought back without leaving the page.
    fetchTasksForWorkspace.mockImplementation(async () => {
      useTaskStore.setState({ error: null, loading: false });
    });
    await user.click(screen.getByRole('button', { name: t.common.retry }));

    await waitFor(() => expect(fetchTasksForWorkspace).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText('Backlog')).toBeInTheDocument());
  });

  it('does not claim the board is empty while a retry is in flight', async () => {
    const user = userEvent.setup();
    let release: (() => void) | undefined;
    // Mimic the store exactly: it records the failure, and it raises `loading` before it
    // awaits. Without the second half the board would have nothing to show a spinner for.
    const fetchTasksForWorkspace = vi
      .fn()
      .mockImplementationOnce(async () => {
        useTaskStore.setState({
          error: {
            friendlyMessage: 'the board is unavailable',
            rawDetail: 'the board is unavailable',
          },
          loading: false,
        });
      })
      .mockImplementationOnce(() => {
        // The real action clears the recorded error before it awaits; without that the retry
        // would land back on the error branch and this assertion would pass for free.
        useTaskStore.setState({ loading: true, error: null });
        return new Promise<void>((resolve) => {
          release = () => resolve();
        });
      });
    useTaskStore.setState({ fetchTasksForWorkspace, error: null, workspaceTasks: [] });

    render(<KanbanBoard locale="en" />);
    await user.click(await screen.findByRole('button', { name: t.common.retry }));

    // The retry starts with `initialLoad` already false, so without putting it back the guard
    // that shows the spinner misses and the page says there are no tasks.
    expect(screen.queryByText(t.kanban.empty_board)).not.toBeInTheDocument();

    release?.();
  });
});

/* ── Current-version-only workspace reads (0.9.0 slice b, 6.7) ──
 *
 * The board renders whatever the workspace read returns; the current-version filter
 * itself is the backend's (`list_current_by_workspace`, WU3 3.7). These cases pin the
 * frontend half of that contract: the board fetches through `listTasksByWorkspace` —
 * the endpoint that carries the filter — and renders exactly the tasks that read
 * returns, so a superseded version cannot appear as cards and a failed-only story
 * cannot appear as anything at all. A frozen version's cards are unreachable here by
 * the same construction: only current versions ever reach the board, so the frozen
 * clause is pinned where a frozen task can actually be acted on — the editor's
 * status-only save of a frozen task ("never blocks or warns on a status-only save of a
 * frozen task" in TaskEditor.test.tsx).
 */
describe('KanbanBoard — current-version-only workspace reads', () => {
  function makeTask(id: string, title: string, status: Task['status']): Task {
    return {
      id,
      storyId: 'story-1',
      title,
      description: `Description for ${title}`,
      status,
      priority: 'medium',
      labels: [],
      dependencies: [],
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      extractionId: null,
      versionNumber: null,
    };
  }

  // One story with two completed runs: v1's four tasks are superseded and must never
  // render; v2's four tasks are the current version and are all the API can answer.
  const v1Titles = ['v1 schema', 'v1 endpoint', 'v1 UI', 'v1 tests'];
  const v2Tasks: Task[] = [
    makeTask('task-v2-1', 'v2 schema', 'backlog'),
    makeTask('task-v2-2', 'v2 endpoint', 'backlog'),
    makeTask('task-v2-3', 'v2 UI', 'in_progress'),
    makeTask('task-v2-4', 'v2 tests', 'done'),
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: realFetchTasksForWorkspace,
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('renders exactly the current version\'s cards for a story with two completed runs, and none of v1\'s', async () => {
    vi.mocked(listTasksByWorkspace).mockResolvedValue(v2Tasks);

    render(<KanbanBoard locale="en" />);

    // The read went through the workspace endpoint that carries the current-version filter.
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1'));

    // All four of v2's tasks render as cards...
    for (const task of v2Tasks) {
      expect(await screen.findByText(task.title)).toBeInTheDocument();
    }
    expect(screen.getByText(t.kanban.total_tasks.replace('{count}', '4'))).toBeInTheDocument();
    // ...and none of v1's tasks do, even though the story has two completed runs.
    for (const title of v1Titles) {
      expect(screen.queryByText(title)).not.toBeInTheDocument();
    }
  });

  it('renders no cards and no error for a story whose only run failed', async () => {
    // A failed-only story has no current version, so the workspace read answers [] —
    // a completed answer, not a failure.
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);

    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1'));

    // The board shows its distinct empty state...
    expect(await screen.findByText(t.kanban.empty_board)).toBeInTheDocument();
    // ...and nothing failed: no alert is rendered and the store records no error.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(useTaskStore.getState().error).toBeNull();
  });
});

/* ── Kanban cascade filters (WU4, D5) ──
 *
 * The filter bar cascades Project → Story → Version and the query that leaves
 * the client must carry exactly one scope — the backend refuses two with 422
 * `REQUEST_VALIDATION_FAILED`, so the client must not be able to send them.
 * Every case below asserts the arguments that reach the mocked
 * `listTasksByWorkspace` (board → store → API), not what the select renders:
 * the exclusive-scope rule is the unit's point.
 */
describe('KanbanBoard — cascade filters', () => {
  const mockProjects: Project[] = [
    {
      id: 'project-1',
      name: 'Alpha',
      description: '',
      workspaceId: 'workspace-1',
      createdBy: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      storyCount: 1,
    },
    {
      id: 'project-2',
      name: 'Beta',
      description: '',
      workspaceId: 'workspace-1',
      createdBy: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      storyCount: 0,
    },
  ];

  const mockStories: UserStory[] = [
    {
      id: 'story-1',
      projectId: 'project-1',
      actor: 'user',
      feature: 'to log in',
      benefit: 'to access my account',
      rawText: 'As a user, I want to log in, so that I can access my account',
      status: 'extracted',
      createdAt: '2026-01-01T00:00:00Z',
    },
  ];

  // Ordered `version_number DESC` by the read: v2 is the current one.
  const mockVersions: StoryVersion[] = [
    {
      id: 'extraction-2',
      versionNumber: 2,
      status: 'completed',
      modelUsed: 'llama3.2',
      provider: 'ollama',
      temperature: 0.1,
      createdAt: '2026-01-02T00:00:00Z',
      completedAt: '2026-01-02T00:01:00Z',
      errorInfo: null,
      isCurrent: true,
      hasOutput: true,
    },
    {
      id: 'extraction-1',
      versionNumber: 1,
      status: 'completed',
      modelUsed: 'llama3.2',
      provider: 'ollama',
      temperature: 0.1,
      createdAt: '2026-01-01T00:00:00Z',
      completedAt: '2026-01-01T00:01:00Z',
      errorInfo: null,
      isCurrent: false,
      hasOutput: true,
    },
  ];

  const storyPage: PaginatedResponse<UserStory> = {
    items: mockStories,
    total: mockStories.length,
    page: 1,
    size: 100,
  };

  /** Open the select whose accessible name is `label` and pick `optionLabel`. */
  async function chooseOption(
    user: ReturnType<typeof userEvent.setup>,
    label: string,
    optionLabel: string,
  ) {
    // `findBy` waits out the mount fetch: the spinner state renders no bar.
    await user.click(await screen.findByRole('combobox', { name: label }));
    await user.click(await screen.findByRole('option', { name: optionLabel }));
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useProjectStore.setState({
      projects: mockProjects,
      loading: false,
      error: null,
      // The projects are already seeded; the board must not need to fetch them.
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: realFetchTasksForWorkspace,
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(listStories).mockResolvedValue(storyPage);
    vi.mocked(listVersions).mockResolvedValue(mockVersions);
  });

  it('fetches with project_id and no other scope when a project is chosen', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1'));

    await chooseOption(user, t.kanban.filter_project, 'Alpha');

    // The filters object is the whole scope: only `projectId`, so the request can
    // only ever carry `project_id`.
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        projectId: 'project-1',
      }),
    );
  });

  it('fetches with user_story_id and no other scope when a story is chosen', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await chooseOption(user, t.kanban.filter_project, 'Alpha');
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        projectId: 'project-1',
      }),
    );

    await chooseOption(user, t.kanban.filter_story, STORY_OPTION_LABEL);

    // Most specific wins: the project scope is dropped, not sent alongside —
    // two scopes are the backend's 422.
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        storyId: 'story-1',
      }),
    );
  });

  it('fetches with user_story_id + extraction_id when a version is chosen', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await chooseOption(user, t.kanban.filter_project, 'Alpha');
    await chooseOption(user, t.kanban.filter_story, STORY_OPTION_LABEL);
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        storyId: 'story-1',
      }),
    );

    // The version select labels the current version with the marker (D10)...
    await chooseOption(user, t.kanban.filter_version, 'v2 · current');

    // ...and the read is exactly that version's, frozen ones included.
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        storyId: 'story-1',
        versionId: 'extraction-2',
      }),
    );
  });

  it('returns to the plain workspace_id fetch when the filters are cleared', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await chooseOption(user, t.kanban.filter_project, 'Alpha');
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        projectId: 'project-1',
      }),
    );

    // The affordance exists only while a filter is active...
    expect(screen.getByRole('button', { name: t.kanban.filter_clear })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: t.kanban.filter_clear }));

    // ...and clearing returns to the unfiltered read: the workspace alone, the
    // pre-filtering call shape.
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1'));
    expect(screen.queryByRole('button', { name: t.kanban.filter_clear })).not.toBeInTheDocument();
  });

  it('shows the filtered empty state, not the workspace-empty copy, when a filter matches nothing', async () => {
    const user = userEvent.setup();
    // Every read answers zero tasks: the workspace really is empty in this fixture,
    // but the filter is active, so the board must not claim the workspace is empty.
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await chooseOption(user, t.kanban.filter_project, 'Alpha');
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        projectId: 'project-1',
      }),
    );

    expect(await screen.findByText(t.kanban.empty_filtered)).toBeInTheDocument();
    expect(screen.getByText(t.kanban.empty_filtered_hint)).toBeInTheDocument();
    // The workspace-empty copy would be a lie here: the filter emptied the board.
    expect(screen.queryByText(t.kanban.empty_board)).not.toBeInTheDocument();
  });

  it('keeps the story select disabled until a project is chosen', async () => {
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);

    expect(await screen.findByRole('combobox', { name: t.kanban.filter_story })).toBeDisabled();

    // And it unlocks once the parent is chosen.
    const user = userEvent.setup();
    await chooseOption(user, t.kanban.filter_project, 'Alpha');
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: t.kanban.filter_story })).toBeEnabled(),
    );
  });

  it('retries a failed filtered load with the same project_id query, not the bare workspace read', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace)
      // Mount: unfiltered, succeeds.
      .mockResolvedValueOnce([])
      // The filtered load fails...
      .mockRejectedValueOnce(new Error('the board is unavailable'))
      // ...and the retry succeeds.
      .mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await chooseOption(user, t.kanban.filter_project, 'Alpha');

    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: t.common.retry }));

    // Call 3 is the retry: it carries the filter the bar still shows, so the
    // board cannot silently swap back to the whole workspace.
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenNthCalledWith(3, 'workspace-1', {
        projectId: 'project-1',
      }),
    );
  });

  it('resets the filters when the workspace changes and refetches the new workspace unfiltered', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await chooseOption(user, t.kanban.filter_project, 'Alpha');
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        projectId: 'project-1',
      }),
    );

    // Switch workspaces the way the switcher does: the current workspace moves.
    useWorkspaceStore.setState({
      currentWorkspace: {
        id: 'workspace-2',
        name: 'Other Workspace',
        slug: 'other-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
    });

    // The new workspace's first (and only) read is unfiltered — the workspace
    // alone, no filters object: workspace A's project is meaningless in B, and a
    // filtered call here would either 403 or show an empty board with the bar
    // still naming the filter.
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-2'));
    const workspace2Calls = vi
      .mocked(listTasksByWorkspace)
      .mock.calls.filter(([wsId]) => wsId === 'workspace-2');
    // Exactly one read for the new workspace, and it names no scope: the filters
    // argument slot is empty, so nothing can 403 or hollow out the board.
    expect(workspace2Calls.length).toBe(1);
    expect(workspace2Calls[0][1]).toBeUndefined();
  });
});

/* ── Board loading levels (D8–D10) ──
 *
 * Three levels, one per surface, and one rule above them all. D10 — the board
 * *never* raises the full-viewport veil: every task read it makes (first
 * entry, workspace switch, filter change, retry) renders the internal loader
 * in place of the columns (D8), and the full veil belongs to mutations alone.
 * Each select carries its own loader while its own read is pending (D9).
 * A card move raises none of the above (pinned in the first describe above).
 * The empty states stay quiet while a read is pending, so a slow load cannot
 * paint "no tasks yet" behind a loader or into the accessibility tree.
 */
describe('KanbanBoard — board loading levels', () => {
  /** A promise the test holds shut until it wants the read to settle. */
  function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((r) => {
      resolve = r;
    });
    return { promise, resolve };
  }

  /** Open the select whose accessible name is `label` and pick `optionLabel`. */
  async function chooseOption(
    user: ReturnType<typeof userEvent.setup>,
    label: string,
    optionLabel: string,
  ) {
    await user.click(await screen.findByRole('combobox', { name: label }));
    await user.click(await screen.findByRole('option', { name: optionLabel }));
  }

  const mockProjects: Project[] = [
    {
      id: 'project-1',
      name: 'Alpha',
      description: '',
      workspaceId: 'workspace-1',
      createdBy: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      storyCount: 1,
    },
  ];

  const mockStories: UserStory[] = [
    {
      id: 'story-1',
      projectId: 'project-1',
      actor: 'user',
      feature: 'to log in',
      benefit: 'to access my account',
      rawText: 'As a user, I want to log in, so that I can access my account',
      status: 'extracted',
      createdAt: '2026-01-01T00:00:00Z',
    },
  ];

  const storyPage: PaginatedResponse<UserStory> = {
    items: mockStories,
    total: mockStories.length,
    page: 1,
    size: 100,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useProjectStore.setState({
      projects: mockProjects,
      loading: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: realFetchTasksForWorkspace,
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(listStories).mockResolvedValue(storyPage);
    vi.mocked(listVersions).mockResolvedValue([]);
  });

  it('shows the internal loader, never the veil, on first entry (D10)', async () => {
    const gate = deferred<Task[]>();
    vi.mocked(listTasksByWorkspace).mockReturnValue(gate.promise);

    render(<KanbanBoard locale="en" />);

    // D10: opening the board is a board read like any other — the internal
    // loader replaces the columns and the full-viewport veil never rises.
    expect(await screen.findByRole('progressbar')).toHaveTextContent(t.common.loading);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    act(() => gate.resolve([]));
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
    // The settled empty board is the honest end state of this read.
    expect(await screen.findByText(t.kanban.empty_board)).toBeInTheDocument();

    // A filter-driven refetch is the same read shape: internal loader, no veil.
    const user = userEvent.setup();
    const refetch = deferred<Task[]>();
    vi.mocked(listTasksByWorkspace).mockReturnValue(refetch.promise);
    await chooseOption(user, t.kanban.filter_project, 'Alpha');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toBeInTheDocument();

    act(() => refetch.resolve([]));
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
  });

  it('never renders a full-viewport veil on entry (D10)', async () => {
    const gate = deferred<Task[]>();
    vi.mocked(listTasksByWorkspace).mockReturnValue(gate.promise);

    render(<KanbanBoard locale="en" />);

    // While the first read is in flight the only loading indicator anywhere in
    // the board is the internal loader: no `role="status"` veil at any point.
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toBeInTheDocument();

    act(() => gate.resolve([]));
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
  });

  it('shows the internal loader, not the veil, on a filter change while the task refetch is pending', async () => {
    const user = userEvent.setup();
    // Mount read settles at once; the refetch the project pick starts does not.
    const gate = deferred<Task[]>();
    vi.mocked(listTasksByWorkspace)
      .mockResolvedValueOnce([])
      .mockReturnValueOnce(gate.promise);

    render(<KanbanBoard locale="en" />);
    // The mount read settles before the pick.
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());

    await chooseOption(user, t.kanban.filter_project, 'Alpha');

    // D8: the internal loader replaces the columns while the task read is in
    // flight...
    expect(await screen.findByRole('progressbar')).toHaveTextContent(t.common.loading);
    // ...the veil never rises for any board read (D10)...
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    // ...and the filter bar stays rendered and usable: changing filters while a
    // read is in flight is a supported interaction.
    expect(screen.getByRole('combobox', { name: t.kanban.filter_project })).toBeEnabled();
    expect(screen.getByRole('combobox', { name: t.kanban.filter_story })).toBeEnabled();

    act(() => gate.resolve([]));
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        projectId: 'project-1',
      }),
    );
  });

  it('shows the story select’s own loader while the stories read is pending — and no veil', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);
    const gate = deferred<PaginatedResponse<UserStory>>();
    vi.mocked(listStories).mockReturnValue(gate.promise);

    render(<KanbanBoard locale="en" />);
    // The task read settled; the loader is down before the pick.
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());

    await chooseOption(user, t.kanban.filter_project, 'Alpha');

    // D9: the pending read is attributable to the control that caused it — a
    // spinner inside the story select's own trigger, not the veil.
    const storyTrigger = await screen.findByRole('combobox', { name: t.kanban.filter_story });
    expect(within(storyTrigger).getByLabelText(t.common.loading)).toBeInTheDocument();
    // The state also belongs to the control: an `aria-label` on the bare svg is
    // ignored by several screen readers, so `aria-busy` is what assistive tech
    // reads as "this select is still loading".
    expect(storyTrigger).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    // The other selects are quiet: each reflects only its own read.
    const projectTrigger = screen.getByRole('combobox', { name: t.kanban.filter_project });
    expect(
      within(projectTrigger).queryByLabelText(t.common.loading),
    ).not.toBeInTheDocument();
    expect(projectTrigger).toHaveAttribute('aria-busy', 'false');

    act(() => gate.resolve(storyPage));
    await waitFor(() =>
      expect(within(storyTrigger).queryByLabelText(t.common.loading)).not.toBeInTheDocument(),
    );
    expect(storyTrigger).toHaveAttribute('aria-busy', 'false');
  });

  it('shows the version select’s own loader while the versions read is pending — and no veil', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());

    await chooseOption(user, t.kanban.filter_project, 'Alpha');
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());

    const gate = deferred<StoryVersion[]>();
    vi.mocked(listVersions).mockReturnValue(gate.promise);
    await chooseOption(user, t.kanban.filter_story, STORY_OPTION_LABEL);

    const versionTrigger = await screen.findByRole('combobox', { name: t.kanban.filter_version });
    expect(within(versionTrigger).getByLabelText(t.common.loading)).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    const storyTrigger = screen.getByRole('combobox', { name: t.kanban.filter_story });
    expect(within(storyTrigger).queryByLabelText(t.common.loading)).not.toBeInTheDocument();

    act(() => gate.resolve([]));
    await waitFor(() =>
      expect(within(versionTrigger).queryByLabelText(t.common.loading)).not.toBeInTheDocument(),
    );
  });

  it('shows the project select’s own loader while the projects read is pending (D9)', async () => {
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);
    useProjectStore.setState({ loading: true });

    render(<KanbanBoard locale="en" />);
    // The first task read settles; the projects read stays pending.
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());

    const projectTrigger = await screen.findByRole('combobox', { name: t.kanban.filter_project });
    expect(within(projectTrigger).getByLabelText(t.common.loading)).toBeInTheDocument();
    // Its own read only: the other two selects are quiet, and the projects read
    // raises no veil either.
    expect(
      within(screen.getByRole('combobox', { name: t.kanban.filter_story })).queryByLabelText(
        t.common.loading,
      ),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByRole('combobox', { name: t.kanban.filter_version })).queryByLabelText(
        t.common.loading,
      ),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    act(() => useProjectStore.setState({ loading: false }));
    await waitFor(() =>
      expect(within(projectTrigger).queryByLabelText(t.common.loading)).not.toBeInTheDocument(),
    );
  });

  it('shows the internal loader, never the veil, when the workspace changes (D10)', async () => {
    const gate = deferred<Task[]>();
    vi.mocked(listTasksByWorkspace)
      // workspace-1's first read settles at once...
      .mockResolvedValueOnce([])
      // ...so workspace-2's first read is a switch, not a first paint.
      .mockReturnValueOnce(gate.promise);

    render(<KanbanBoard locale="en" />);
    // workspace-1's board settled: the loader came down and the empty board
    // rendered.
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
    expect(await screen.findByText(t.kanban.empty_board)).toBeInTheDocument();

    // Switch workspaces the way the switcher does: the current workspace moves.
    useWorkspaceStore.setState({
      currentWorkspace: {
        id: 'workspace-2',
        name: 'Other Workspace',
        slug: 'other-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
    });

    // D10 dissolved D7: a switch is a board read like any other — the whole
    // board context changed, and the internal loader replaces the columns
    // exactly as it does for a filter change. The full veil never rises.
    expect(await screen.findByRole('progressbar')).toHaveTextContent(t.common.loading);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    act(() => gate.resolve([]));
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-2'));
  });

  it('shows the internal loader, never the veil, on the retry from the error card (D10)', async () => {
    const user = userEvent.setup();
    let release!: () => void;
    const retryPending = new Promise<void>((resolve) => {
      release = resolve;
    });
    // Mimic the real store action: it never rejects — it records the failure in
    // `error` — and the retry raises `loading` before it awaits.
    const fetchTasksForWorkspace = vi
      .fn()
      .mockImplementationOnce(async () => {
        useTaskStore.setState({
          error: {
            friendlyMessage: 'the board is unavailable',
            rawDetail: 'the board is unavailable',
          },
          loading: false,
        });
      })
      .mockImplementationOnce(() => {
        useTaskStore.setState({ loading: true, error: null });
        return retryPending;
      });
    useTaskStore.setState({ fetchTasksForWorkspace, error: null, workspaceTasks: [] });

    render(<KanbanBoard locale="en" />);
    await screen.findByRole('alert');

    await user.click(screen.getByRole('button', { name: t.common.retry }));

    // D10 killed the failed-first-read exception: a retry is just another
    // board read — the internal loader, not the full veil.
    expect(await screen.findByRole('progressbar')).toHaveTextContent(t.common.loading);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    release();
  });

  it('does not show the veil when no workspace is selected — the prompt renders instead (D4)', async () => {
    useWorkspaceStore.setState({ currentWorkspace: null });
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);

    expect(await screen.findByText(t.kanban.no_workspace)).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('does not paint the empty-board copy while a read is in flight', async () => {
    const gate = deferred<Task[]>();
    vi.mocked(listTasksByWorkspace).mockReturnValue(gate.promise);

    render(<KanbanBoard locale="en" />);

    await screen.findByRole('progressbar');
    // A slow first load must not claim the workspace is empty behind the loader.
    expect(screen.queryByText(t.kanban.empty_board)).not.toBeInTheDocument();
    expect(screen.queryByText(t.kanban.empty_board_hint)).not.toBeInTheDocument();

    act(() => gate.resolve([]));
    expect(await screen.findByText(t.kanban.empty_board)).toBeInTheDocument();
  });
});

/* ── listTasksByWorkspace — D5 query precedence (the API layer's own contract) ──
 *
 * The board resolves the cascade before calling, so the board-level cases above
 * already send exclusive scopes; this block pins the API layer's resolution for
 * any caller that passes a wider cascade (D5: most specific wins, never two
 * scopes, because the backend 422s `REQUEST_VALIDATION_FAILED` on two).
 */
describe('listTasksByWorkspace — query precedence', () => {
  it('builds exactly one scope per filter combination', async () => {
    const { listTasksByWorkspace: realList } = await vi.importActual<
      typeof import('@/lib/tasks-api')
    >('@/lib/tasks-api');

    // Nothing → workspace_id (the board as it was before the filters existed).
    await realList('ws-1');
    expect(vi.mocked(api.get)).toHaveBeenLastCalledWith(
      '/api/v1/tasks/?workspace_id=ws-1&page=1&size=100',
    );

    // Project alone → project_id.
    await realList('ws-1', { projectId: 'p-1' });
    expect(vi.mocked(api.get)).toHaveBeenLastCalledWith(
      '/api/v1/tasks/?project_id=p-1&page=1&size=100',
    );

    // Story (even beside a project) → user_story_id only.
    await realList('ws-1', { projectId: 'p-1', storyId: 's-1' });
    expect(vi.mocked(api.get)).toHaveBeenLastCalledWith(
      '/api/v1/tasks/?user_story_id=s-1&page=1&size=100',
    );

    // Version beside its story → user_story_id + extraction_id (frozen reads).
    await realList('ws-1', { storyId: 's-1', versionId: 'v-1' });
    expect(vi.mocked(api.get)).toHaveBeenLastCalledWith(
      '/api/v1/tasks/?user_story_id=s-1&extraction_id=v-1&page=1&size=100',
    );

    // A versionId without its story is ignored (unreachable from the board's
    // cascade) and falls through to the next applicable scope.
    await realList('ws-1', { versionId: 'v-1' });
    expect(vi.mocked(api.get)).toHaveBeenLastCalledWith(
      '/api/v1/tasks/?workspace_id=ws-1&page=1&size=100',
    );
  });
});

/* ── KanbanCard version chip (WU5) ──
 *
 * The board renders through the real cards, which is where the chip lives. The
 * chip is a bare `v{n}` and **never** a currency marker (D1's honesty rule, D8):
 * a card cannot tell a current-version board read from a frozen-version read —
 * only the story's summary knows which run is current — so marking a card
 * `v2 · current` would be exactly the lie D1 forbids. A null `version_number`
 * (reachable: the backend's `_version_number` answers None when the task's
 * entity carries no `extraction_id` or the batched lookup misses) renders no
 * chip at all — not `vnull`, not `v?`, not an empty badge.
 */
describe('KanbanCard — version chip', () => {
  function chipTask(fields: Partial<Task> & Pick<Task, 'id' | 'versionNumber'>): Task {
    return {
      storyId: 'story-1',
      title: `Task ${fields.id}`,
      description: '',
      status: 'todo',
      priority: 'medium',
      labels: [],
      dependencies: [],
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      extractionId: 'extraction-1',
      ...fields,
    };
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: vi.fn().mockResolvedValue(undefined),
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('shows the task version as a bare v{n} badge next to its labels', async () => {
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-v', versionNumber: 2, labels: ['db', 'backend'] })],
    });

    render(<KanbanBoard locale="en" />);

    expect(await screen.findByText('v2')).toBeInTheDocument();
    // The labels still render beside it.
    expect(screen.getByText('db')).toBeInTheDocument();
    expect(screen.getByText('backend')).toBeInTheDocument();
  });

  it('renders no chip at all when version_number is null', async () => {
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-null', versionNumber: null, labels: ['db'] })],
    });

    render(<KanbanBoard locale="en" />);

    expect(await screen.findByText('Task task-null')).toBeInTheDocument();
    // None of the degraded shapes: no `vnull`, no `v?`, no empty badge.
    expect(screen.queryByText('vnull')).not.toBeInTheDocument();
    expect(screen.queryByText('v?')).not.toBeInTheDocument();
    expect(screen.queryByText(/^v\d*$/)).not.toBeInTheDocument();
  });

  it('shows the bare v{n} on a version-filtered board and never the current marker', async () => {
    // A version-filtered read returns a frozen version's tasks (D8/D5); the card
    // cannot know whether that run is current, so it must not claim it.
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-frozen', versionNumber: 1 })],
    });

    render(<KanbanBoard locale="en" />);

    expect(await screen.findByText('v1')).toBeInTheDocument();
    // The current marker's rendered text, as StoryVersionBadge and the cascade's
    // version select produce it: `v1 · current`. Its absence is the pin.
    expect(screen.queryByText('v1 · current')).not.toBeInTheDocument();
  });
});

/* ── KanbanCard project and story chips (WU14) ──
 *
 * The board renders through the real cards, which is where the chips live. A
 * card names where it came from: the project by name (D13 — as text, never a
 * link: the card's one click target stays the title) and the story by its
 * short id, exactly as the story cards show it (D12 — `shortUUID`, reused, so
 * the two surfaces cannot drift). Both chips are context (D15): the same
 * `outline` variant and sizing classes as the label and version chips, muted
 * like the version chip, ordered project → story → version → labels (the owner
 * moved the labels last on 2026-10-08, so the three context chips lead the row
 * and the task's own attributes trail it). Each
 * chip renders only when its data is present — no `undefined` badge, no empty
 * chip — and a long project name must ellipsize inside a bounded chip instead
 * of pushing the labels or the version chip out of the card.
 */
describe('KanbanCard — project and story chips', () => {
  const STORY_ID = '01a10dee-6d92-7d13-812f-bc39dfd8e767';

  function chipTask(fields: Partial<Task> & Pick<Task, 'id'>): Task {
    return {
      storyId: STORY_ID,
      title: `Task ${fields.id}`,
      description: '',
      status: 'todo',
      priority: 'medium',
      labels: [],
      dependencies: [],
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      extractionId: 'extraction-1',
      versionNumber: null,
      projectId: null,
      projectName: null,
      ...fields,
    };
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: vi.fn().mockResolvedValue(undefined),
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('renders the project and story chips with their values, ordered project → story → version → labels', async () => {
    useTaskStore.setState({
      workspaceTasks: [
        chipTask({
          id: 'task-full',
          projectId: 'project-1',
          projectName: 'Alpha',
          labels: ['db', 'backend'],
          versionNumber: 2,
        }),
      ],
    });

    render(<KanbanBoard locale="en" />);

    expect(await screen.findByText('Alpha')).toBeInTheDocument();
    // The metadata row, read left to right through the real card: the three
    // context chips first — project, story, version — then the task's own
    // labels, which the owner moved to the end.
    const row = screen.getByText('db').closest('div') as HTMLElement;
    expect(Array.from(row.children).map((el) => el.textContent)).toEqual([
      'Alpha',
      shortUUID(STORY_ID),
      'v2',
      'db',
      'backend',
    ]);

    // D13: the project chip is text, not a second link inside a draggable card.
    expect(screen.getByText('Alpha').closest('a')).toBeNull();
  });

  it('names the story exactly as the story cards do — shortUUID(task.storyId) (D12)', async () => {
    useTaskStore.setState({ workspaceTasks: [chipTask({ id: 'task-story' })] });

    render(<KanbanBoard locale="en" />);

    // The chip's text is the function's output itself, not an inline slice —
    // reusing the function is what keeps this surface from drifting (D12).
    expect(await screen.findByText(shortUUID(STORY_ID))).toBeInTheDocument();
  });

  it('renders the story chip and no project chip when the task has no project fields', async () => {
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-noproj', labels: ['db'] })],
    });

    render(<KanbanBoard locale="en" />);

    expect(await screen.findByText(shortUUID(STORY_ID))).toBeInTheDocument();
    // The row holds the story chip and the label, nothing else: no project
    // chip, and no degraded placeholder where one would go.
    const row = screen.getByText('db').closest('div') as HTMLElement;
    expect(Array.from(row.children).map((el) => el.textContent)).toEqual([
      shortUUID(STORY_ID),
      'db',
    ]);
  });

  it('renders neither chip and still shows its labels when the task names neither its project nor its story', async () => {
    // Beyond the type's own guarantee (`storyId` is required) this pins the
    // per-field render guards: falsy data produces no chip, not an empty one.
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-bare', storyId: '', labels: ['db'] })],
    });

    render(<KanbanBoard locale="en" />);

    // The metadata row survives on the labels alone.
    const row = await screen.findByText('db').then((el) => el.closest('div') as HTMLElement);
    expect(Array.from(row.children).map((el) => el.textContent)).toEqual(['db']);
  });

  it('bounds a long project name and keeps the full name in the tooltip (D17/D18)', async () => {
    const user = userEvent.setup();
    const longName = 'A Very Long Project Name That Would Push The Row '.repeat(4).trim();
    useTaskStore.setState({
      workspaceTasks: [
        chipTask({
          id: 'task-long',
          projectId: 'project-1',
          projectName: longName,
          labels: ['db'],
          versionNumber: 1,
        }),
      ],
    });

    render(<KanbanBoard locale="en" />);

    // WU17/D18: the chip carries no native `title` anymore — a real tooltip is
    // the only one a hover can raise, so two tooltips on one hover cannot
    // happen. The repo's TooltipTrigger wrapper owns the element's `data-slot`,
    // so the chip is identified by the tooltip trigger contract itself.
    const chip = (await screen.findByText(shortProjectTitle(longName))).closest(
      '[data-base-ui-tooltip-trigger]',
    ) as HTMLElement;
    expect(chip).not.toHaveAttribute('title');
    // The chip is width-bounded and its text ellipsizes inside that bound
    // instead of pushing the labels or the version chip out of the card.
    expect(chip).toHaveClass('max-w-[10rem]');
    expect(chip.querySelector('.truncate')).not.toBeNull();
    // The full truth lives in the tooltip, so a hover still names the project.
    await user.hover(chip);
    expect(await screen.findByText(longName)).toBeInTheDocument();
    // And the rest of the row is intact beside it.
    expect(screen.getByText('db')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
  });
});

/* ── Context treatment shared by the card chips and the cascade's selects (WU17) ──
 *
 * Three surfaces now name the same two things — project, story — and they must
 * agree by construction, not by accident (D16–D21 of feature
 * ``kanban-context-tooltips``). Each test below asserts a surface's rendered
 * output against the same rule function the production code consumes, for the
 * card **and** for the selects, so a future divergence between the surfaces
 * fails here. The tooltip's content lives in a portal; these tests assert the
 * opened popup through `screen` queries, which search the whole body — the
 * choice this file makes for portalled content.
 */
describe('KanbanBoard — context treatment on chips and selects (WU17)', () => {
  const STORY_ID = '01a10dee-6d92-7d13-812f-bc39dfd8e767';
  const SENTENCE = 'As a user, I want to log in, so that I can access my account';
  // Longer than the card's 12-character cap **and** the select's wider one, so
  // the truncated labels, the full tooltip and the native `title` are all
  // distinct, observable values.
  const LONG_PROJECT = 'Infrastructure Modernization Programme';

  /** The card-cap label the project chip must show. */
  const cardProjectLabel = shortProjectTitle(LONG_PROJECT);
  // One cap for both surfaces now — the owner asked for the badge's short text
  // inside the select too, which reverses D21's wider dropdown cap.
  const selectProjectLabel = shortProjectTitle(LONG_PROJECT);
  // This describe's story carries the full STORY_ID, so its row starts with
  // that story's short id, then the shortened label.
  const selectStoryLabel = `${shortUUID(STORY_ID)} · ${shortProjectTitle('user: to log in')}`;
  /** The wider select-cap label (D21) the project options must show. */

  const longProject: Project = {
    id: 'project-1',
    name: LONG_PROJECT,
    description: '',
    workspaceId: 'workspace-1',
    createdBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 1,
  };

  const story: UserStory = {
    id: STORY_ID,
    projectId: 'project-1',
    actor: 'user',
    feature: 'to log in',
    benefit: 'to access my account',
    rawText: SENTENCE,
    status: 'extracted',
    createdAt: '2026-01-01T00:00:00Z',
  };

  const storyPage: PaginatedResponse<UserStory> = {
    items: [story],
    total: 1,
    page: 1,
    size: 100,
  };

  function chipTask(fields: Partial<Task> & Pick<Task, 'id'>): Task {
    return {
      storyId: STORY_ID,
      title: `Task ${fields.id}`,
      description: '',
      status: 'todo',
      priority: 'medium',
      labels: [],
      dependencies: [],
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      extractionId: 'extraction-1',
      versionNumber: null,
      projectId: 'project-1',
      projectName: LONG_PROJECT,
      storyRawText: SENTENCE,
      ...fields,
    };
  }

  /** Open the select whose accessible name is `label` and pick `optionLabel`. */
  async function chooseOption(
    user: ReturnType<typeof userEvent.setup>,
    label: string,
    optionLabel: string,
  ) {
    await user.click(await screen.findByRole('combobox', { name: label }));
    await user.click(await screen.findByRole('option', { name: optionLabel }));
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useProjectStore.setState({
      projects: [longProject],
      loading: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: vi.fn().mockResolvedValue(undefined),
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(listStories).mockResolvedValue(storyPage);
    vi.mocked(listVersions).mockResolvedValue([]);
  });

  // ── The card's chips (D17/D18) ──

  it('shows the full project name in a real tooltip on the card chip, and no native title (D17/D18)', async () => {
    const user = userEvent.setup();
    useTaskStore.setState({ workspaceTasks: [chipTask({ id: 'task-p', labels: ['db'] })] });

    render(<KanbanBoard locale="en" />);

    // The chip's visible label is the card cap's truncation of the shared rule…
    expect(await screen.findByText(cardProjectLabel)).toBeInTheDocument();
    // …and the full name is nowhere on the page until the hover opens the tooltip.
    expect(screen.queryByText(LONG_PROJECT)).not.toBeInTheDocument();

    // D18: the chip carries no native `title` — the real tooltip is the only
    // one a hover can raise. (The repo's TooltipTrigger wrapper owns the
    // element's `data-slot`, so the chip is identified by the tooltip trigger
    // contract itself.)
    const chip = screen.getByText(cardProjectLabel).closest(
      '[data-base-ui-tooltip-trigger]',
    ) as HTMLElement;
    expect(chip).not.toHaveAttribute('title');
    // Same icon rule as everywhere a project is named on the board.
    expect(chip.querySelector('.lucide-folder-kanban')).not.toBeNull();

    await user.hover(chip);
    expect(await screen.findByText(LONG_PROJECT)).toBeInTheDocument();
  });

  it('opens the tooltip immediately, not after Base UI\'s 600 ms default', async () => {
    // The bug this pins: the tooltips were mounted without a TooltipProvider, so
    // Base UI's default 600 ms delay applied and a hover-and-move-on showed
    // nothing. Every assertion in this file still passed, because `findBy*`
    // waits a second — content was verified while responsiveness was not.
    //
    // The bound below is deliberately tighter than that default: with the delay
    // restored, the popup cannot be there in 150 ms and this fails.
    const user = userEvent.setup();
    useTaskStore.setState({ workspaceTasks: [chipTask({ id: 'task-fast', labels: ['db'] })] });

    render(<KanbanBoard locale="en" />);

    const chip = (await screen.findByText(cardProjectLabel)).closest(
      '[data-base-ui-tooltip-trigger]',
    ) as HTMLElement;
    await user.hover(chip);

    await waitFor(() => expect(screen.getByText(LONG_PROJECT)).toBeInTheDocument(), {
      timeout: 150,
    });
  });

  it('shows the story sentence in the story chip tooltip (D17)', async () => {
    const user = userEvent.setup();
    useTaskStore.setState({ workspaceTasks: [chipTask({ id: 'task-s' })] });

    render(<KanbanBoard locale="en" />);

    const chip = await screen.findByText(shortUUID(STORY_ID));
    expect(
      chip.closest('[data-base-ui-tooltip-trigger]')?.querySelector('.lucide-fingerprint'),
    ).not.toBeNull();

    await user.hover(chip);
    expect(await screen.findByText(SENTENCE)).toBeInTheDocument();
  });

  it('falls back to the id when the sentence is missing and never renders an empty tooltip (D17)', async () => {
    const user = userEvent.setup();
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-null-sentence', storyRawText: null })],
    });

    render(<KanbanBoard locale="en" />);

    const chip = await screen.findByText(shortUUID(STORY_ID));
    await user.hover(chip);
    // The tooltip shows what the card has — the story's id — not nothing.
    expect(await screen.findByText(STORY_ID)).toBeInTheDocument();
    // And no open popup anywhere is empty.
    const popups = document.querySelectorAll('[data-slot="tooltip-content"]');
    expect(popups.length).toBeGreaterThan(0);
    for (const popup of popups) {
      expect((popup.textContent ?? '').length).toBeGreaterThan(0);
    }
  });

  // ── The cascade's selects (D16/D18/D21) ──

  it("gives the project select options the folder icon, the badge's short text and the full name in our own tooltip", async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);
    // The fetch-path assertions need the real store action (as the cascade
    // describes do); the card describes stub it instead.
    useTaskStore.setState({ fetchTasksForWorkspace: realFetchTasksForWorkspace });

    render(<KanbanBoard locale="en" />);
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1'));

    await user.click(await screen.findByRole('combobox', { name: t.kanban.filter_project }));

    // The option carries the same short text the card chip does: seeing
    // ``Infrastructure...`` on the card and the full name in the dropdown for
    // the same project read as two different projects.
    const option = await screen.findByRole('option', { name: selectProjectLabel });
    expect(selectProjectLabel).toBe(cardProjectLabel);
    expect(option.querySelector('.lucide-folder-kanban')).not.toBeNull();
    // A native `title` is what this used to rely on, and it is why the owner
    // reported seeing no hover at all: the browser shows it late, in its own
    // style, and a row cut to a dozen characters cannot be read without it. The
    // row now raises our tooltip, the same one the chips use.
    expect(option).not.toHaveAttribute('title');
    // The option *is* the tooltip's trigger — a wrapper span inside it swallowed
    // the click and the row stopped selecting, so the hover lives on the row.
    expect(option).toHaveAttribute('data-base-ui-tooltip-trigger');
    await user.hover(option);
    expect(await screen.findByText(LONG_PROJECT)).toBeInTheDocument();
  });

  it('gives the story select options the fingerprint icon, its short id and the sentence in our own tooltip', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" />);
    await chooseOption(user, t.kanban.filter_project, selectProjectLabel);

    await user.click(await screen.findByRole('combobox', { name: t.kanban.filter_story }));

    // The owner's call of 2026-10-08: the short id *and* the shortened human
    // label, so a story reads the same way here and on the board's card. The id
    // itself is never truncated — cutting it would cost the two characters that
    // separate two stories of one actor.
    const option = await screen.findByRole('option', { name: selectStoryLabel });
    // The id the fixture carries (`story-1`, which `shortUUID` passes through
    // unchanged because it is not a uuid) plus the shortened label — the two
    // halves the owner asked for, in that order.
    expect(option.textContent).toContain(shortUUID(STORY_ID));
    expect(option.textContent).toContain('user: to log...');
    expect(option).not.toHaveAttribute('title');
    expect(option).toHaveAttribute('data-base-ui-tooltip-trigger');
    await user.hover(option);
    expect(await screen.findByText(SENTENCE)).toBeInTheDocument();
    expect(option.querySelector('.lucide-fingerprint')).not.toBeNull();
  });

  it('gives the select triggers a real tooltip with the full current value (D18)', async () => {
    const user = userEvent.setup();
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);
    useTaskStore.setState({ fetchTasksForWorkspace: realFetchTasksForWorkspace });

    render(<KanbanBoard locale="en" />);
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1'));

    // The project trigger's tooltip is the full name — but with nothing
    // selected there is no tooltip at all: no empty popup mounts.
    const projectTrigger = await screen.findByRole('combobox', { name: t.kanban.filter_project });
    await user.hover(projectTrigger);
    expect(screen.queryByText(LONG_PROJECT)).not.toBeInTheDocument();
    expect(document.querySelector('[data-slot="tooltip-content"]')).toBeNull();

    // Once a project is chosen, the trigger's tooltip carries its full name.
    await chooseOption(user, t.kanban.filter_project, selectProjectLabel);
    await user.hover(screen.getByRole('combobox', { name: t.kanban.filter_project }));
    expect(await screen.findByText(LONG_PROJECT)).toBeInTheDocument();

    // …and the story trigger's is the full sentence, once a story is chosen.
    await chooseOption(user, t.kanban.filter_project, selectProjectLabel);
    await chooseOption(user, t.kanban.filter_story, selectStoryLabel);
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenLastCalledWith('workspace-1', {
        storyId: STORY_ID,
      }),
    );
    await user.hover(screen.getByRole('combobox', { name: t.kanban.filter_story }));
    expect(await screen.findByText(SENTENCE)).toBeInTheDocument();
  });
});

/* ── The project's own icon on the chips and rows (WU20, D22–D24 of feature
 * ``kanban-project-icons``) ──
 *
 * Both the card's project chip and the cascade's project rows used to draw the
 * same hardcoded `FolderKanban` for every project. Now the icon is data — the
 * project's own name from the payload/row — rendered through `IconDisplay`
 * with `FolderKanban` as the fallback, the same one the rest of the app uses
 * for an icon-less project. The story keeps the fixed fingerprint either way:
 * `'fingerprint'` is not in `IconDisplay`'s map, so the story's icon is a
 * fallback, never a name. The board renders through the real cards and the
 * real selects, which is where both surfaces live.
 */
describe('KanbanBoard — the project’s own icon on chips and rows (WU20)', () => {
  const STORY_ID = '01a10dee-6d92-7d13-812f-bc39dfd8e767';
  const SENTENCE = 'As a user, I want to log in, so that I can access my account';
  const PROJECT_NAME = 'Alpha';

  function chipTask(fields: Partial<Task> & Pick<Task, 'id'>): Task {
    return {
      storyId: STORY_ID,
      title: `Task ${fields.id}`,
      description: '',
      status: 'todo',
      priority: 'medium',
      labels: [],
      dependencies: [],
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      extractionId: 'extraction-1',
      versionNumber: null,
      projectId: 'project-1',
      projectName: PROJECT_NAME,
      projectIcon: null,
      storyRawText: SENTENCE,
      ...fields,
    };
  }

  function projectFixture(icon: string | null): Project {
    return {
      id: 'project-1',
      name: PROJECT_NAME,
      description: '',
      icon,
      workspaceId: 'workspace-1',
      createdBy: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      storyCount: 1,
    };
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: vi.fn().mockResolvedValue(undefined),
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('renders the project’s own icon on the card chip when the task payload carries one (D24)', async () => {
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-icon', projectIcon: 'database' })],
    });

    render(<KanbanBoard locale="en" />);

    // The icon is the payload's name resolved by `IconDisplay`, not the folder.
    const chip = (await screen.findByText(PROJECT_NAME)).closest(
      '[data-base-ui-tooltip-trigger]',
    ) as HTMLElement;
    expect(chip.querySelector('.lucide-database')).not.toBeNull();
    expect(chip.querySelector('.lucide-folder-kanban')).toBeNull();
  });

  it('renders the folder fallback on the card chip when the project has no icon, leaving label and tooltip alone', async () => {
    const user = userEvent.setup();
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-noicon', projectIcon: null })],
    });

    render(<KanbanBoard locale="en" />);

    // An icon-less project draws the app's own default for one (D22).
    const chip = (await screen.findByText(PROJECT_NAME)).closest(
      '[data-base-ui-tooltip-trigger]',
    ) as HTMLElement;
    expect(chip.querySelector('.lucide-folder-kanban')).not.toBeNull();
    // A null icon must not touch the label or the tooltip: the name is intact
    // and the hover still names the project in full.
    expect(chip.textContent).toContain(PROJECT_NAME);
    await user.hover(chip);
    // The full name lives in the opened tooltip popup (the chip itself already
    // shows the truncated label, so the popup is queried directly).
    await waitFor(() =>
      expect(document.querySelector('[data-slot="tooltip-content"]')?.textContent).toBe(
        PROJECT_NAME,
      ),
    );
  });

  it('keeps the fingerprint on the story chip whether or not the project has an icon', async () => {
    for (const projectIcon of ['database', null]) {
      useTaskStore.setState({
        workspaceTasks: [chipTask({ id: 'task-story', projectIcon })],
      });

      const { unmount } = render(<KanbanBoard locale="en" />);

      // The story's icon is a fixed fallback — never a name — so it stays the
      // fingerprint whatever the project's own icon is.
      const storyChip = await screen.findByText(shortUUID(STORY_ID));
      expect(
        storyChip.closest('[data-base-ui-tooltip-trigger]')?.querySelector('.lucide-fingerprint'),
      ).not.toBeNull();

      unmount();
    }
  });

  it('uses the project’s own icon in the project select’s rows, matching the card’s for the same project (D22)', async () => {
    const user = userEvent.setup();
    useProjectStore.setState({
      projects: [projectFixture('database')],
      loading: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useTaskStore.setState({
      workspaceTasks: [chipTask({ id: 'task-icon', projectIcon: 'database' })],
    });

    render(<KanbanBoard locale="en" />);

    // The card draws the payload's icon...
    const cardChip = (await screen.findByText(PROJECT_NAME)).closest(
      '[data-base-ui-tooltip-trigger]',
    ) as HTMLElement;
    expect(cardChip.querySelector('.lucide-database')).not.toBeNull();

    // ...and the select's row for the same project draws the project's own
    // icon — the name the project row it lists carries — not the folder.
    await user.click(await screen.findByRole('combobox', { name: t.kanban.filter_project }));
    const option = await screen.findByRole('option', { name: PROJECT_NAME });
    expect(option.querySelector('.lucide-database')).not.toBeNull();
    expect(option.querySelector('.lucide-folder-kanban')).toBeNull();
  });

  it('renders the folder fallback on a project row whose project has no icon', async () => {
    const user = userEvent.setup();
    useProjectStore.setState({
      projects: [projectFixture(null)],
      loading: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useTaskStore.setState({ workspaceTasks: [] });

    render(<KanbanBoard locale="en" />);

    await user.click(await screen.findByRole('combobox', { name: t.kanban.filter_project }));
    const option = await screen.findByRole('option', { name: PROJECT_NAME });
    console.log('DEBUG-HTML', option.outerHTML);
    expect(option.querySelector('.lucide-folder-kanban')).not.toBeNull();
    expect(option.querySelector('.lucide-database')).toBeNull();
  });
});

/* ── Deep link entry (feature ``view-in-kanban``, WU1) ──
 *
 * A link to the board lands on ``/[locale]/kanban?project=<id>&story=<id>``
 * and the page passes the two ids to the island as `initialProjectId` /
 * `initialStoryId`. The cascade must come up already seeded: the project seeds
 * level one, the story level two **only when a project id also travelled** —
 * the cascade's invariant is that a child filter never exists without its
 * parent, so an orphan story id is ignored and the board loads unfiltered. No
 * version is seeded: the link names a story, not a run. As everywhere in this
 * file, the assertions look at the arguments that reach the mocked
 * `listTasksByWorkspace`, not at what the selects render.
 */
describe('KanbanBoard — deep link entry', () => {
  const mockProjects: Project[] = [
    {
      id: 'project-1',
      name: 'Alpha',
      description: '',
      workspaceId: 'workspace-1',
      createdBy: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      storyCount: 1,
    },
  ];

  const mockStories: UserStory[] = [
    {
      id: 'story-1',
      projectId: 'project-1',
      actor: 'user',
      feature: 'to log in',
      benefit: 'to access my account',
      rawText: 'As a user, I want to log in, so that I can access my account',
      status: 'extracted',
      createdAt: '2026-01-01T00:00:00Z',
    },
  ];

  const storyPage: PaginatedResponse<UserStory> = {
    items: mockStories,
    total: mockStories.length,
    page: 1,
    size: 100,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: {
        id: 'workspace-1',
        name: 'Test Workspace',
        slug: 'test-workspace',
        ownerId: 'user-1',
        role: 'admin',
        memberCount: 1,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      } as Workspace,
      loading: false,
      saving: false,
    });
    useProjectStore.setState({
      projects: mockProjects,
      loading: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    useTaskStore.setState({
      tasks: {},
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: realFetchTasksForWorkspace,
      updateTaskStatus: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(listStories).mockResolvedValue(storyPage);
    vi.mocked(listVersions).mockResolvedValue([]);
  });

  it('seeds the project level from initialProjectId: the first read is project-scoped and the select names it', async () => {
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" initialProjectId="project-1" />);

    // The very first read is already filtered: the cascade starts seeded, the
    // user never had to pick anything.
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1', {
        projectId: 'project-1',
      }),
    );
    // And the project select shows the project it is filtering by.
    const trigger = await screen.findByRole('combobox', { name: t.kanban.filter_project });
    expect(within(trigger).getByText('Alpha')).toBeInTheDocument();
  });

  it('seeds both levels from initialProjectId + initialStoryId: the read is story-scoped, one scope only', async () => {
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" initialProjectId="project-1" initialStoryId="story-1" />);

    // Most specific wins from the first call: `user_story_id`, and **no**
    // `project_id` beside it — two scopes are the backend's 422.
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1', {
        storyId: 'story-1',
      }),
    );
    const calls = vi.mocked(listTasksByWorkspace).mock.calls;
    expect(calls.every(([, filters]) => filters?.projectId === undefined)).toBe(true);

    // The story select shows the story once its options have loaded.
    const storyTrigger = await screen.findByRole('combobox', { name: t.kanban.filter_story });
    expect(within(storyTrigger).getByText(STORY_OPTION_LABEL)).toBeInTheDocument();
  });

  it('ignores an orphan initialStoryId with no project: the read stays the unfiltered workspace read', async () => {
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);

    render(<KanbanBoard locale="en" initialStoryId="story-1" />);

    // The unfiltered read: the workspace alone, no filters object.
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1'));
    const calls = vi.mocked(listTasksByWorkspace).mock.calls;
    expect(calls.every(([, filters]) => filters?.storyId === undefined)).toBe(true);

    // No story filter exists: the cascade's child never appears without its
    // parent, so the story select stays locked on its pick-a-project prompt.
    const storyTrigger = screen.getByRole('combobox', { name: t.kanban.filter_story });
    expect(storyTrigger).toBeDisabled();
    expect(within(storyTrigger).queryByText(STORY_OPTION_LABEL)).not.toBeInTheDocument();
  });

  it('keeps the seeded project filter when the workspace arrives only after mount', async () => {
    vi.mocked(listTasksByWorkspace).mockResolvedValue([]);
    // A fresh session: the persisted store has not selected a workspace yet, so
    // the board mounts with `currentWorkspace: null` and the real id arrives
    // when `fetchWorkspaces` auto-selects one.
    useWorkspaceStore.setState({ currentWorkspace: null });

    render(<KanbanBoard locale="en" initialProjectId="project-1" />);

    expect(await screen.findByText(t.kanban.no_workspace)).toBeInTheDocument();
    expect(listTasksByWorkspace).not.toHaveBeenCalled();

    // The workspace's first arrival — undefined → real id, not a switch.
    act(() => {
      useWorkspaceStore.setState({
        currentWorkspace: {
          id: 'workspace-1',
          name: 'Test Workspace',
          slug: 'test-workspace',
          ownerId: 'user-1',
          role: 'admin',
          memberCount: 1,
          createdAt: '2026-01-01T00:00:00Z',
          updatedAt: '2026-01-01T00:00:00Z',
        } as Workspace,
      });
    });

    // The seeded cascade survives it: the read is project-scoped, not the
    // whole-workspace read the old reset produced.
    await waitFor(() =>
      expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1', {
        projectId: 'project-1',
      }),
    );
  });
});
