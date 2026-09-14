import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KanbanBoard } from '@/components/react/KanbanBoard';
import * as api from '@/lib/tasks-api';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import type { Task } from '@/types/task';
import type { Workspace } from '@/types/workspace';

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
});
