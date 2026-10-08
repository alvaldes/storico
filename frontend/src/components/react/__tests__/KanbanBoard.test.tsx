import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KanbanBoard } from '@/components/react/KanbanBoard';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useTranslations } from '@/i18n/utils';
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

    await chooseOption(user, t.kanban.filter_story, 'user: to log in');

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
    await chooseOption(user, t.kanban.filter_story, 'user: to log in');
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
