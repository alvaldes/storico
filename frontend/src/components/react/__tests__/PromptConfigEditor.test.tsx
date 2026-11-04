import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PromptConfigEditor } from '@/components/react/PromptConfigEditor';
import { getPrompts, upsertPrompts } from '@/lib/prompts-api';
import { toast } from 'sonner';

vi.mock('@/lib/prompts-api', () => ({
  getPrompts: vi.fn(),
  upsertPrompts: vi.fn(),
}));

// The toast is part of the contract under test — a failed save has to *tell* the
// user, not only flip a button icon — so it is mocked to be assertable rather than
// rendered.
vi.mock('sonner', () => ({
  toast: { loading: vi.fn(() => 'toast-id'), success: vi.fn(), error: vi.fn() },
}));

const WORKSPACE_ID = 'ws-1';
const SWITCH_NAME = 'Automatic few-shot examples';

/**
 * These tests moved here from `LLMConfigEditor.test.tsx` when the prompts section
 * left the LLM card and became the Prompts tab (S11/T10): the assertions are the
 * ones the merged card had, pointed at the extracted component. `FewShotConfigEditor`
 * reports a generic `{ enabled, limit, threshold }` payload while the persisted row
 * speaks `fewShot*`, and these tests pin the round-trip across that boundary: the
 * switch has to read back the value it just wrote, and the save payload has to carry
 * the new value rather than the loaded one.
 *
 * Testing the child alone cannot catch a mapping regression — its own unit tests
 * assert the payload it emits, which was never wrong.
 */
describe('PromptConfigEditor few-shot wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(getPrompts).mockResolvedValue({
      systemPrompt: 'You are an expert software development lead.',
      instructionTemplate: 'Break this user story into smaller development tasks.',
      fewShotEnabled: true,
      fewShotLimit: 3,
      fewShotThreshold: 0.85,
    });
    vi.mocked(upsertPrompts).mockResolvedValue({});
  });

  async function renderEditor() {
    render(<PromptConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    // The editor renders a loading placeholder until the request settles.
    return screen.findByRole('switch', { name: SWITCH_NAME });
  }

  it('reads back the value it wrote when the enabled switch is toggled off', async () => {
    const user = userEvent.setup();
    const control = await renderEditor();
    expect(control).toHaveAttribute('aria-checked', 'true');

    await user.click(control);

    await waitFor(() =>
      expect(screen.getByRole('switch', { name: SWITCH_NAME })).toHaveAttribute(
        'aria-checked',
        'false',
      ),
    );
  });

  it('toggles back on from off', async () => {
    const user = userEvent.setup();
    const control = await renderEditor();

    await user.click(control);
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: SWITCH_NAME })).toHaveAttribute(
        'aria-checked',
        'false',
      ),
    );

    await user.click(screen.getByRole('switch', { name: SWITCH_NAME }));

    await waitFor(() =>
      expect(screen.getByRole('switch', { name: SWITCH_NAME })).toHaveAttribute(
        'aria-checked',
        'true',
      ),
    );
  });

  it('saves the toggled value, not the loaded one', async () => {
    const user = userEvent.setup();
    const control = await renderEditor();

    await user.click(control);
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: SWITCH_NAME })).toHaveAttribute(
        'aria-checked',
        'false',
      ),
    );

    await user.click(screen.getByRole('button', { name: 'Save Prompt Configuration' }));

    await waitFor(() =>
      expect(upsertPrompts).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ fewShotEnabled: false }),
      ),
    );
  });

  it('disables the limit and threshold controls while few-shot is off', async () => {
    const user = userEvent.setup();
    const control = await renderEditor();

    await user.click(control);

    // The slider's label names the group wrapper; the range input it controls is
    // only reachable with `hidden: true` because jsdom cannot lay out the thumb.
    await waitFor(() =>
      expect(
        within(screen.getByRole('group', { name: 'Max examples' })).getByRole('slider', {
          hidden: true,
        }),
      ).toBeDisabled(),
    );
    // Both inputs are gated on the same flag, so they must agree with the switch.
    expect(control).toHaveAttribute('aria-checked', 'false');
  });
});

/**
 * The move to its own component gave the prompts section its own load, and this
 * file pins it: a saved row reaches its fields, a save sends the row it holds, and
 * a failed save says so through the toast — the same behaviour the merged card had,
 * now reachable from the Prompts tab.
 */
describe('PromptConfigEditor load and save', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(getPrompts).mockResolvedValue({
      systemPrompt: 'You are an expert software development lead.',
      instructionTemplate: 'Break this user story into smaller development tasks.',
      fewShotEnabled: true,
      fewShotLimit: 3,
      fewShotThreshold: 0.85,
    });
    vi.mocked(upsertPrompts).mockResolvedValue({});
  });

  it('loads the saved prompts into their fields', async () => {
    render(<PromptConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);

    const system = await screen.findByLabelText('System Prompt');
    await waitFor(() =>
      expect(system).toHaveValue('You are an expert software development lead.'),
    );
    expect(screen.getByLabelText('Instruction Template')).toHaveValue(
      'Break this user story into smaller development tasks.',
    );
  });

  it('sends the row it holds when saving', async () => {
    const user = userEvent.setup();
    render(<PromptConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('System Prompt');

    await user.type(screen.getByLabelText('System Prompt'), ' Tailored.');
    await user.click(screen.getByRole('button', { name: 'Save Prompt Configuration' }));

    await waitFor(() =>
      expect(upsertPrompts).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({
          systemPrompt: 'You are an expert software development lead. Tailored.',
          instructionTemplate: 'Break this user story into smaller development tasks.',
          fewShotEnabled: true,
          fewShotLimit: 3,
          fewShotThreshold: 0.85,
        }),
      ),
    );
    expect(toast.success).toHaveBeenCalledWith('Prompt configuration saved');
  });

  it('reports a failed save through the toast', async () => {
    const user = userEvent.setup();
    vi.mocked(upsertPrompts).mockRejectedValue(new Error('500 Server Error'));
    render(<PromptConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('System Prompt');

    await user.click(screen.getByRole('button', { name: 'Save Prompt Configuration' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('500 Server Error'));
  });
});
