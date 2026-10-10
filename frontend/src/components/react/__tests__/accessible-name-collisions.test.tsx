import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StoryForm } from '@/components/react/StoryForm';
import { TaskEditor } from '@/components/react/TaskEditor';
import { StoryDetail } from '@/components/react/StoryDetail';
import { ExportPanel } from '@/components/react/ExportPanel';
import { ApiRequestError } from '@/lib/api';
import * as versioningApi from '@/lib/versioning-api';
import { getLLMConfigStatus } from '@/lib/llm-config-api';
import { useTaskStore, type ExtractionState } from '@/stores/taskStore';
import { useStoryStore } from '@/stores/storyStore';
import { useProjectStore } from '@/stores/projectStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useAuthStore } from '@/stores/authStore';
import { useTranslations } from '@/i18n/utils';
import type { Task } from '@/types/task';
import type { Workspace } from '@/types/workspace';
import type { UserStory } from '@/types/story';
import type { Project } from '@/types/project';

/* ── Why this file exists ──────────────────────────────────────────────────
 *
 * `ErrorDisplay` accepts an optional `retryLabel`, and several call sites used
 * it to hand the retry button the SAME accessible name another button already
 * carries in the same rendered state. Two sub-classes:
 *
 * - Same action, one name (StoryForm, TaskEditor, StoryDetail): the retry sits
 *   beside the form's own submit / the header action, and both reach one
 *   handler. The rule: a retry that sits beside the form's own submit takes
 *   `common.retry` and never the submit's copy.
 * - Two different actions, one name (ExportPanel): the preview retry and the
 *   download retry can both be on the page at once while retrying different
 *   actions. The preview retry takes `common.retry`; the download retry must
 *   name the download. (The panel's older pair — the store-error retry and the
 *   download retry — ended with the one-section rework: the panel no longer
 *   fetches the workspace's tasks through the task store, so there is no
 *   store-error card to retry.)
 *
 * The rule lives in ONE helper (`expectNoSharedAccessibleButtonName`): render
 * each component in the exact state where the collision happens and assert
 * that no two buttons in that render share an accessible name.
 *
 * ─────────────────────────────────────────────────────────────────────────── */

// The components' mount effects and actions must settle without a backend.
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

vi.mock('@/lib/llm-config-api', () => ({
  getLLMConfigStatus: vi.fn(),
}));

vi.mock('@/lib/versioning-api', () => ({
  listVersions: vi.fn(),
  listStoryInvalidations: vi.fn(),
  createInvalidation: vi.fn(),
  listInvalidations: vi.fn(),
  revokeInvalidation: vi.fn(),
  fetchRepetition: vi.fn(),
}));

// The failure channels toast; the spy keeps the tests noise-free.
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const t = useTranslations('en');

/* ── The rule, in one place ── */

/**
 * The accessible name the way this rule cares about it: `aria-label`, then
 * `aria-labelledby`, then visible text. A button with no name at all is a
 * different accessibility problem and is out of scope here — the rule is
 * about two buttons sharing one name.
 */
function accessibleName(button: HTMLElement): string {
  const ariaLabel = button.getAttribute('aria-label');
  if (ariaLabel) return ariaLabel.replace(/\s+/g, ' ').trim();
  const labelledBy = button.getAttribute('aria-labelledby');
  if (labelledBy) {
    return labelledBy
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent ?? '')
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim();
  }
  return (button.textContent ?? '').replace(/\s+/g, ' ').trim();
}

/**
 * In the rendered state under test, no two buttons may share an accessible
 * name. Every collision test below ends with this one assertion, so a revert
 * of any single call-site fix turns exactly one test red here.
 */
function expectNoSharedAccessibleButtonName() {
  const names = screen
    .getAllByRole('button')
    .map(accessibleName)
    .filter((name) => name !== '');
  const duplicates = names.filter((name, i) => names.indexOf(name) !== i);
  expect([...new Set(duplicates)]).toEqual([]);
}

/* ── Fixtures ── */

function makeWorkspace(id: string): Workspace {
  return {
    id,
    name: id,
    slug: id,
    ownerId: 'user-1',
    role: 'admin',
    memberCount: 1,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  };
}

const story: UserStory = {
  id: 'story-1',
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

const editorTask: Task = {
  id: 'task-1',
  storyId: 'story-1',
  title: 'DB schema',
  description: 'Create the database schema',
  status: 'todo',
  priority: 'high',
  labels: ['db', 'backend'],
  dependencies: [],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

const failedExtraction: ExtractionState = {
  extractionId: 'ext-1',
  status: 'failed',
  userStoryStatus: 'failed_extraction',
  error: { friendlyMessage: 'Extraction failed', rawDetail: 'boom', status: 500 },
  errorCode: 'server',
  versionNumber: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  // The D16 repetition read answers "no match" by default.
  vi.mocked(versioningApi.fetchRepetition).mockResolvedValue({ matches: [] });
  vi.mocked(versioningApi.listStoryInvalidations).mockResolvedValue([]);
  vi.mocked(versioningApi.listInvalidations).mockResolvedValue([]);
  vi.mocked(versioningApi.listVersions).mockResolvedValue([]);
  // The configuration gate passes by default; only its answer matters here.
  vi.mocked(getLLMConfigStatus).mockResolvedValue({
    configured: true,
    provider: 'ollama',
    missing: [],
  });
  useWorkspaceStore.setState({
    workspaces: [],
    currentWorkspace: makeWorkspace('ws-1'),
    loading: false,
    saving: false,
  });
  useAuthStore.setState({ user: { id: 'user-1', email: 'u@example.com', name: 'User One' } });
  useProjectStore.setState({ projects: [project], loading: false, error: null });
  useStoryStore.setState({
    stories: [story],
    loading: false,
    saving: false,
    fetchStory: vi.fn().mockResolvedValue(undefined),
    updateStory: vi.fn().mockResolvedValue(undefined),
    deleteStory: vi.fn().mockResolvedValue(undefined),
    fetchVersions: vi.fn().mockResolvedValue(undefined),
  });
  useTaskStore.setState({
    tasks: {},
    workspaceTasks: [],
    extractions: {},
    loading: false,
    error: null,
    updatingTaskId: null,
    allowedTransitions: {},
    fetchTasks: vi.fn().mockResolvedValue(undefined),
    extractTasks: vi.fn().mockResolvedValue(undefined),
    fetchTasksForWorkspace: vi.fn().mockResolvedValue(undefined),
    updateTask: vi.fn().mockResolvedValue(undefined),
  });
});

/* ── Site 1: StoryForm ── */

describe('StoryForm — the error-card retry never borrows the submit copy', () => {
  it('create mode: no two buttons share an accessible name while the submit error shows', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockRejectedValue(
      new ApiRequestError(500, 'Server Error', 'boom', { detail: 'boom' }),
    );
    render(<StoryForm open={true} onOpenChange={vi.fn()} onSubmit={onSubmit} locale="en" />);

    // Fill the three parts fields so local validation passes and the submit
    // reaches `onSubmit`, which rejects with a backend error.
    await user.type(screen.getByLabelText(t.stories.actor_label), 'user');
    await user.type(screen.getByLabelText(t.stories.feature_label), 'log in');
    await user.type(screen.getByLabelText(t.stories.benefit_label), 'access my account');

    await user.click(screen.getByRole('button', { name: t.common.create }));

    // The error card is up: it carries the retry under test.
    await screen.findByRole('button', { name: t.errorDisplay.dismiss });
    expect(onSubmit).toHaveBeenCalledTimes(1);

    expectNoSharedAccessibleButtonName();
  });

  it('edit mode: no two buttons share an accessible name while the submit error shows', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockRejectedValue(
      new ApiRequestError(500, 'Server Error', 'boom', { detail: 'boom' }),
    );
    render(
      <StoryForm
        open={true}
        onOpenChange={vi.fn()}
        onSubmit={onSubmit}
        locale="en"
        initialData={{ actor: 'user', feature: 'log in', benefit: 'access my account' }}
      />,
    );

    await user.click(screen.getByRole('button', { name: t.common.save }));
    await screen.findByRole('button', { name: t.errorDisplay.dismiss });

    expectNoSharedAccessibleButtonName();
  });
});

/* ── Site 2: TaskEditor ── */

describe('TaskEditor — the save-error retry never borrows the save copy', () => {
  it('no two buttons share an accessible name while the save error shows', async () => {
    const user = userEvent.setup();
    // The editor talks to the STORE's `updateTask` action, not to the API
    // client directly: the stub that must reject is the store action.
    const storeUpdateTask = vi.fn().mockRejectedValue(new Error('Network error'));
    useTaskStore.setState({ updateTask: storeUpdateTask });

    render(
      <TaskEditor
        task={editorTask}
        open={true}
        frozen={false}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    // Unique before the error: exactly the footer save button.
    await user.click(screen.getByRole('button', { name: t.taskEditor.save }));

    // The save-error card is up; the retry under test is rendered beside it.
    await waitFor(() => {
      expect(storeUpdateTask).toHaveBeenCalledTimes(1);
    });
    await screen.findByRole('button', { name: t.errorDisplay.dismiss });

    expectNoSharedAccessibleButtonName();
  });
});

/* ── Site 3: StoryDetail ── */

describe('StoryDetail — the extraction-error retry never borrows the header copy', () => {
  it('no two buttons share an accessible name while a failed extraction shows', async () => {
    useTaskStore.setState({ extractions: { 'story-1': failedExtraction } });

    render(<StoryDetail locale="en" storyId="story-1" />);

    // The failed state renders the header retry AND the error card.
    await screen.findByRole('alert');

    expectNoSharedAccessibleButtonName();
  });
});

/* ── Site 4: ExportPanel — two different actions must not share one name ── */

describe('ExportPanel — the preview retry and the download retry have different names', () => {
  it('no two buttons share an accessible name while both error cards show', async () => {
    const user = userEvent.setup();
    // Every request the panel makes fails at the network itself, so no
    // envelope code is translated and the caller's copy carries the cards.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));

    render(<ExportPanel locale="en" />);

    // The preview read runs on mount, so the preview's failure card is up
    // first; its retry takes the shared `common.retry` name.
    await waitFor(() => {
      expect(screen.getAllByRole('alert')).toHaveLength(1);
    });
    // The download fails too, on the same dead network, and its card joins
    // the preview's: two different actions, retried by two buttons that had
    // better not share one name.
    await user.click(screen.getByRole('button', { name: t.exportPage.download }));
    await waitFor(() => {
      expect(screen.getAllByRole('alert')).toHaveLength(2);
    });

    expectNoSharedAccessibleButtonName();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });
});
