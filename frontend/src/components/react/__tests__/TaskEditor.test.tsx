import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TaskEditor } from '@/components/react/TaskEditor';
import * as api from '@/lib/tasks-api';
import * as versioningApi from '@/lib/versioning-api';
import { ApiRequestError } from '@/lib/api';
import { useTaskStore } from '@/stores/taskStore';
import type { Task } from '@/types/task';

// Mock the api module — the store consumes these mocks.
vi.mock('@/lib/tasks-api', () => ({
  updateTask: vi.fn(),
}));

// The mark controls call the versioning client directly (W6-B1); every test
// states its own answer.
vi.mock('@/lib/versioning-api', () => ({
  listVersions: vi.fn(),
  createInvalidation: vi.fn(),
  listInvalidations: vi.fn(),
  revokeInvalidation: vi.fn(),
  fetchRepetition: vi.fn(),
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

// Sibling task in the same story — the only valid dependency target.
const siblingTask: Task = {
  id: 'task-0',
  storyId: 'story-1',
  title: 'Setup repo',
  description: 'Initialize the repository',
  status: 'done',
  priority: 'medium',
  labels: [],
  dependencies: [],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

describe('TaskEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: the D16 repetition read answers "no match". Tests that need a
    // match state their own answer.
    vi.mocked(versioningApi.fetchRepetition).mockResolvedValue({ matches: [] });
    useTaskStore.setState({
      tasks: { 'story-1': [siblingTask, mockTask] },
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
    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const labelInput = screen.getByPlaceholderText('Add a label and press Enter');
    await user.type(labelInput, '{Enter}');

    expect(screen.getByText('Label cannot be empty')).toBeInTheDocument();
  });

  it('rejects duplicate label (case-insensitive)', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const labelInput = screen.getByPlaceholderText('Add a label and press Enter');
    await user.type(labelInput, 'DB{Enter}');

    expect(screen.getByText('Label already exists')).toBeInTheDocument();
  });

  it('accepts a new unique label', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const labelInput = screen.getByPlaceholderText('Add a label and press Enter');
    await user.type(labelInput, 'api{Enter}');

    expect(screen.queryByText('Label already exists')).not.toBeInTheDocument();
    expect(screen.queryByText('Label cannot be empty')).not.toBeInTheDocument();
    expect(screen.getByText('api')).toBeInTheDocument();
  });

  /* ── Dependency validation ── */

  it('offers only sibling tasks from the same story as dependencies', async () => {
    render(
      <TaskEditor
        task={{ ...mockTask, dependencies: [] }}
        open={true}
        frozen={false}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');

    const depSelect = screen.getByLabelText('Dependencies') as HTMLSelectElement;
    const values = Array.from(depSelect.options).map((o) => o.value);

    // The sibling is offered by task.id...
    expect(values).toContain('task-0');
    // ...and the edited task is never offered as its own dependency.
    expect(values).not.toContain(mockTask.id);
  });

  it('adds a selected sibling dependency by task.id', async () => {
    const user = userEvent.setup();
    render(
      <TaskEditor
        task={{ ...mockTask, dependencies: [] }}
        open={true}
        frozen={false}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');

    await user.selectOptions(screen.getByLabelText('Dependencies'), 'task-0');

    // The chip renders the sibling's title, not its raw id.
    expect(screen.getByText('Setup repo')).toBeInTheDocument();
  });

  it('does not re-offer a sibling that is already a dependency', async () => {
    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />);

    await screen.findByText('Edit Task');

    const depSelect = screen.getByLabelText('Dependencies') as HTMLSelectElement;
    const values = Array.from(depSelect.options).map((o) => o.value);

    // task-0 is already a dependency of mockTask, so it is not re-offered.
    expect(values).not.toContain('task-0');
  });

  /* ── A story whose tasks were never loaded ── */

  it('renders when the story has no entry in the task slice', async () => {
    // The siblings selector used to end with `?? []`, which builds a NEW array on every call.
    // Zustand v5 subscribes through `useSyncExternalStore`, which compares snapshots with
    // `Object.is`, so an unstable snapshot makes React re-render forever: this render threw
    // "Maximum update depth exceeded" and the dialog never appeared.
    useTaskStore.setState({ tasks: {} });

    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />);

    expect(await screen.findByText('Edit Task')).toBeInTheDocument();
  });

  it('offers no dependency candidates when the story slice is empty', async () => {
    // The same missing slice, asserted on behaviour rather than on the absence of a crash:
    // with no siblings loaded there is nothing to depend on, so the select offers only its
    // placeholder.
    useTaskStore.setState({ tasks: {} });

    render(
      <TaskEditor
        task={{ ...mockTask, dependencies: [] }}
        open={true}
        frozen={false}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');

    const depSelect = screen.getByLabelText('Dependencies') as HTMLSelectElement;
    const values = Array.from(depSelect.options)
      .map((o) => o.value)
      .filter(Boolean);

    expect(values).toEqual([]);
  });

  /* ── i18n — validation messages must follow the dialog's locale ── */

  it('shows a localized validation error in Spanish, never the hardcoded English', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="es" />);

    await screen.findByText('Editar Tarea');

    // Recut for the D5/D21 matrix (T2b): the title is read-only text now, so
    // its required-error path is unreachable by design. The reachable local
    // validation path here is the empty label — the test's intent is
    // unchanged: the message follows the dialog's locale, the hardcoded
    // English never shows, and the store is never called.
    const labelInput = screen.getByPlaceholderText('Agrega una etiqueta y presiona Enter');
    await user.type(labelInput, '{Enter}');

    expect(screen.getByText('La etiqueta no puede estar vacía')).toBeInTheDocument();
    expect(screen.queryByText('Label cannot be empty')).not.toBeInTheDocument();
    // Local validation failed: the store must never be called.
    expect(api.updateTask).not.toHaveBeenCalled();
  });

  it('shows the localized invalid-transition error in Spanish with translated status names', async () => {
    const user = userEvent.setup();
    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="es" />);

    await screen.findByText('Editar Tarea');

    // The select disables invalid options, so the pointer cannot reach 'done'
    // from 'todo'; fireEvent bypasses that guard the way a stale client state
    // would, which is exactly the path this validation message exists for.
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'done' } });
    await user.click(screen.getByText('Guardar Cambios'));

    // The composed message uses the translated status names — no raw enum slugs.
    expect(screen.getByText('Transición inválida: Por Hacer → Terminado')).toBeInTheDocument();
    expect(
      screen.getByText('Transición inválida: Por Hacer → Terminado').textContent,
    ).not.toMatch(/\btodo\b|\bdone\b/);
    // Local validation failed: the store must never be called.
    expect(api.updateTask).not.toHaveBeenCalled();
  });

  /* ── Save / rollback ── */

  it('shows the localized save-failure banner and keeps the English backend detail reachable', async () => {
    const user = userEvent.setup();

    // Built exactly the way `lib/api.ts` `parseResponse` builds it: the English
    // backend `detail` becomes the error `message`, and the parsed response body
    // rides along as `rawBody` for the raw-detail channel. A plain `Error` would
    // exercise the wrap-unknown path instead of the backend-detail path.
    const backendBody = { detail: 'Not a member of this workspace' };
    vi.mocked(api.updateTask).mockRejectedValue(
      new ApiRequestError(403, 'Forbidden', 'Not a member of this workspace', backendBody),
    );

    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="es" />);

    await screen.findByText('Editar Tarea');

    await user.click(screen.getByText('Guardar Cambios'));

    // 1. The headline is the translated friendly message...
    expect(
      await screen.findByText('Error al guardar la tarea — intenta de nuevo'),
    ).toBeInTheDocument();
    // 2. ...not the server's English sentence, which must not be the visible
    // headline of a Spanish failure.
    expect(screen.queryByText('Not a member of this workspace')).not.toBeInTheDocument();

    // 3. Nothing is lost: the English backend sentence is still reachable
    // through the raw-detail disclosure, via its Spanish chrome label.
    await user.click(screen.getByText('Mostrar detalles del error del backend'));
    expect(screen.getByRole('region')).toHaveTextContent('Not a member of this workspace');
  });

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

    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={onOpenChange} locale="en" />);

    await screen.findByText('Edit Task');

    await user.click(screen.getByText('Save Changes'));

    // store.updateTask called exactly once with the narrowed D5/D21 payload:
    // the title and description are read-only text and never sent, and the
    // payload still carries the unchanged status — a no-op status is valid
    // under the current contract.
    expect(api.updateTask).toHaveBeenCalledTimes(1);
    expect(api.updateTask).toHaveBeenCalledWith('task-1', {
      labels: ['db', 'backend'],
      dependencies: ['task-0'],
      status: 'todo',
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

    render(<TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={onOpenChange} locale="en" />);

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
    const user = userEvent.setup();
    const firstRender = render(
      <TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />,
    );

    await screen.findByText('Edit Task');

    // The title is read-only under the D5/D21 matrix, so the editable state
    // this test observes is a label: type one in and see it appear.
    const labelInput = screen.getByPlaceholderText('Add a label and press Enter');
    await user.type(labelInput, 'api{Enter}');
    expect(screen.getByText('api')).toBeInTheDocument();

    // Rerender with a different task (simulating opening editor for another
    // task): unmount the first dialog so the assertion sees only the new one.
    const otherTask: Task = { ...mockTask, id: 'task-2', title: 'Other task' };
    firstRender.unmount();
    render(<TaskEditor task={otherTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />);

    // The form resets to the new task: the typed label is gone, and the new
    // task's title shows as the read-only text it now is.
    await waitFor(() => {
      expect(screen.queryByText('api')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Other task')).toBeInTheDocument();
  });

  /* ── WU2 field policy + frozen seam (tasks 2.6 / 2.9 — RED until T2b lands) ──
   *
   * design.md "the editor owns the field policy": `title` and `description`
   * render as read-only text (no input, no textarea), there is no `priority`
   * control at all (D21), and `dependencies` is disabled — and omitted from the
   * payload — while the new required `frozen` prop is true. `frozen` is passed
   * explicitly everywhere here so T2b cannot quietly default it away; the
   * WU3 seam (the page computing it from the selector's `is_current`) stays
   * visible at the call site.
   */

  describe('field policy and frozen seam', () => {
    it('renders title and description as read-only text, not editable controls', async () => {
      render(
        <TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />,
      );

      await screen.findByText('Edit Task');

      // No editable control answers to either field's label...
      expect(screen.queryByRole('textbox', { name: 'Title' })).not.toBeInTheDocument();
      expect(screen.queryByRole('textbox', { name: 'Description' })).not.toBeInTheDocument();
      // ...and the content itself stays visible as read-only text.
      expect(screen.getByText('DB schema')).toBeInTheDocument();
      expect(screen.getByText('Create the database schema')).toBeInTheDocument();
    });

    it('renders no priority control at all (D21)', async () => {
      render(
        <TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />,
      );

      await screen.findByText('Edit Task');

      expect(screen.queryByLabelText(/priority/i)).not.toBeInTheDocument();
    });

    it('disables the dependencies control while frozen', async () => {
      // A task that depends on nothing, so the select is ENABLED today via the
      // empty-candidates rule alone — the only way this turns green is the
      // frozen prop actually gating the control.
      const openTask = { ...mockTask, dependencies: [] };

      render(
        <TaskEditor task={openTask} open={true} frozen={true} onOpenChange={vi.fn()} locale="en" />,
      );

      await screen.findByText('Edit Task');

      const depSelect = screen.getByLabelText('Dependencies') as HTMLSelectElement;
      expect(depSelect).toBeDisabled();
    });

    it('omits the dependencies key from the save body while frozen', async () => {
      const user = userEvent.setup();
      vi.mocked(api.updateTask).mockResolvedValue(mockTask);

      render(
        <TaskEditor task={mockTask} open={true} frozen={true} onOpenChange={vi.fn()} locale="en" />,
      );

      await screen.findByText('Edit Task');
      await user.click(screen.getByText('Save Changes'));

      await waitFor(() => {
        expect(api.updateTask).toHaveBeenCalledTimes(1);
      });
      const [, payload] = vi.mocked(api.updateTask).mock.calls[0];
      // The payload cannot contain the key at all — not even as `[]` — so the
      // editor can never trigger TASK_VERSION_FROZEN.
      expect(payload).not.toHaveProperty('dependencies');
      expect(payload).toMatchObject({ status: 'todo', labels: ['db', 'backend'] });
    });

    it('sends exactly the contract keys on a current-version save (frozen false)', async () => {
      const user = userEvent.setup();
      vi.mocked(api.updateTask).mockResolvedValue(mockTask);

      render(
        <TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />,
      );

      await screen.findByText('Edit Task');
      await user.click(screen.getByText('Save Changes'));

      await waitFor(() => {
        expect(api.updateTask).toHaveBeenCalledTimes(1);
      });
      const [, payload] = vi.mocked(api.updateTask).mock.calls[0];
      // Exactly status, labels and dependencies — no title, description or priority.
      expect(Object.keys(payload as object).sort()).toEqual(['dependencies', 'labels', 'status']);
    });

    it('never blocks or warns on a status-only save of a frozen task', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      vi.mocked(api.updateTask).mockResolvedValue(mockTask);

      render(
        <TaskEditor
          task={mockTask}
          open={true}
          frozen={true}
          onOpenChange={onOpenChange}
          locale="en"
        />,
      );

      await screen.findByText('Edit Task');
      await user.click(screen.getByText('Save Changes'));

      // The save goes through without a dependencies write...
      await waitFor(() => {
        expect(api.updateTask).toHaveBeenCalledTimes(1);
      });
      const [, payload] = vi.mocked(api.updateTask).mock.calls[0];
      expect(payload).not.toHaveProperty('dependencies');
      // ...no failure banner is shown...
      expect(
        screen.queryByText('Failed to update task — please try again'),
      ).not.toBeInTheDocument();
      // ...and the dialog closes as on any successful save.
      await waitFor(() => {
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });
  });
});

/* ── Mark controls, confirmations and the D16 notice (0.9.0 slice b, W6-B1) ──
 *
 * The submission sequence is the contract: an empty reason blocks the save with
 * NO request; a mark or an unmark asks for confirmation whose cancel issues NO
 * request; the confirmed write goes first (POST create / DELETE revoke), then
 * the PUT; a failure rolls the optimistic update back and keeps the dialog open
 * with the user's edits intact. The D16 notice is a read-only warning whose one
 * action fills the textarea client-side and persists nothing.
 */
describe('TaskEditor — mark controls, confirmations and the D16 notice', () => {
  const activeMark = {
    id: 'mark-1',
    reason: 'Duplicates the login task from v1',
    markedBy: 'user-1',
    markedAt: '2026-10-02T10:00:00Z',
    revokedBy: null,
    revokedAt: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(versioningApi.fetchRepetition).mockResolvedValue({ matches: [] });
    useTaskStore.setState({
      tasks: { 'story-1': [siblingTask, mockTask] },
      workspaceTasks: [],
      extractions: {},
      loading: false,
      error: null,
      updatingTaskId: null,
    });
  });

  it('renders the Inválida checkbox, checked only when it starts marked or defaulted', async () => {
    // Default entry (the Edit pencil): unchecked, no reason field yet.
    const plain = render(
      <TaskEditor task={mockTask} open={true} frozen={false} onOpenChange={vi.fn()} locale="en" />,
    );
    await screen.findByText('Edit Task');
    const checkbox = screen.getByRole('checkbox', { name: 'Invalid' });
    expect(checkbox).not.toBeChecked();
    expect(screen.queryByLabelText('Reason')).not.toBeInTheDocument();
    plain.unmount();

    // The mark button's entry point: checkbox checked, reason field ready.
    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        markDefaultChecked={true}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );
    await screen.findByText('Edit Task');
    expect(screen.getByRole('checkbox', { name: 'Invalid' })).toBeChecked();
    expect(screen.getByLabelText('Reason')).toBeInTheDocument();
  });

  it('opens a marked task with the checkbox checked and the reason populated', async () => {
    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        activeMark={activeMark}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');

    expect(screen.getByRole('checkbox', { name: 'Invalid' })).toBeChecked();
    const reason = screen.getByLabelText('Reason') as HTMLTextAreaElement;
    expect(reason.value).toBe('Duplicates the login task from v1');
  });

  it('blocks the save with the missing-reason message and issues no request when the reason is empty', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        markDefaultChecked={true}
        onOpenChange={onOpenChange}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');
    await user.click(screen.getByText('Save Changes'));

    // The field is marked as missing...
    expect(screen.getByText('A reason is required to mark this task as invalid')).toBeInTheDocument();
    // ...no request of any kind was issued...
    expect(versioningApi.createInvalidation).not.toHaveBeenCalled();
    expect(api.updateTask).not.toHaveBeenCalled();
    // ...and the dialog stays open.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('persists the mark after the confirmation, then saves the task', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    vi.mocked(versioningApi.createInvalidation).mockResolvedValue(activeMark);
    vi.mocked(api.updateTask).mockResolvedValue(mockTask);

    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        markDefaultChecked={true}
        onOpenChange={onOpenChange}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');
    await user.type(screen.getByLabelText('Reason'), 'Duplicates the login task from v1');
    await user.click(screen.getByText('Save Changes'));

    // The confirmation names what the mark implies before anything is sent.
    const confirm = await screen.findByRole('alertdialog');
    expect(
      within(confirm).getByText((_, element) =>
        element?.textContent ===
        'The mark records your judgment: it will travel to the prompt of the next extraction, and it cannot be withdrawn once the version freezes.'
          ? true
          : false,
      ),
    ).toBeInTheDocument();

    await user.click(within(confirm).getByRole('button', { name: 'Mark as invalid' }));

    // Mark first, then the PUT, in that order, exactly once each.
    await waitFor(() => {
      expect(versioningApi.createInvalidation).toHaveBeenCalledTimes(1);
    });
    expect(versioningApi.createInvalidation).toHaveBeenCalledWith(
      'task-1',
      'Duplicates the login task from v1',
    );
    await waitFor(() => {
      expect(api.updateTask).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('revokes the mark after the confirmation when the checkbox is unchecked on a marked task', async () => {
    const user = userEvent.setup();
    vi.mocked(versioningApi.revokeInvalidation).mockResolvedValue(undefined);
    vi.mocked(api.updateTask).mockResolvedValue(mockTask);

    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        activeMark={activeMark}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');
    await user.click(screen.getByRole('checkbox', { name: 'Invalid' }));
    await user.click(screen.getByText('Save Changes'));

    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: 'Remove mark' }));

    await waitFor(() => {
      expect(versioningApi.revokeInvalidation).toHaveBeenCalledTimes(1);
    });
    expect(versioningApi.revokeInvalidation).toHaveBeenCalledWith('task-1');
    await waitFor(() => {
      expect(api.updateTask).toHaveBeenCalledTimes(1);
    });
  });

  it('cancelling the mark confirmation issues no request and keeps the editor open with the edits', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        markDefaultChecked={true}
        onOpenChange={onOpenChange}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');
    await user.type(screen.getByLabelText('Reason'), 'Duplicates the login task from v1');
    await user.click(screen.getByText('Save Changes'));

    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: 'Cancel' }));

    expect(versioningApi.createInvalidation).not.toHaveBeenCalled();
    expect(api.updateTask).not.toHaveBeenCalled();
    // The editor dialog is still open and the typed reason is intact.
    expect(screen.getByLabelText('Reason')).toHaveValue('Duplicates the login task from v1');
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('cancelling the unmark confirmation issues no request and keeps the mark active', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        activeMark={activeMark}
        onOpenChange={onOpenChange}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');
    await user.click(screen.getByRole('checkbox', { name: 'Invalid' }));
    await user.click(screen.getByText('Save Changes'));

    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: 'Cancel' }));

    expect(versioningApi.revokeInvalidation).not.toHaveBeenCalled();
    expect(api.updateTask).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('shows the D16 notice with the earlier version and reason, and copying it fills the field without persisting', async () => {
    const user = userEvent.setup();
    vi.mocked(versioningApi.fetchRepetition).mockResolvedValue({
      matches: [
        {
          versionNumber: 1,
          reason: 'Already covered by the auth refactor',
          markedAt: '2026-10-01T10:00:00Z',
        },
      ],
    });

    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        markDefaultChecked={true}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');

    // The notice is fetched when the mark controls render...
    expect(versioningApi.fetchRepetition).toHaveBeenCalledWith('task-1');
    // ...names the earlier version and its reason...
    expect(
      screen.getByText('You marked this task in v1: Already covered by the auth refactor'),
    ).toBeInTheDocument();

    // ...and its one action fills the textarea client-side, persisting nothing.
    await user.click(screen.getByRole('button', { name: 'Copy the reason' }));
    expect(screen.getByLabelText('Reason')).toHaveValue('Already covered by the auth refactor');
    expect(versioningApi.createInvalidation).not.toHaveBeenCalled();
    expect(api.updateTask).not.toHaveBeenCalled();
  });

  it('shows no repetition notice when the read reports no match (near-identical title)', async () => {
    // The backend matches normalized titles exactly, so a near-identical title
    // arrives as an empty match list — and the notice must not appear.
    vi.mocked(versioningApi.fetchRepetition).mockResolvedValue({ matches: [] });

    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        markDefaultChecked={true}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');

    expect(
      screen.queryByText(/You marked this task in v\d+/),
    ).not.toBeInTheDocument();
    // The mark controls themselves are still there.
    expect(screen.getByRole('checkbox', { name: 'Invalid' })).toBeChecked();
  });

  it('rolls back a failed save and keeps the dialog open with the edits intact', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    vi.mocked(versioningApi.createInvalidation).mockResolvedValue(activeMark);
    vi.mocked(api.updateTask).mockRejectedValue(new Error('Network error'));

    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={false}
        markDefaultChecked={true}
        onOpenChange={onOpenChange}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');
    await user.type(screen.getByLabelText('Reason'), 'Duplicates the login task from v1');
    // An edit that must survive the failure inside the open dialog.
    await user.type(screen.getByPlaceholderText('Add a label and press Enter'), 'api{Enter}');
    expect(screen.getByText('api')).toBeInTheDocument();

    await user.click(screen.getByText('Save Changes'));
    await user.click(await screen.findByRole('button', { name: 'Mark as invalid' }));

    // The PUT failed: the store rolled back to the original snapshot...
    await waitFor(() => {
      const stored = useTaskStore.getState().tasks['story-1']?.find((t) => t.id === 'task-1');
      expect(stored).toEqual(mockTask);
    });
    // ...the failure banner is shown...
    expect(
      await screen.findByText('Failed to update task — please try again'),
    ).toBeInTheDocument();
    // ...the dialog stays open with the user's unsaved edits intact...
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByText('api')).toBeInTheDocument();
    expect(screen.getByLabelText('Reason')).toHaveValue('Duplicates the login task from v1');
    // ...and the mark write itself did happen before the PUT (the sequence's order).
    expect(versioningApi.createInvalidation).toHaveBeenCalledTimes(1);
  });

  it('disables the Inválida checkbox while the version is frozen', async () => {
    render(
      <TaskEditor
        task={mockTask}
        open={true}
        frozen={true}
        onOpenChange={vi.fn()}
        locale="en"
      />,
    );

    await screen.findByText('Edit Task');

    expect(screen.getByRole('checkbox', { name: 'Invalid' })).toBeDisabled();
  });
});
