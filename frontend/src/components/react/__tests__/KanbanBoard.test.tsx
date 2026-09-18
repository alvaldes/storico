import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KanbanBoard } from '@/components/react/KanbanBoard';
import * as api from '@/lib/tasks-api';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useTranslations } from '@/i18n/utils';
import type { Task } from '@/types/task';
import type { Workspace } from '@/types/workspace';

const t = useTranslations('en');

// Mock the api module — the store consumes these mocks.
vi.mock('@/lib/tasks-api', () => ({
  updateTask: vi.fn(),
}));

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
      error: null,
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
      useTaskStore.setState({ error: 'the board is unavailable', loading: false });
    });
    useTaskStore.setState({ fetchTasksForWorkspace, error: null });

    render(<KanbanBoard locale="en" />);

    // This state replaces the whole page, so before the component rendered something a
    // failed load left the board empty with no explanation at all.
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('the board is unavailable');
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
        useTaskStore.setState({ error: 'the board is unavailable', loading: false });
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
