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

import { listTasksByWorkspace } from '@/lib/tasks-api';

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
