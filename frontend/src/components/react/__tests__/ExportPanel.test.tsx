import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ExportPanel } from '@/components/react/ExportPanel';
import { listStories } from '@/lib/stories-api';
import { listVersions } from '@/lib/versioning-api';
import {
  getTrelloExport,
  previewTrelloExport,
  triggerTrelloExport,
  type TrelloExportJob,
} from '@/lib/trello-api';
import { resolveExportTarget } from '@/lib/task-export-api';
import { ApiRequestError } from '@/lib/api';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useProjectStore } from '@/stores/projectStore';
import { getTranslations } from '@/i18n/utils';
import en from '@/i18n/en.json';
import type { Workspace } from '@/types/workspace';
import type { Project } from '@/types/project';
import type { UserStory, StoryVersion } from '@/types/story';

type TrelloModule = typeof import('@/lib/trello-api');

vi.mock('@/lib/stories-api', () => ({
  listStories: vi.fn(),
}));

vi.mock('@/lib/versioning-api', () => ({
  listVersions: vi.fn(),
}));

// The terminal-status predicate stays real: the poll-stops-when-terminal claim
// is about its shape, so mocking it would vacate it. Only the network calls are
// replaced; the file export goes through `global fetch` (stubbed per test), the
// same seam the browser uses, so the URLs the panel asks for are asserted
// verbatim.
vi.mock('@/lib/trello-api', async (importOriginal) => ({
  ...(await importOriginal<TrelloModule>()),
  triggerTrelloExport: vi.fn(),
  getTrelloExport: vi.fn(),
  previewTrelloExport: vi.fn(),
}));

const t = getTranslations('en');

/* The treated row labels this page must share with the board (EP6): the
 * project's name cut at the one shared cap (`CONTEXT_LABEL_CAP`, 12), the
 * story as ``shortUUID · label`` (the id never truncated, the label cut at the
 * same cap), and the current version carrying the same current marker word the
 * board uses (`versionSelector.current`). Composed here once so each assertion
 * names the shape, not a copy of it. */
const PROJECT_ROW = 'Alpha Projec...';
const PROJECT_FULL_NAME = 'Alpha Project';
const STORY_ROW = 'story-1 · user: to log...';
const STORY_2_ROW = 'story-2 · user: to exp...';
const STORY_SENTENCE = 'As a user, I want to log in, so that I can access my account';
const CURRENT_VERSION_ROW = `v2 · ${en.versionSelector.current}`;

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

function makeStory(id = 'story-1', feature = 'to log in'): UserStory {
  return {
    id,
    projectId: 'project-1',
    actor: 'user',
    feature,
    benefit: '',
    rawText: `As a user, I want ${feature}, so that I can access my account`,
    createdAt: '2026-01-01T00:00:00Z',
    status: 'pending_extraction',
  };
}

function makeVersion(id = 'ext-1', versionNumber = 2): StoryVersion {
  return {
    id,
    versionNumber,
    status: 'completed',
    modelUsed: 'llama3.2',
    provider: 'ollama',
    temperature: 0.1,
    createdAt: '2026-01-01T00:00:00Z',
    completedAt: '2026-01-01T00:01:00Z',
    errorInfo: null,
    isCurrent: true,
    hasOutput: true,
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

/** A plain-object Response stand-in: only the members the export client reads. */
function httpResponse(
  body: string,
  init: { status?: number; headers?: Record<string, string> } = {},
): Response {
  const status = init.status ?? 200;
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    text: async () => body,
    blob: async () => new Blob([body]),
    headers: new Headers(init.headers),
  } as unknown as Response;
}

type FetchRoute = {
  match: (url: string) => boolean;
  respond: (url: string) => Response;
};

/**
 * Stub `global fetch` with a URL router — the stores' reads go through the
 * shared client and the export reads go through raw fetch, so every request
 * this page makes funnels through here and an unrouted URL fails loudly.
 */
function stubFetch(routes: FetchRoute[]): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const route = routes.find((r) => r.match(url));
    if (!route) throw new Error(`unexpected fetch: ${url}`);
    return route.respond(url);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function jsonRoute(pattern: RegExp, body: unknown): FetchRoute {
  return {
    match: (url) => pattern.test(url),
    respond: () => httpResponse(JSON.stringify(body)),
  };
}

const FILE_EXPORT_URL = /\/api\/v1\/workspaces\/workspace-1\/export\/tasks\?/;
const TRELLO_PREVIEW_URL = /\/api\/v1\/workspaces\/workspace-1\/export\/trello\/preview/;

describe('ExportPanel — the toolbar', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

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
      size: 100,
    });
    vi.mocked(listVersions).mockResolvedValue([makeVersion()]);
    // The toolbar's Trello-format tests click the Trello button, which reads
    // the preview; it answers a plan without ever creating a job.
    vi.mocked(previewTrelloExport).mockResolvedValue({ name: 'Test Workspace', columns: [] });
    // The default route set: the export preview answers a fixed body so every
    // test can assert on the URL it was asked for.
    fetchMock = stubFetch([
      {
        match: (url) => FILE_EXPORT_URL.test(url),
        respond: () => httpResponse('[]'),
      },
    ]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

  it('keeps the download reachable for a workspace with zero tasks', async () => {
    // An empty workspace still produces valid empty content from the backend,
    // so the download must remain reachable from the UI.
    render(<ExportPanel locale="en" />);

    expect(await screen.findByRole('button', { name: t.exportPage.download })).toBeEnabled();
  });

  it('renders one section: toolbar, formats, preview and action share the same card', async () => {
    const user = userEvent.setup();
    render(<ExportPanel locale="en" />);

    const preview = await screen.findByTestId('export-preview');
    const section = preview.closest('section');
    expect(section).not.toBeNull();
    // The action button lives in the same section the toolbar and the preview do.
    expect(section).toContainElement(screen.getByRole('button', { name: t.exportPage.download }));
    expect(section).toContainElement(
      screen.getByRole('combobox', { name: t.exportPage.scope_project_label }),
    );
    await user.click(screen.getByRole('button', { name: 'Trello' }));
    expect(section).toContainElement(
      await screen.findByRole('button', { name: t.exportPage.trello_trigger }),
    );
  });

  it('disables the version selector until a story is chosen', async () => {
    // A version belongs to a story, and the API answers 422 for one asked at
    // project or workspace level — the control makes that impossible instead of
    // letting the user find out.
    const user = userEvent.setup();
    render(<ExportPanel locale="en" />);

    const versionSelect = await screen.findByRole('combobox', {
      name: t.exportPage.scope_version_label,
    });
    expect(versionSelect).toBeDisabled();

    await pick(user, t.exportPage.scope_project_label, PROJECT_ROW);
    expect(screen.getByRole('combobox', { name: t.exportPage.scope_version_label })).toBeDisabled();

    await pick(user, t.exportPage.scope_story_label, STORY_ROW);
    expect(screen.getByRole('combobox', { name: t.exportPage.scope_version_label })).toBeEnabled();
  });

  /** Select the Trello format, whose action is the trigger rather than the download. */
  async function chooseTrello(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: 'Trello' }));
    await screen.findByRole('button', { name: t.exportPage.trello_trigger });
  }

  it('sends exactly one target for the Trello body: the story beats its project, and the version rides along', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockResolvedValue(makeJob({ status: 'running' }));
    render(<ExportPanel locale="en" />);

    await pick(user, t.exportPage.scope_project_label, PROJECT_ROW);
    await pick(user, t.exportPage.scope_story_label, STORY_ROW);
    await pick(user, t.exportPage.scope_version_label, CURRENT_VERSION_ROW);
    await chooseTrello(user);
    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    await waitFor(() => expect(triggerTrelloExport).toHaveBeenCalledTimes(1));
    const [, body] = vi.mocked(triggerTrelloExport).mock.calls[0];
    // Most-specific-wins, the Kanban cascade's rule: the story travels, its
    // project does not, and the chosen version names its extraction.
    expect(body).toEqual({ user_story_id: 'story-1', extraction_id: 'ext-1' });
  });

  it('narrowing to a project alone sends that project and nothing else', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockResolvedValue(makeJob({ status: 'running' }));
    render(<ExportPanel locale="en" />);

    await pick(user, t.exportPage.scope_project_label, PROJECT_ROW);
    await chooseTrello(user);
    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    await waitFor(() => expect(triggerTrelloExport).toHaveBeenCalledTimes(1));
    expect(vi.mocked(triggerTrelloExport).mock.calls[0][1]).toEqual({ project_id: 'project-1' });
  });

  it('exports the whole workspace when nothing is picked', async () => {
    const user = userEvent.setup();
    vi.mocked(triggerTrelloExport).mockResolvedValue(makeJob({ status: 'running' }));
    render(<ExportPanel locale="en" />);

    await chooseTrello(user);
    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    await waitFor(() => expect(triggerTrelloExport).toHaveBeenCalledTimes(1));
    expect(vi.mocked(triggerTrelloExport).mock.calls[0][1]).toEqual({});
  });

  it('changing the story drops the previous story\'s version — no stale extraction can travel', async () => {
    const user = userEvent.setup();
    vi.mocked(listStories).mockResolvedValue({
      items: [makeStory('story-1'), makeStory('story-2', 'to export reports')],
      total: 2,
      page: 1,
      size: 100,
    });
    vi.mocked(listVersions).mockImplementation(async (storyId) =>
      storyId === 'story-1' ? [makeVersion('ext-1', 2)] : [makeVersion('ext-2', 1)],
    );
    vi.mocked(triggerTrelloExport).mockResolvedValue(makeJob({ status: 'running' }));
    render(<ExportPanel locale="en" />);

    await pick(user, t.exportPage.scope_project_label, PROJECT_ROW);
    await pick(user, t.exportPage.scope_story_label, STORY_ROW);
    await pick(user, t.exportPage.scope_version_label, CURRENT_VERSION_ROW);
    // Move to the other story: the version choice was that story's, so it is
    // gone — a surviving extraction would name a story this export no longer
    // names.
    await pick(user, t.exportPage.scope_story_label, STORY_2_ROW);
    await chooseTrello(user);
    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    await waitFor(() => expect(triggerTrelloExport).toHaveBeenCalledTimes(1));
    expect(vi.mocked(triggerTrelloExport).mock.calls[0][1]).toEqual({ user_story_id: 'story-2' });
  });

  it('builds the file export\'s query from the same resolved target — one target, never two', async () => {
    const user = userEvent.setup();
    render(<ExportPanel locale="en" />);

    await pick(user, t.exportPage.scope_project_label, PROJECT_ROW);
    await pick(user, t.exportPage.scope_story_label, STORY_ROW);
    await pick(user, t.exportPage.scope_version_label, CURRENT_VERSION_ROW);
    await user.click(screen.getByRole('button', { name: t.exportPage.download }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls.at(-1)![0]);
    expect(url).toContain('user_story_id=story-1');
    expect(url).toContain('extraction_id=ext-1');
    // The story implies its project: the project never travels beside it.
    expect(url).not.toContain('project_id=');
    // And the download is the download, not the preview.
    expect(url).not.toContain('preview=');
  });

  it('keeps the one-target guarantee in the resolver itself, so two targets are impossible by construction', () => {
    // The unit behind the component claim: even a caller that holds every id —
    // impossible UI states, but trivially constructible argument pairs — gets
    // one coherent target back, and the most specific one.
    expect(resolveExportTarget('project-1', 'story-1', 'ext-1')).toEqual({
      user_story_id: 'story-1',
      extraction_id: 'ext-1',
    });
    expect(resolveExportTarget('project-1', 'story-1', null)).toEqual({ user_story_id: 'story-1' });
    expect(resolveExportTarget('project-1', null, null)).toEqual({ project_id: 'project-1' });
    expect(resolveExportTarget(null, 'story-1', 'ext-1')).toEqual({
      user_story_id: 'story-1',
      extraction_id: 'ext-1',
    });
    // A version without its story is the API's 422; the resolver never emits it.
    expect(resolveExportTarget('project-1', null, 'ext-1')).toEqual({ project_id: 'project-1' });
    expect(resolveExportTarget(null, null, 'ext-1')).toEqual({});
    expect(resolveExportTarget(null, null, null)).toEqual({});
  });
});

describe('ExportPanel — the four formats', () => {
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
      size: 100,
    });
    vi.mocked(listVersions).mockResolvedValue([makeVersion()]);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => httpResponse('[]')),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('offers CSV, JSON, Markdown and Trello, in that order', async () => {
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    const csv = screen.getByRole('button', { name: 'CSV' });
    const json = screen.getByRole('button', { name: 'JSON' });
    const markdown = screen.getByRole('button', { name: 'Markdown' });
    const trello = screen.getByRole('button', { name: 'Trello' });

    // Document order, not list membership: the selector presents the four
    // formats in the order the product serves them.
    const following = Node.DOCUMENT_POSITION_FOLLOWING;
    expect(csv.compareDocumentPosition(json) & following).toBeTruthy();
    expect(json.compareDocumentPosition(markdown) & following).toBeTruthy();
    expect(markdown.compareDocumentPosition(trello) & following).toBeTruthy();
  });
});

describe('ExportPanel — the preview', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

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
      size: 100,
    });
    vi.mocked(listVersions).mockResolvedValue([makeVersion()]);
    fetchMock = stubFetch([
      {
        match: (url) => FILE_EXPORT_URL.test(url),
        respond: () => httpResponse('[{"title":"task from the server"}]'),
      },
    ]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function pick(label: string, optionLabel: string) {
    const user = userEvent.setup();
    await user.click(await screen.findByRole('combobox', { name: label }));
    await user.click(await screen.findByRole('option', { name: optionLabel }));
    return user;
  }

  it('fetches the file body with preview=true for the current selection and shows it', async () => {
    render(<ExportPanel locale="en" />);

    // The mount preview is the whole workspace, in the default format.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0][0])).toContain('format=json&preview=true');
    expect(await screen.findByTestId('export-preview')).toHaveTextContent(
      '[{"title":"task from the server"}]',
    );

    // Narrowing the selection re-reads the preview for the narrowed scope.
    await pick(t.exportPage.scope_project_label, PROJECT_ROW);
    await waitFor(() => {
      expect(String(fetchMock.mock.calls.at(-1)![0])).toContain('project_id=project-1');
    });
    expect(String(fetchMock.mock.calls.at(-1)![0])).toContain('preview=true');
  });

  it('changes what it fetches with the format', async () => {
    const user = userEvent.setup();
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await user.click(screen.getByRole('button', { name: 'CSV' }));
    await waitFor(() => {
      expect(String(fetchMock.mock.calls.at(-1)![0])).toContain('format=csv&preview=true');
    });
  });

  it('renders the Trello plan as JSON from the preview endpoint, without creating a job', async () => {
    const user = userEvent.setup();
    vi.mocked(previewTrelloExport).mockResolvedValue({
      name: 'Test Workspace',
      columns: [
        {
          name: 'Backlog',
          cards: [{ title: 'task one', description: '', labels: ['backend'], dependencyTitles: [] }],
        },
      ],
    });
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await user.click(screen.getByRole('button', { name: 'Trello' }));

    expect(await screen.findByTestId('export-preview')).toHaveTextContent('Test Workspace');
    expect(screen.getByTestId('export-preview')).toHaveTextContent('task one');
    await waitFor(() => expect(previewTrelloExport).toHaveBeenCalledTimes(1));
    expect(vi.mocked(previewTrelloExport).mock.calls[0][1]).toEqual({});
    // The preview describes the export; it must not perform it.
    expect(triggerTrelloExport).not.toHaveBeenCalled();
  });

  it('shows the Trello preview for the narrowed selection, version included', async () => {
    const user = userEvent.setup();
    vi.mocked(previewTrelloExport).mockResolvedValue({ name: 'Test Workspace', columns: [] });
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await pick(t.exportPage.scope_project_label, PROJECT_ROW);
    await pick(t.exportPage.scope_story_label, STORY_ROW);
    await pick(t.exportPage.scope_version_label, CURRENT_VERSION_ROW);
    await user.click(screen.getByRole('button', { name: 'Trello' }));

    await waitFor(() => expect(previewTrelloExport).toHaveBeenCalled());
    expect(vi.mocked(previewTrelloExport).mock.calls.at(-1)?.[1]).toEqual({
      user_story_id: 'story-1',
      extraction_id: 'ext-1',
    });
  });

  it('is read-only: the preview is a pre block, not an editor', async () => {
    render(<ExportPanel locale="en" />);

    const preview = await screen.findByTestId('export-preview');
    // E2: the text is shown and copied, never submitted back.
    expect(preview.tagName).toBe('PRE');
    expect(preview).not.toHaveAttribute('contenteditable');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('textarea')).not.toBeInTheDocument();
  });

  it('copies the preview to the clipboard', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    render(<ExportPanel locale="en" />);

    await user.click(await screen.findByRole('button', { name: t.exportPage.copy }));

    expect(writeText).toHaveBeenCalledWith('[{"title":"task from the server"}]');
  });

  it('answers a failed preview with its translated code', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (TRELLO_PREVIEW_URL.test(url) || FILE_EXPORT_URL.test(url)) {
        return httpResponse(
          JSON.stringify({ detail: 'boom', error_code: 'UNSUPPORTED_EXPORT_FORMAT' }),
          { status: 400 },
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    const user = userEvent.setup();
    render(<ExportPanel locale="en" />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(en.errorCodes.UNSUPPORTED_EXPORT_FORMAT);
  });
});

describe('ExportPanel — the download and its failures', () => {
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
      size: 100,
    });
    vi.mocked(listVersions).mockResolvedValue([makeVersion()]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('saves the file the server names', async () => {
    const user = userEvent.setup();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        httpResponse('id,title', {
          headers: { 'Content-Disposition': 'attachment; filename="tasks.csv"' },
        }),
      ),
    );
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await user.click(screen.getByRole('button', { name: 'CSV' }));
    await user.click(screen.getByRole('button', { name: t.exportPage.download }));

    await waitFor(() => expect(anchorClick).toHaveBeenCalled());
    anchorClick.mockRestore();
  });

  it('answers a refused download with the translated code, not raw prose', async () => {
    const user = userEvent.setup();
    // The mount preview (with `preview=true`) still succeeds; only the download
    // request — the same endpoint without the preview parameter — is refused.
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('preview=true')) return httpResponse('[]');
        return httpResponse(
          JSON.stringify({
            detail: 'Unsupported format',
            error_code: 'UNSUPPORTED_EXPORT_FORMAT',
          }),
          { status: 400 },
        );
      }),
    );
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await user.click(screen.getByRole('button', { name: t.exportPage.download }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(en.errorCodes.UNSUPPORTED_EXPORT_FORMAT);
  });
});

describe('ExportPanel — Trello export', () => {
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
      size: 100,
    });
    vi.mocked(listVersions).mockResolvedValue([makeVersion()]);
    vi.mocked(previewTrelloExport).mockResolvedValue({ name: 'Test Workspace', columns: [] });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => httpResponse('[]')),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

  /** Render the panel and wait for the first preview read to settle. */
  async function renderPanel() {
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');
  }

  it('states the new-board limitation where the trigger button is (D3)', async () => {
    const user = userEvent.setup();
    await renderPanel();
    await user.click(screen.getByRole('button', { name: 'Trello' }));

    const note = screen.getByText(t.exportPage.trello_new_board_note);
    // The note sits where the button is: the same section, not a distant footnote.
    expect(note.closest('section')).toContainElement(
      screen.getByRole('button', { name: t.exportPage.trello_trigger }),
    );
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
    await renderPanel();
    await user.click(screen.getByRole('button', { name: 'Trello' }));

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
    await renderPanel();
    await user.click(screen.getByRole('button', { name: 'Trello' }));

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
    await renderPanel();
    await user.click(screen.getByRole('button', { name: 'Trello' }));

    await user.click(screen.getByRole('button', { name: t.exportPage.trello_trigger }));

    expect(
      await screen.findByRole('link', { name: t.exportPage.trello_board_link }),
    ).toHaveAttribute('href', 'https://trello.com/b/abc/test-workspace');
    expect(screen.getByText('7 cards created.')).toBeInTheDocument();
  });

  it('runs the whole flow from inside the merged section: trigger → poll → board link', async () => {
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
      fireEvent.click(screen.getByRole('button', { name: 'Trello' }));
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

/* ── The selects read like the board's (EP6) ──
 *
 * The export page's cascade was built with plain labels — a bare project name,
 * a bare ``actor: feature`` — and never consumed the shared context treatments
 * the board's cascade renders through, so the same project read two different
 * ways on two pages. These cases pin the parity: the project rows carry the
 * kind's icon and the 12-character label with ``...``, the story rows carry
 * the fingerprint and the ``shortUUID · label`` shape, the triggers carry the
 * chip treatment with the full value in a real tooltip (none when nothing is
 * selected), and the version select stays plain like the board's — its only
 * gain is the `` · <current>`` mark on the current version.
 */
describe('ExportPanel — the selects read like the board\'s (EP6)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

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
      size: 100,
    });
    vi.mocked(listVersions).mockResolvedValue([makeVersion()]);
    vi.mocked(previewTrelloExport).mockResolvedValue({ name: 'Test Workspace', columns: [] });
    fetchMock = stubFetch([
      {
        match: (url) => FILE_EXPORT_URL.test(url),
        respond: () => httpResponse('[]'),
      },
    ]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

  it('gives the project rows the folder fallback, the shared 12-character label and the full name in our own tooltip', async () => {
    const user = userEvent.setup();
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await user.click(
      await screen.findByRole('combobox', { name: t.exportPage.scope_project_label }),
    );
    const option = await screen.findByRole('option', { name: PROJECT_ROW });
    // The kind's mark, drawn through the shared treatment's fallback — the same
    // one the board's rows draw for an icon-less project.
    expect(option.querySelector('.lucide-folder-kanban')).not.toBeNull();
    // The label is the shared cap's short text, not the full name: the same
    // project must not read two different ways on two pages.
    expect(option.textContent).toContain(PROJECT_ROW);
    expect(option.textContent).not.toContain(PROJECT_FULL_NAME);
    // The row's hover is our tooltip, never a native `title`, and the option
    // *is* the tooltip's trigger — a wrapper span inside it swallowed the
    // click and the row stopped selecting, the board's load-bearing subtlety.
    expect(option).not.toHaveAttribute('title');
    expect(option).toHaveAttribute('data-base-ui-tooltip-trigger');
    await user.hover(option);
    expect(await screen.findByText(PROJECT_FULL_NAME)).toBeInTheDocument();
  });

  it('carries the project\'s own icon onto its row — the fallback is only for an icon-less project', async () => {
    const user = userEvent.setup();
    useProjectStore.setState({ projects: [{ ...makeProject(), icon: 'rocket' }] });
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await user.click(
      await screen.findByRole('combobox', { name: t.exportPage.scope_project_label }),
    );
    const option = await screen.findByRole('option', { name: PROJECT_ROW });
    expect(option.querySelector('.lucide-rocket')).not.toBeNull();
    expect(option.querySelector('.lucide-folder-kanban')).toBeNull();
  });

  it('gives the story rows the fingerprint, the short id · shortened label shape and the sentence in our own tooltip', async () => {
    const user = userEvent.setup();
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await pick(user, t.exportPage.scope_project_label, PROJECT_ROW);
    await user.click(await screen.findByRole('combobox', { name: t.exportPage.scope_story_label }));
    const option = await screen.findByRole('option', { name: STORY_ROW });
    // The fingerprint, the id (which `shortUUID` passes through — `story-1` is
    // not a uuid) and the human label cut at the shared cap, in that order.
    expect(option.querySelector('.lucide-fingerprint')).not.toBeNull();
    expect(option.textContent).toContain('story-1');
    expect(option.textContent).toContain('user: to log...');
    expect(option).not.toHaveAttribute('title');
    expect(option).toHaveAttribute('data-base-ui-tooltip-trigger');
    await user.hover(option);
    expect(await screen.findByText(STORY_SENTENCE)).toBeInTheDocument();
  });

  it('gives the triggers the kind\'s icon and a tooltip with the selected value\'s full text — none when nothing is selected', async () => {
    const user = userEvent.setup();
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    // With nothing selected the tooltip is disabled, so no empty popup mounts.
    const projectTrigger = await screen.findByRole('combobox', {
      name: t.exportPage.scope_project_label,
    });
    await user.hover(projectTrigger);
    expect(screen.queryByText(PROJECT_FULL_NAME)).not.toBeInTheDocument();
    expect(document.querySelector('[data-slot="tooltip-content"]')).toBeNull();

    // Once a project is chosen, the trigger reads like a chip: the kind's icon
    // and a tooltip carrying the full name.
    await pick(user, t.exportPage.scope_project_label, PROJECT_ROW);
    const chosenProjectTrigger = screen.getByRole('combobox', {
      name: t.exportPage.scope_project_label,
    });
    expect(chosenProjectTrigger.querySelector('.lucide-folder-kanban')).not.toBeNull();
    await user.hover(chosenProjectTrigger);
    expect(await screen.findByText(PROJECT_FULL_NAME)).toBeInTheDocument();

    // …and the story trigger's is the full sentence, once a story is chosen.
    await pick(user, t.exportPage.scope_story_label, STORY_ROW);
    const storyTrigger = screen.getByRole('combobox', {
      name: t.exportPage.scope_story_label,
    });
    expect(storyTrigger.querySelector('.lucide-fingerprint')).not.toBeNull();
    await user.hover(storyTrigger);
    expect(await screen.findByText(STORY_SENTENCE)).toBeInTheDocument();
  });

  it('leaves the version rows plain — no icon, no tooltip — and marks the current one', async () => {
    const user = userEvent.setup();
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion('ext-1', 2),
      { ...makeVersion('ext-0', 1), isCurrent: false },
    ]);
    render(<ExportPanel locale="en" />);
    await screen.findByTestId('export-preview');

    await pick(user, t.exportPage.scope_project_label, PROJECT_ROW);
    await pick(user, t.exportPage.scope_story_label, STORY_ROW);
    await user.click(
      await screen.findByRole('combobox', { name: t.exportPage.scope_version_label }),
    );

    // The missing half of the parity: the current version carries the mark,
    // with the same word the board prints (`versionSelector.current`).
    const current = await screen.findByRole('option', { name: CURRENT_VERSION_ROW });
    const plain = screen.getByRole('option', { name: 'v1' });
    for (const option of [current, plain]) {
      // Plain, exactly like the board's version rows: no icon and no tooltip.
      expect(option.querySelector('svg')).toBeNull();
      expect(option).not.toHaveAttribute('data-base-ui-tooltip-trigger');
    }
  });
});

/* The state the server and the first paint are actually in, and the one nothing
 * else in this file renders: the workspace store has not resolved yet. The "no
 * workspace" early return used to sit above the option memos, so this transition
 * — undefined, then defined — ran more hooks than the first render and React
 * threw "Rendered more hooks than during the previous render". The island
 * unmounted and the page showed nothing, in production, while 941 tests, `tsc`,
 * `astro build` and CI all passed on a component that rendered nothing. This is
 * the test that fails instead of passing along. */
describe('ExportPanel — the workspace arrives after the first render', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the empty state and then the panel without changing the hook order', async () => {
    useWorkspaceStore.setState({
      workspaces: [],
      currentWorkspace: null,
      loading: true,
      saving: false,
    });
    useProjectStore.setState({
      projects: [],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(listStories).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 50,
      totalPages: 0,
    } as never);
    vi.mocked(listVersions).mockResolvedValue([]);
    stubFetch([
      jsonRoute(FILE_EXPORT_URL, []),
      jsonRoute(TRELLO_PREVIEW_URL, { name: 'Board', columns: [] }),
    ]);

    render(<ExportPanel locale="en" />);
    expect(screen.getByText(en.exportPage.no_workspace)).toBeTruthy();

    // The store resolves, which is what production does a moment after paint.
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
        loading: false,
      });
    });

    await waitFor(() => expect(screen.getByText(en.exportPage.title)).toBeTruthy());
  });
});
