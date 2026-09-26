import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ImportStoriesDialog, describeImportReason } from '@/components/react/ImportStoriesDialog';
import { useStoryStore } from '@/stores/storyStore';
import { ApiRequestError } from '@/lib/api';
import en from '@/i18n/en.json';

function makeFile(name = 'stories.csv'): File {
  return new File(['actor,feature,benefit'], name, { type: 'text/csv' });
}

let importStories: ReturnType<typeof vi.fn>;

function renderDialog(props: Partial<Parameters<typeof ImportStoriesDialog>[0]> = {}) {
  return render(
    <ImportStoriesDialog
      open
      onOpenChange={props.onOpenChange ?? vi.fn()}
      locale="en"
      projectId="project-a"
      workspaceId="ws-a"
      {...props}
    />,
  );
}

describe('ImportStoriesDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    importStories = vi.fn();
    useStoryStore.setState({
      importStories: importStories as unknown as ReturnType<
        typeof useStoryStore.getState
      >['importStories'],
    });
  });

  it('submits the selected file with the exact params and renders the summary', async () => {
    const user = userEvent.setup();
    const file = makeFile();
    importStories.mockResolvedValue({
      created: 3,
      skipped: 2,
      totalRows: 5,
      duplicates: [],
      storyIds: ['s1', 's2', 's3'],
    });

    renderDialog();
    const input = screen.getByLabelText('CSV file') as HTMLInputElement;
    await user.upload(input, file);
    await user.click(screen.getByRole('button', { name: 'Import' }));

    await waitFor(() => expect(importStories).toHaveBeenCalledTimes(1));
    // The store receives exactly what the dialog was given — no reshaping.
    expect(importStories).toHaveBeenCalledWith({
      workspaceId: 'ws-a',
      projectId: 'project-a',
      file,
    });
    expect(await screen.findByText('Import finished')).toBeInTheDocument();
    expect(screen.getByText('3 created, 2 skipped')).toBeInTheDocument();
  });

  it('renders import_result_none instead of a "0 created" line', async () => {
    const user = userEvent.setup();
    importStories.mockResolvedValue({
      created: 0,
      skipped: 4,
      totalRows: 4,
      duplicates: [],
      storyIds: [],
    });

    renderDialog();
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByText('Import finished')).toBeInTheDocument();
    expect(
      screen.getByText('Every line already exists in this project, so nothing was added.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/0 created/)).not.toBeInTheDocument();
    expect(screen.queryByText(/created,/)).not.toBeInTheDocument();
    // All-duplicates, not empty: the empty-file message must not appear.
    expect(screen.queryByText('The file has no rows to import.')).not.toBeInTheDocument();
  });

  it('tells the truth about an empty file instead of claiming every line already exists', async () => {
    const user = userEvent.setup();
    // A header-only file is a 201 with total_rows 0 — not a duplicate report.
    importStories.mockResolvedValue({
      created: 0,
      skipped: 0,
      totalRows: 0,
      duplicates: [],
      storyIds: [],
    });

    renderDialog();
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByText('The file has no rows to import.')).toBeInTheDocument();
    expect(
      screen.queryByText('Every line already exists in this project, so nothing was added.'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Import finished')).toBeInTheDocument();
  });

  it('scrolls the success report duplicates like the failure report does', async () => {
    const user = userEvent.setup();
    importStories.mockResolvedValue({
      created: 0,
      skipped: 2,
      totalRows: 2,
      duplicates: [
        { line: 2, reason: 'duplicate' },
        { line: 3, reason: 'duplicate' },
      ],
      storyIds: [],
    });

    renderDialog();
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByText('Import finished')).toBeInTheDocument();
    // jsdom has no layout, so assert on the scroll container's classes: the
    // duplicates list must sit inside the same max-h-64 overflow-y-auto
    // wrapper the row-failure report uses.
    const item = screen.getByText('Line 2').closest('li');
    expect(item).not.toBeNull();
    const scroller = item!.closest('ul')!.parentElement;
    expect(scroller).toHaveClass('max-h-64');
    expect(scroller).toHaveClass('overflow-y-auto');
  });

  it('disables submit without a project or workspace (defence: the UI never opens the dialog without both)', async () => {
    const user = userEvent.setup();
    renderDialog({ projectId: '', workspaceId: '' });
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());

    const submit = screen.getByRole('button', { name: 'Import' });
    expect(submit).toBeDisabled();
    // Even a programmatic submit must not reach the store.
    fireEvent.submit(submit.closest('form')!);
    expect(importStories).not.toHaveBeenCalled();
  });

  it('refuses a second submit dispatched in the same batch', async () => {
    const user = userEvent.setup();
    importStories.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () => resolve({ created: 1, skipped: 0, totalRows: 1, duplicates: [], storyIds: ['s1'] }),
            0,
          ),
        ),
    );

    renderDialog();
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    // Two submit events inside one batch: React has not flushed `running` yet,
    // so both handlers would observe `running === false` and both would fire —
    // only the run-token ref can refuse the second one.
    act(() => {
      const form = screen.getByRole('button', { name: 'Import' }).closest('form')!;
      fireEvent.submit(form);
      fireEvent.submit(form);
    });

    await waitFor(() => expect(screen.getByText('Import finished')).toBeInTheDocument());
    expect(importStories).toHaveBeenCalledTimes(1);
  });

  it('writes nothing when the dialog closes while the import is still in flight', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    let resolveImport!: (value: {
      created: number;
      skipped: number;
      totalRows: number;
      duplicates: never[];
      storyIds: string[];
    }) => void;
    importStories.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveImport = resolve;
        }),
    );

    const { rerender } = renderDialog({ onOpenChange });
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    await user.click(screen.getByRole('button', { name: 'Import' }));

    // In flight: the spinner is up and no report exists yet.
    expect(screen.getByText('Importing...')).toBeInTheDocument();
    expect(screen.queryByText('Import finished')).not.toBeInTheDocument();
    expect(importStories).toHaveBeenCalledTimes(1);

    // Close BEFORE the request settles, then reopen.
    rerender(
      <ImportStoriesDialog
        open={false}
        onOpenChange={onOpenChange}
        locale="en"
        projectId="project-a"
        workspaceId="ws-a"
      />,
    );
    rerender(
      <ImportStoriesDialog
        open
        onOpenChange={onOpenChange}
        locale="en"
        projectId="project-a"
        workspaceId="ws-a"
      />,
    );

    // The stale completion must write NOTHING: no report, no failure, no stuck
    // spinner — the dialog looks fresh, not like a report pasted over a run
    // that no longer belongs to it.
    await act(async () => {
      resolveImport({
        created: 3,
        skipped: 0,
        totalRows: 3,
        duplicates: [],
        storyIds: ['s1', 's2', 's3'],
      });
    });
    expect(screen.queryByText('Import finished')).not.toBeInTheDocument();
    expect(screen.queryByText('3 created, 0 skipped')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('Importing...')).not.toBeInTheDocument();
  });

  it('renders a rows failure with line numbers, reasons, duplicates, and the nothing-saved hint', async () => {
    const user = userEvent.setup();
    importStories.mockRejectedValue(
      new ApiRequestError(
        422,
        'Unprocessable Entity',
        {
          error_code: 'IMPORT_VALIDATION_FAILED',
          total_rows: 3,
          errors: [
            { line: 2, reason: 'missing_field', field: 'actor' },
            { line: 5, reason: 'unparsable_story' },
          ],
          duplicates: [{ line: 4, reason: 'duplicate' }],
        },
        { error_code: 'IMPORT_VALIDATION_FAILED' },
      ),
    );

    renderDialog();
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByText('The file has lines that must be fixed')).toBeInTheDocument();
    // The user must know nothing was saved.
    expect(
      screen.getByText('Nothing was imported. Fix these lines and upload the file again.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Line 2')).toBeInTheDocument();
    expect(screen.getByText('missing value for actor')).toBeInTheDocument();
    expect(screen.getByText('Line 5')).toBeInTheDocument();
    expect(screen.getByText('this line is not a user story')).toBeInTheDocument();
    expect(screen.getByText('Skipped lines')).toBeInTheDocument();
    expect(screen.getByText('Line 4')).toBeInTheDocument();
    expect(screen.getByText('already exists in this project')).toBeInTheDocument();
    // The success summary must not appear for a rejected import.
    expect(screen.queryByText('Import finished')).not.toBeInTheDocument();
  });

  it('renders a human-readable size for IMPORT_FILE_TOO_LARGE', async () => {
    const user = userEvent.setup();
    importStories.mockRejectedValue(
      new ApiRequestError(
        413,
        'Payload Too Large',
        {
          error_code: 'IMPORT_FILE_TOO_LARGE',
          size: 3145728,
          max: 2097152,
        },
        { error_code: 'IMPORT_FILE_TOO_LARGE' },
      ),
    );

    renderDialog();
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByText('The file is larger than 2 MB.')).toBeInTheDocument();
    expect(screen.queryByText(/2097152/)).not.toBeInTheDocument();
  });

  it('renders ErrorDisplay for an unexpected error instead of crashing', async () => {
    const user = userEvent.setup();
    importStories.mockRejectedValue(new Error('boom'));

    const { baseElement } = renderDialog();
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    await user.click(screen.getByRole('button', { name: 'Import' }));

    // The dialog portals its content, so query the document, not the container.
    await waitFor(() =>
      expect(baseElement.querySelector('[data-slot="error-display"]')).toBeInTheDocument(),
    );
    expect(screen.getByText('boom')).toBeInTheDocument();
    expect(screen.queryByText('Import finished')).not.toBeInTheDocument();
  });

  it('does not show the previous run report after closing and reopening', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    importStories.mockResolvedValue({
      created: 3,
      skipped: 0,
      totalRows: 3,
      duplicates: [],
      storyIds: ['s1', 's2', 's3'],
    });

    const { rerender } = renderDialog({ onOpenChange });
    await user.upload(screen.getByLabelText('CSV file') as HTMLInputElement, makeFile());
    await user.click(screen.getByRole('button', { name: 'Import' }));
    expect(await screen.findByText('Import finished')).toBeInTheDocument();

    rerender(
      <ImportStoriesDialog
        open={false}
        onOpenChange={onOpenChange}
        locale="en"
        projectId="project-a"
        workspaceId="ws-a"
      />,
    );
    rerender(
      <ImportStoriesDialog
        open
        onOpenChange={onOpenChange}
        locale="en"
        projectId="project-a"
        workspaceId="ws-a"
      />,
    );

    expect(screen.queryByText('Import finished')).not.toBeInTheDocument();
    expect(screen.queryByText('3 created, 0 skipped')).not.toBeInTheDocument();
  });
});

describe('describeImportReason', () => {
  it('maps every reason code that carries placeholders, using the real en translations', () => {
    expect(describeImportReason(en, { reason: 'missing_field', field: 'actor' })).toBe(
      'missing value for actor',
    );
    expect(describeImportReason(en, { reason: 'empty_field', field: 'feature' })).toBe(
      'empty value for feature',
    );
    expect(
      describeImportReason(en, { reason: 'too_long', field: 'actor', length: 150, max: 100 }),
    ).toBe('actor is too long (150 characters, maximum 100)');
    expect(describeImportReason(en, { reason: 'field_count_mismatch', observed: 4, expected: 3 })).toBe(
      'this line has 4 values but the file declares 3',
    );
    expect(describeImportReason(en, { reason: 'duplicate_in_file', firstLine: 7 })).toBe(
      'repeats line 7',
    );
    expect(describeImportReason(en, { reason: 'too_many_rows', max: 1000 })).toBe(
      'more than 1000 lines',
    );
    // The file-rejection payload for this reason carries no `max`; without it
    // the dialog must not print a substituted 0 ("more than 0 lines").
    expect(describeImportReason(en, { reason: 'too_many_rows' })).toBe(
      'the file has more lines than one import allows',
    );
    expect(describeImportReason(en, { reason: 'too_many_rows' })).not.toMatch(/\b0\b/);
  });

  it('falls back to import_reason_unknown for an unrecognised code', () => {
    expect(describeImportReason(en, { reason: 'some_future_code' })).toBe('unexpected problem');
  });
});
