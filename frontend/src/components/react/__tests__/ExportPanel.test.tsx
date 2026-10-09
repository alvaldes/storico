import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ExportPanel } from '@/components/react/ExportPanel';
import { listTasksByWorkspace } from '@/lib/tasks-api';
import { listStories } from '@/lib/stories-api';
import {
  getTrelloExport,
  resolveTrelloExportTarget,
  triggerTrelloExport,
  type TrelloExportJob,
} from '@/lib/trello-api';
import { ApiRequestError } from '@/lib/api';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useProjectStore } from '@/stores/projectStore';
import { useTranslations } from '@/i18n/utils';
import en from '@/i18n/en.json';
import type { Task } from '@/types/task';
import type { Workspace } from '@/types/workspace';
import type { Project } from '@/types/project';
import type { UserStory } from '@/types/story';

type TrelloModule = typeof import('@/lib/trello-api');

vi.mock('@/lib/tasks-api', () => ({
  listTasks: vi.fn(),
  listTasksByWorkspace: vi.fn(),
  updateTask: vi.fn(),
  updateTaskStatus: vi.fn(),
  startExtraction: vi.fn(),
  getExtractionStatus: vi.fn(),
}));

vi.mock('@/lib/stories-api', () => ({
  listStories: vi.fn(),
}));

// The resolver and the terminal-status predicate stay real: the one-target-by-
// construction claim is about their shape, so mocking them would vacate it. Only
// the two network calls are replaced.
vi.mock('@/lib/trello-api', async (importOriginal) => ({
  ...(await importOriginal<TrelloModule>()),
  triggerTrelloExport: vi.fn(),
  getTrelloExport: vi.fn(),
}));

const t = useTranslations('en');

function makeProject(id = 'project-1', name = 'Alpha Project'): Project {
  return {
    id,
    name,
    description: '',
    icon: null,
    workspaceId: 'workspace-1',
    createdBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 1,
  };
}

function makeStory(id = 'story-1'): UserStory {
  return {
    id,
    projectId: 'project-1',
    actor: 'user',
    feature: 'to log in',
    benefit: '',
    rawText: 'As a user, I want to log in, so that I can access my account',
    createdAt: '2026-01-01T00:00:00Z',
    status: 'pending_extraction',
  };
}

function makeJob(overrides: Record<string, unknown> = {}): TrelloExportJob {
  return {
    id: 'job-1',
    workspaceId: 'workspace-1',
    scope: 'workspace',
    projectId: null,
    userStoryId: null,
    status: 'pending',
    errorCode: null,
    boardId: null,
    boardUrl: null,
    cardsCreated: null,
    createdAt: '2026-01-01T00:00:00Z',
    completedAt: null,
    ...overrides,
  } as TrelloExportJob;
}

// The real store action, captured before any test replaces it: the 6.7 case drives the
// panel's actual fetch path (store → `listTasksByWorkspace`) instead of stubbing it.
const realFetchTasksForWorkspace = useTaskStore.getState().fetchTasksForWorkspace;

describe('ExportPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The Trello scope cascade reads the workspace's projects and, once a project
    // is picked, its stories. Seed both quietly: the store must not hit the
    // network here, and the cascade must have one project to offer.
    useProjectStore.setState({
      projects: [makeProject()],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(listStories).mockResolvedValue({
      items: [makeStory()],
      total: 1,
      page: 1,
      size: 20,
    });
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

  it('counts only the tasks the current-version workspace read returns', async () => {
    // One story with two completed runs: the backend's current-version filter (WU3 3.7,
    // `list_current_by_workspace`) is carried by `listTasksByWorkspace`, the endpoint the
    // panel fetches through — so the answer holds only the current version's four tasks,
    // and the count the panel shows is 4, never 8.
    const currentVersionTasks: Task[] = [
      'v2 schema',
      'v2 endpoint',
      'v2 UI',
      'v2 tests',
    ].map((title, i): Task => ({
      id: `task-v2-${i + 1}`,
      storyId: 'story-1',
      title,
      description: `Description for ${title}`,
      status: 'todo',
      priority: 'medium',
      labels: [],
      dependencies: [],
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    }));
    vi.mocked(listTasksByWorkspace).mockResolvedValue(currentVersionTasks);
    useTaskStore.setState({
      workspaceTasks: [],
      loading: false,
      error: null,
      updatingTaskId: null,
      allowedTransitions: {},
      fetchTasksForWorkspace: realFetchTasksForWorkspace,
    });

    render(<ExportPanel locale="en" />);

    // The read went through the workspace endpoint that carries the current-version filter.
    await waitFor(() => expect(listTasksByWorkspace).toHaveBeenCalledWith('workspace-1'));

    // The panel counts exactly the tasks that read returned.
    expect(await screen.findByText('4 tasks to export')).toBeInTheDocument();
  });
});

describe('ExportPanel — Trello export', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The same quiet defaults the panel's own describe seeds: the stores are
    // module singletons, so this describe must not depend on the previous one
    // having run (a `-t` filter would leave them empty).
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
    useProjectStore.setState({
      projects: [makeProject()],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(listStories).mockResolvedValue({
      items: [makeStory()],
      total: 1,
      page: 1,
      size: 20,
    });
  });

  /** Open the select whose accessible name is `label` and pick `optionLabel`. */
  async function pick(
    user: ReturnType<typeof userEvent.setup>,
    label: string,
    optionLabel: string,
  ) {
    await user.click(await screen.findByRole('combobox', { name: label }));
    await user.click(await screen.findByRole('option', { name: optionLabel }));
  }

  /** Render the panel with the quiet defaults the Trello section needs. */
  async function renderPanel(user: ReturnType<typeof userEvent.setup>) {
    render(<ExportPanel locale="en" />);
    // The download card settles first; the Trello section is in the same tree.
    await screen.findByText(t.exportPage.trello_section_title);
    return user;
  }

  it('states the new-board limitation where the trigger button is (D3)', async () => {
    const user = userEvent.setup();
    await renderPanel(user);

    const note = screen.getByText(t.exportPage.trello_new_board_note);
    // The note sits where the button is: the same card, not a distant footnote.
    expect(note.closest('section')).toContainElement(
      screen.getByRole('button', { name: t.exportPage.trello_trigger }),
    );
  });

  it('sends exactly one target: the story beats its project, and both can never travel together', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockResolvedValue(makeJob({ status: 'running' }));
    await renderPanel(user);

    await pick(user, t.exportPage.trello_scope_project_label, 'Alpha Project');
    await pick(user, t.exportPage.trello_scope_story_label, 'user: to log in');
    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    await waitFor(() => expect(triggerTrelloExport).toHaveBeenCalledTimes(1));
    const [, body] = vi.mocked(triggerTrelloExport).mock.calls[0];
    // Most-specific-wins, the Kanban cascade's rule: one key, never two.
    expect(body).toEqual({ user_story_id: 'story-1' });
  });

  it('narrowing to a project alone sends that project and nothing else', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockResolvedValue(makeJob({ status: 'running' }));
    await renderPanel(user);

    await pick(user, t.exportPage.trello_scope_project_label, 'Alpha Project');
    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    await waitFor(() => expect(triggerTrelloExport).toHaveBeenCalledTimes(1));
    expect(vi.mocked(triggerTrelloExport).mock.calls[0][1]).toEqual({ project_id: 'project-1' });
  });

  it('exports the whole workspace when nothing is picked', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockResolvedValue(makeJob({ status: 'running' }));
    await renderPanel(user);

    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    await waitFor(() => expect(triggerTrelloExport).toHaveBeenCalledTimes(1));
    expect(vi.mocked(triggerTrelloExport).mock.calls[0][1]).toEqual({});
  });

  it('keeps the one-target guarantee in the resolver itself, so two targets are impossible by construction', () => {
    // The unit behind the component claim: even a caller that holds both ids —
    // an impossible UI state, but a trivially constructible argument pair —
    // gets one target back, and the most specific one.
    expect(resolveTrelloExportTarget('project-1', 'story-1')).toEqual({ user_story_id: 'story-1' });
    expect(resolveTrelloExportTarget('project-1', null)).toEqual({ project_id: 'project-1' });
    expect(resolveTrelloExportTarget(null, 'story-1')).toEqual({ user_story_id: 'story-1' });
    expect(resolveTrelloExportTarget(null, null)).toEqual({});
  });

  it('surfaces a failed job through its translated error code, not raw prose', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockResolvedValue(
      makeJob({
        status: 'failed',
        errorCode: 'TRELLO_CREDENTIAL_REJECTED',
        boardUrl: 'https://trello.com/b/half/half-built',
      }),
    );
    await renderPanel(user);

    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    const alert = await screen.findByRole('alert');
    // The translated copy, not the code and not backend English prose.
    expect(alert).toHaveTextContent(en.errorCodes.TRELLO_CREDENTIAL_REJECTED);
    // A half-built board stays reachable, per the job's own board_url.
    expect(
      screen.getByRole('link', { name: t.exportPage.trello_board_link }),
    ).toHaveAttribute('href', 'https://trello.com/b/half/half-built');
  });

  it('answers a refused trigger (409, no credentials) with the translated code', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockRejectedValue(
      new ApiRequestError(409, 'Conflict', 'no credentials', {
        detail: 'no credentials',
        error_code: 'TRELLO_CREDENTIALS_MISSING',
      }),
    );
    await renderPanel(user);

    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(en.errorCodes.TRELLO_CREDENTIALS_MISSING);
  });

  it('links the completed board and counts its cards', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockResolvedValue(
      makeJob({
        status: 'completed',
        boardUrl: 'https://trello.com/b/abc/test-workspace',
        cardsCreated: 7,
        completedAt: '2026-01-01T00:05:00Z',
      }),
    );
    await renderPanel(user);

    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    expect(
      await screen.findByRole('link', { name: t.exportPage.trello_board_link }),
    ).toHaveAttribute('href', 'https://trello.com/b/abc/test-workspace');
    expect(screen.getByText('7 cards created.')).toBeInTheDocument();
  });

  it('polls a running job until it is terminal, then stops — it does not hammer the endpoint', async () => {
    vi.useFakeTimers();
    try {
      const running = makeJob({ status: 'running' });
      vi.mocked(triggerTrelloExport).mockResolvedValue(running);
      vi.mocked(getTrelloExport).mockResolvedValue(
        makeJob({
          status: 'completed',
          boardUrl: 'https://trello.com/b/abc/test-workspace',
          cardsCreated: 7,
          completedAt: '2026-01-01T00:05:00Z',
        }),
      );
      render(<ExportPanel locale="en" />);
      // Flush the mount effects before touching fake timers: RTL's `findBy*`
      // polls with timers of its own and would hang against the fakes.
      await act(async () => {});
      // Synchronous dispatch: userEvent's own event loop waits on timers of its
      // own and hangs against the fakes, so this one click uses fireEvent.
      fireEvent.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));
      // A flush, not a `waitFor`: waitFor polls with timers of its own, which
      // the fakes below would hold still.
      await act(async () => {});
      expect(triggerTrelloExport).toHaveBeenCalledTimes(1);
      expect(screen.getByText(t.exportPage.trello_running)).toBeInTheDocument();
      expect(getTrelloExport).not.toHaveBeenCalled();

      // One tick, one poll.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(getTrelloExport).toHaveBeenCalledTimes(1);
      expect(getTrelloExport).toHaveBeenCalledWith('workspace-1', 'job-1');

      // The poll answered terminal, so the link renders — and time passing
      // brings no further polls.
      expect(
        screen.getByRole('link', { name: t.exportPage.trello_board_link }),
      ).toHaveAttribute('href', 'https://trello.com/b/abc/test-workspace');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30000);
      });
      expect(getTrelloExport).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
