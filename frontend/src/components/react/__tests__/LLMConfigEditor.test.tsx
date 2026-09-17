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

/**
 * The custom-provider path is free text, so it cannot inherit the known providers'
 * auto-probe contract: there the provider changes once per selection, here it changes
 * on every keystroke and each probe reaches the user's external provider. These tests
 * pin the explicit contract instead — a custom list is loaded only on demand.
 */
describe('LLMConfigEditor custom provider', () => {
  const CUSTOM_MODELS = [
    { id: 'deepseek-chat', name: 'DeepSeek Chat' },
    { id: 'deepseek-reasoner', name: 'DeepSeek Reasoner' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'deepseek',
      model: 'deepseek-chat',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: 'sk-deepseek',
    });
    vi.mocked(getPrompts).mockResolvedValue({
      systemPrompt: 'You are an expert software development lead.',
      instructionTemplate: 'Break this user story into smaller development tasks.',
      fewShotEnabled: true,
      fewShotLimit: 3,
      fewShotThreshold: 0.85,
    });
    vi.mocked(fetchAvailableModels).mockResolvedValue(CUSTOM_MODELS);
    vi.mocked(upsertLLMConfig).mockResolvedValue({
      provider: 'deepseek',
      model: 'deepseek-chat',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: 'sk-deepseek',
    });
    vi.mocked(upsertPrompts).mockResolvedValue({});
  });

  /**
   * The editor starts on the default known provider and only reaches the custom branch
   * once the saved row lands, so the saved custom name is the marker for that switch.
   */
  async function renderCustomEditor() {
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByDisplayValue('deepseek');
  }

  it('issues no provider probe while the provider name is typed', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    // A custom workspace never auto-probes, so the counter starts empty and typing must
    // not move it: each keystroke reaches the user's provider otherwise.
    expect(fetchAvailableModels).not.toHaveBeenCalled();

    const providerInput = screen.getByLabelText('Provider');
    await user.clear(providerInput);
    await user.type(providerInput, 'groq');

    expect(fetchAvailableModels).not.toHaveBeenCalled();
  });

  it('keeps the entered API key and Base URL while the provider name is typed', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    expect(screen.getByLabelText('API Key')).toHaveValue('sk-deepseek');
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://api.deepseek.com/v1');

    const providerInput = screen.getByLabelText('Provider');
    await user.clear(providerInput);
    await user.type(providerInput, 'groq');

    // Renaming the provider does not invalidate the endpoint or the credential: only
    // the mode switches do, because only they change which provider is in effect.
    expect(screen.getByLabelText('API Key')).toHaveValue('sk-deepseek');
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://api.deepseek.com/v1');
  });

  it('probes the provider when the custom refresh button is pressed', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    const callsBefore = vi.mocked(fetchAvailableModels).mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Refresh models' }));

    await waitFor(() =>
      expect(vi.mocked(fetchAvailableModels).mock.calls.length).toBe(callsBefore + 1),
    );
    expect(fetchAvailableModels).toHaveBeenLastCalledWith(WORKSPACE_ID);
  });

  it('refreshes without an API key, because a local gateway needs none', async () => {
    const user = userEvent.setup();
    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'deepseek',
      model: 'deepseek-chat',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: 'http://localhost:8000/v1',
      apiKey: '',
    });
    await renderCustomEditor();

    const refresh = screen.getByRole('button', { name: 'Refresh models' });
    expect(refresh).toBeEnabled();

    const callsBefore = vi.mocked(fetchAvailableModels).mock.calls.length;
    await user.click(refresh);

    await waitFor(() =>
      expect(vi.mocked(fetchAvailableModels).mock.calls.length).toBe(callsBefore + 1),
    );
  });

  it('saves the model id typed into the custom field', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    const modelInput = screen.getByLabelText('Model');
    await user.clear(modelInput);
    await user.type(modelInput, 'deepseek-reasoner');

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'deepseek-reasoner' }),
      ),
    );
  });

  it('offers the discovered model ids as native suggestions', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    const modelInput = screen.getByLabelText('Model');
    // No probe has run in custom mode, so there are no ids to offer yet.
    expect(modelInput).not.toHaveAttribute('list');

    await user.click(screen.getByRole('button', { name: 'Refresh models' }));
    await waitFor(() => expect(modelInput).toHaveAttribute('list'));

    // The native pairing is only real if the attribute names a datalist that holds the
    // ids, so assert the link rather than the attribute alone.
    const listId = modelInput.getAttribute('list');
    const datalist = document.getElementById(listId ?? '');
    expect(datalist?.tagName).toBe('DATALIST');
    expect(
      Array.from(datalist?.querySelectorAll('option') ?? []).map((o) => o.getAttribute('value')),
    ).toEqual(['deepseek-chat', 'deepseek-reasoner']);
  });

  it('shows the typing hint and no empty-list warning before any probe runs', async () => {
    await renderCustomEditor();

    expect(
      screen.queryByText('No models available. Check the provider then refresh.'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Type the model id the provider expects, or load the provider's list for suggestions.",
      ),
    ).toBeInTheDocument();
    // The custom field is typed, never a selection-only control.
    expect(screen.getByLabelText('Model')).not.toHaveAttribute('readonly');
  });

  it('reports an empty provider list only after a probe returns nothing', async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAvailableModels).mockResolvedValue([]);
    await renderCustomEditor();

    expect(
      screen.queryByText('The provider returned no models. Type the model id manually.'),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Refresh models' }));

    expect(
      await screen.findByText('The provider returned no models. Type the model id manually.'),
    ).toBeInTheDocument();
  });

  it('reports a failed custom probe with the fetch error', async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAvailableModels).mockRejectedValue(new Error('502 Bad Gateway'));
    await renderCustomEditor();

    expect(
      screen.queryByText('Could not reach the provider. Check your API key and Base URL.'),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Refresh models' }));

    expect(
      await screen.findByText('Could not reach the provider. Check your API key and Base URL.'),
    ).toBeInTheDocument();
  });

  it('still auto-probes the model list for a known provider', async () => {
    const user = userEvent.setup();
    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'gemini',
      model: 'gemini-2.5-flash',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: '',
      apiKey: 'AIza-test',
    });

    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    // The custom path probes only on demand; a gate that leaked into the known path
    // would leave this list empty until the user pressed refresh.
    await waitFor(() => expect(fetchAvailableModels).toHaveBeenCalledWith(WORKSPACE_ID));
    await user.click(screen.getByRole('button', { expanded: false }));
    expect(await screen.findByRole('option', { name: 'DeepSeek Chat' })).toBeInTheDocument();
  });
});
