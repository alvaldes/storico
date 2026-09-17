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

describe('LLMConfigEditor model field', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'gemini',
      model: 'gemini-2.5-flash',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: '',
      apiKey: 'AIza-test',
    });
    vi.mocked(getPrompts).mockResolvedValue({
      systemPrompt: 'You are an expert software development lead.',
      instructionTemplate: 'Break this user story into smaller development tasks.',
      fewShotEnabled: true,
      fewShotLimit: 3,
      fewShotThreshold: 0.85,
    });
    vi.mocked(fetchAvailableModels).mockResolvedValue([
      { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
      { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash' },
    ]);
    vi.mocked(upsertLLMConfig).mockResolvedValue({
      provider: 'gemini',
      model: 'gemini-2.5-flash',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: '',
      apiKey: 'AIza-test',
    });
    vi.mocked(upsertPrompts).mockResolvedValue({});
  });

  it('shows the saved model id instead of the provider placeholder', async () => {
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);

    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));
    // The placeholder advertises the provider default; it must never read back as the value.
    expect(input).toHaveAttribute('placeholder', 'gemini-2.0-flash');
  });

  it('shows the saved model id even when the provider list does not include it', async () => {
    vi.mocked(fetchAvailableModels).mockResolvedValue([
      { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash' },
    ]);

    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);

    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));
  });

  it('saves the model picked from the list', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    await user.click(screen.getByRole('button', { expanded: false }));
    await user.click(await screen.findByRole('option', { name: 'Gemini 2.0 Flash' }));

    await waitFor(() => expect(input).toHaveValue('gemini-2.0-flash'));

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'gemini-2.0-flash' }),
      ),
    );
  });

  it('offers the typed model as a pickable option when no listed id matches it', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    await user.clear(input);
    await user.type(input, 'gemini-3-pro-preview');

    await user.click(await screen.findByRole('option', { name: 'Use "gemini-3-pro-preview"' }));
    await waitFor(() => expect(input).toHaveValue('gemini-3-pro-preview'));

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'gemini-3-pro-preview' }),
      ),
    );
  });

  it('does not offer the typed value when it already names a listed model', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    await user.clear(input);
    await user.type(input, 'gemini-2.0-flash');

    await waitFor(() =>
      expect(
        screen.queryByRole('option', { name: 'Use "gemini-2.0-flash"' }),
      ).not.toBeInTheDocument(),
    );
  });

  it('still lets you set a model when the provider list is unavailable', async () => {
    vi.mocked(fetchAvailableModels).mockRejectedValue(new Error('502 Bad Gateway'));

    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    await user.clear(input);
    await user.type(input, 'gemini-2.0-flash');
    await user.click(await screen.findByRole('option', { name: 'Use "gemini-2.0-flash"' }));

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'gemini-2.0-flash' }),
      ),
    );
  });

  it('stops offering the typed value once it has been selected', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    await user.clear(input);
    await user.type(input, 'gemini-3-pro-preview');
    await user.click(await screen.findByRole('option', { name: 'Use "gemini-3-pro-preview"' }));
    await waitFor(() => expect(input).toHaveValue('gemini-3-pro-preview'));

    // Reopening with the committed value must not show it as a candidate again.
    await user.click(screen.getByRole('button', { expanded: false }));
    await waitFor(() =>
      expect(
        screen.queryByRole('option', { name: 'Use "gemini-3-pro-preview"' }),
      ).not.toBeInTheDocument(),
    );
  });

  it('drops the typed candidate when the provider changes', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    await user.clear(input);
    await user.type(input, 'gemini-3-pro-preview');
    await screen.findByRole('option', { name: 'Use "gemini-3-pro-preview"' });

    // The provider field exposes no accessible role name in jsdom, so reach the
    // trigger through the label the field already points at with `htmlFor`.
    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: /Anthropic/ }));
    // The combobox remounts on provider change, so re-query instead of reusing `input`.
    await waitFor(() => expect(screen.getByLabelText('Model')).toHaveValue(''));

    // The candidate belonged to the previous provider's list; it must not resurface.
    await user.click(screen.getByRole('button', { expanded: false }));
    await waitFor(() =>
      expect(
        screen.queryByRole('option', { name: 'Use "gemini-3-pro-preview"' }),
      ).not.toBeInTheDocument(),
    );
  });

  it('warns when the saved model is missing from the provider list', async () => {
    vi.mocked(fetchAvailableModels).mockResolvedValue([
      { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash' },
    ]);

    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);

    expect(
      await screen.findByText("The saved model is not in the provider's model list."),
    ).toBeInTheDocument();
  });

  it('stays quiet when the saved model is in the provider list', async () => {
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    expect(
      screen.queryByText("The saved model is not in the provider's model list."),
    ).not.toBeInTheDocument();
  });

  it('saves the loaded model when the field is untouched', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'gemini-2.5-flash' }),
      ),
    );
  });
});
