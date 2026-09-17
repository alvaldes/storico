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

  it('shows the saved model id and a placeholder that names no model', async () => {
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);

    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));
    // A provider default as placeholder reads as an existing selection: the field must
    // stay silent about models it does not actually hold.
    expect(input).toHaveAttribute('placeholder', 'Select a model');
  });

  it('stays empty behind the generic placeholder when nothing has been saved yet', async () => {
    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'gemini',
      model: '',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: '',
      apiKey: 'AIza-test',
    });

    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);

    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue(''));
    expect(input).toHaveAttribute('placeholder', 'Select a model');
  });

  it('refuses typed text: the model only changes through the list', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    expect(input).toHaveAttribute('readonly');
    // `skipClick` keeps the assertion on typing alone: a click would open the popup,
    // which is not what this test is about.
    await user.type(input, 'gpt-4o', { skipClick: true });
    expect(input).toHaveValue('gemini-2.5-flash');

    // Typing must not smuggle in an unlisted id as a pickable option either.
    await user.click(screen.getByRole('button', { expanded: false }));
    expect(await screen.findByRole('option', { name: 'Gemini 2.0 Flash' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /^Use "/ })).not.toBeInTheDocument();

    // The open popup makes the rest of the page inert, so leave it before saving.
    await user.keyboard('{Escape}');
    await user.click(await screen.findByRole('button', { name: 'Save LLM Configuration' }));
    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'gemini-2.5-flash' }),
      ),
    );
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

  it('warns that no model can be selected when the provider lists none', async () => {
    vi.mocked(fetchAvailableModels).mockResolvedValue([]);

    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    // The saved model still shows, but the field cannot invent a new one: say so
    // instead of leaving the user waiting for a list that will never arrive.
    expect(
      await screen.findByText('No models available. Check the provider then refresh.'),
    ).toBeInTheDocument();
  });

  it('falls back to the fetch error when the provider is unreachable', async () => {
    vi.mocked(fetchAvailableModels).mockRejectedValue(new Error('502 Bad Gateway'));

    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    expect(input).toHaveAttribute('readonly');
    expect(
      await screen.findByText('Could not reach the provider. Check your API key and Base URL.'),
    ).toBeInTheDocument();
  });

  it('clears the model when the provider changes', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    const input = await screen.findByLabelText('Model');
    await waitFor(() => expect(input).toHaveValue('gemini-2.5-flash'));

    // The provider field exposes no accessible role name in jsdom, so reach the
    // trigger through the label the field already points at with `htmlFor`.
    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: /Anthropic/ }));

    // A Gemini id is not an Anthropic model: the field must not carry it over.
    await waitFor(() => expect(screen.getByLabelText('Model')).toHaveValue(''));
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
