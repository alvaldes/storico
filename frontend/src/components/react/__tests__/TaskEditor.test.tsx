import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TaskEditor } from '@/components/react/TaskEditor';
import * as api from '@/lib/tasks-api';
import { useTaskStore } from '@/stores/taskStore';
import type { Task } from '@/types/task';

// Mock the api module — the store consumes these mocks.
vi.mock('@/lib/tasks-api', () => ({
  updateTask: vi.fn(),
}));

const mockTask: Task = {
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
};

describe('TaskEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useTaskStore.setState({
      tasks: { 'story-1': [mockTask] },
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
    });
  });

  /* ── Label validation ── */

  it('rejects empty label', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const labelInput = screen.getByPlaceholderText('Add a label and press Enter');
    await user.type(labelInput, '{Enter}');

    expect(screen.getByText('Label cannot be empty')).toBeInTheDocument();
  });

  it('rejects duplicate label (case-insensitive)', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const labelInput = screen.getByPlaceholderText('Add a label and press Enter');
    await user.type(labelInput, 'DB{Enter}');

    expect(screen.getByText('Label already exists')).toBeInTheDocument();
  });

  it('accepts a new unique label', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const labelInput = screen.getByPlaceholderText('Add a label and press Enter');
    await user.type(labelInput, 'api{Enter}');

    expect(screen.queryByText('Label already exists')).not.toBeInTheDocument();
    expect(screen.queryByText('Label cannot be empty')).not.toBeInTheDocument();
    expect(screen.getByText('api')).toBeInTheDocument();
  });

  /* ── Dependency validation ── */

  it('rejects empty dependency', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const depInput = screen.getByPlaceholderText('Add a dependency and press Enter');
    await user.type(depInput, '{Enter}');

    expect(screen.getByText('Dependency cannot be empty')).toBeInTheDocument();
  });

  it('rejects self-dependency', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const depInput = screen.getByPlaceholderText('Add a dependency and press Enter');
    await user.type(depInput, 'task-1{Enter}');

    expect(screen.getByText('A task cannot depend on itself')).toBeInTheDocument();
  });

  it('silently deduplicates duplicate dependency', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const depInput = screen.getByPlaceholderText('Add a dependency and press Enter');
    await user.type(depInput, 'task-0{Enter}');

    expect(screen.queryByText('Dependency cannot be empty')).not.toBeInTheDocument();
    expect(screen.queryByText('A task cannot depend on itself')).not.toBeInTheDocument();
  });

  /* ── Save / rollback ── */

  it('optimistically updates, applies server response, and closes on success', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    const serverResponse: Task = {
      ...mockTask,
      title: 'Updated title',
      description: 'Updated desc',
      labels: ['db'],
      dependencies: [],
      updatedAt: '2026-01-02T00:00:00Z',
    };
    vi.mocked(api.updateTask).mockResolvedValue(serverResponse);

    render(
      <TaskEditor task={mockTask} open={true} onOpenChange={onOpenChange} locale="en" />,
    );

    await screen.findByText('Edit Task');

    const titleInput = screen.getByPlaceholderText('Task title');
    await user.clear(titleInput);
    await user.type(titleInput, 'Updated title');

    await user.click(screen.getByText('Save Changes'));

    // store.updateTask called exactly once with the optimistic payload.
    expect(api.updateTask).toHaveBeenCalledTimes(1);
    expect(api.updateTask).toHaveBeenCalledWith('task-1', {
      title: 'Updated title',
      description: 'Create the database schema',
      labels: ['db', 'backend'],
      dependencies: ['task-0'],
    });

    // After the PUT resolves, the store applies the server-authoritative Task.
    await waitFor(() => {
      const state = useTaskStore.getState();
      const stored = state.tasks['story-1']?.find((t) => t.id === 'task-1');
      expect(stored).toMatchObject({
        id: 'task-1',
        title: 'Updated title',
        description: 'Updated desc',
        labels: ['db'],
        dependencies: [],
      });
    });

    // updatingTaskId cleared after settle.
    await waitFor(() => {
      expect(useTaskStore.getState().updatingTaskId).toBeNull();
    });

    // Dialog closed after success.
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('rolls back the optimistic update and keeps dialog open on save failure', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    vi.mocked(api.updateTask).mockRejectedValue(new Error('Network error'));

    render(
      <TaskEditor task={mockTask} open={true} onOpenChange={onOpenChange} locale="en" />,
    );

    await screen.findByText('Edit Task');

    await user.click(screen.getByText('Save Changes'));

    // store.updateTask attempted the PUT exactly once.
    await waitFor(() => {
      expect(api.updateTask).toHaveBeenCalledTimes(1);
    });

    // Store rolled back to the original task snapshot.
    await waitFor(() => {
      const state = useTaskStore.getState();
      const stored = state.tasks['story-1']?.find((t) => t.id === 'task-1');
      expect(stored).toEqual(mockTask);
    });

    // updatingTaskId cleared even after rollback.
    await waitFor(() => {
      expect(useTaskStore.getState().updatingTaskId).toBeNull();
    });

    // Dialog stays open on error.
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  /* ── Form reset ── */

  it('resets form when dialog opens with a different task', async () => {
    const { rerender } = render(
      <TaskEditor task={mockTask} open={true} onOpenChange={vi.fn()} locale="en" />,
    );

    await screen.findByText('Edit Task');

    // Change title
    const titleInput = screen.getByPlaceholderText('Task title');
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, 'Changed title');

    // Rerender with a different task (simulating opening editor for another task)
    const otherTask: Task = { ...mockTask, id: 'task-2', title: 'Other task' };
    render(
      <TaskEditor task={otherTask} open={true} onOpenChange={vi.fn()} locale="en" />,
    );

    // Title should be reset to the new task's title
    await waitFor(() => {
      expect(screen.getByDisplayValue('Other task')).toBeInTheDocument();
    });
  });
});