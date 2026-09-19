import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ExportPanel } from '@/components/react/ExportPanel';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import type { Workspace } from '@/types/workspace';

vi.mock('@/lib/tasks-api', () => ({
  listTasks: vi.fn(),
  listTasksByWorkspace: vi.fn(),
  updateTask: vi.fn(),
  updateTaskStatus: vi.fn(),
  startExtraction: vi.fn(),
  getExtractionStatus: vi.fn(),
}));

describe('ExportPanel', () => {
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
    });
  });

  it('keeps Download enabled for a workspace with zero tasks', async () => {
    // An empty workspace still produces valid empty content from the backend,
    // so the download must remain reachable from the UI.
    render(<ExportPanel locale="en" />);

    await waitFor(() => {
      expect(screen.getByText('No tasks to export in this workspace.')).toBeInTheDocument();
    });

    const downloadButton = screen.getByRole('button', { name: 'Download' });
    expect(downloadButton).toBeEnabled();
  });

  it('reports a failed task load with what the API answered', async () => {
    // This branch had no test at all. It is worth pinning now because the store keeps the
    // whole failure rather than a message: the page supplies its own headline, so the status
    // and the machine code can only reach the card through the structured fields.
    useTaskStore.setState({
      error: {
        friendlyMessage: 'the workspace could not be read',
        rawDetail: { detail: 'the workspace could not be read' },
        status: 500,
        errorCode: 'WORKSPACE_TASKS_FAILED',
      },
    });

    render(<ExportPanel locale="en" />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Failed to load tasks for export');
    expect(alert).toHaveTextContent('HTTP 500');
    expect(alert).toHaveTextContent('WORKSPACE_TASKS_FAILED');
  });
});
