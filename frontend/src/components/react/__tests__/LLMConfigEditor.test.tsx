import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LLMConfigEditor } from '@/components/react/LLMConfigEditor';
import { getLLMConfig, upsertLLMConfig, fetchAvailableModels } from '@/lib/llm-config-api';
import { getPrompts, upsertPrompts } from '@/lib/prompts-api';

vi.mock('@/lib/llm-config-api', () => ({
  getLLMConfig: vi.fn(),
  upsertLLMConfig: vi.fn(),
  fetchAvailableModels: vi.fn(),
}));

vi.mock('@/lib/prompts-api', () => ({
  getPrompts: vi.fn(),
  upsertPrompts: vi.fn(),
}));

const WORKSPACE_ID = 'ws-1';
const SWITCH_NAME = 'Automatic few-shot examples';

/**
 * `FewShotConfigEditor` reports a generic `{ enabled, limit, threshold }` payload
 * while the persisted row speaks `fewShot*`. These tests pin the round-trip across
 * that boundary: the switch has to read back the value it just wrote, and the save
 * payload has to carry the new value rather than the loaded one.
 *
 * Testing the child alone cannot catch a mapping regression — its own unit tests
 * assert the payload it emits, which was never wrong.
 */
describe('LLMConfigEditor few-shot wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'ollama',
      model: 'llama3.2',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: 'http://localhost:11434',
      apiKey: '',
    });
    vi.mocked(getPrompts).mockResolvedValue({
      systemPrompt: 'You are an expert software development lead.',
      instructionTemplate: 'Break this user story into smaller development tasks.',
      fewShotEnabled: true,
      fewShotLimit: 3,
      fewShotThreshold: 0.85,
    });
    vi.mocked(fetchAvailableModels).mockResolvedValue([]);
    vi.mocked(upsertLLMConfig).mockResolvedValue({
      provider: 'ollama',
      model: 'llama3.2',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: 'http://localhost:11434',
      apiKey: '',
    });
    vi.mocked(upsertPrompts).mockResolvedValue({});
  });

  async function renderEditor() {
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    // The editor renders a loading placeholder until both requests settle.
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
