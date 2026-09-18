import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LLMConfigEditor } from '@/components/react/LLMConfigEditor';
import { getLLMConfig, upsertLLMConfig, fetchAvailableModels } from '@/lib/llm-config-api';
import { getPrompts, upsertPrompts } from '@/lib/prompts-api';
import {
  createCustomProvider,
  listCustomProviders,
  renameCustomProvider,
} from '@/lib/custom-providers-api';
import { ApiRequestError } from '@/lib/api';
import { toast } from 'sonner';
import type { CustomProvider, WorkspaceLLMConfig } from '@/types/workspace';

vi.mock('@/lib/llm-config-api', () => ({
  getLLMConfig: vi.fn(),
  upsertLLMConfig: vi.fn(),
  fetchAvailableModels: vi.fn(),
}));

vi.mock('@/lib/prompts-api', () => ({
  getPrompts: vi.fn(),
  upsertPrompts: vi.fn(),
}));

// Defaults to an empty registry: most tests here are about the known-provider path,
// which behaves identically whether or not the workspace has custom providers.
vi.mock('@/lib/custom-providers-api', () => ({
  listCustomProviders: vi.fn().mockResolvedValue([]),
  createCustomProvider: vi.fn(),
  renameCustomProvider: vi.fn(),
}));

// The toast is part of the contract under test — the save gate has to *tell* the user
// what is missing, not only refuse — so it is mocked to be assertable rather than
// rendered.
vi.mock('sonner', () => ({
  toast: { loading: vi.fn(() => 'toast-id'), success: vi.fn(), error: vi.fn() },
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

  it('probes the provider picked in the form, never the saved one', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await waitFor(() =>
      expect(fetchAvailableModels).toHaveBeenCalledWith(WORKSPACE_ID, {
        provider: 'gemini',
        baseUrl: '',
        apiKey: 'AIza-test',
      }),
    );

    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: 'Ollama (Local)' }));

    // Ollama needs no credential, so the probe runs and must describe Ollama while
    // carrying nothing that belonged to Gemini. Answering for the saved row here is the
    // reported bug: the select showed one provider and the endpoint answered for another.
    await waitFor(() =>
      expect(fetchAvailableModels).toHaveBeenLastCalledWith(WORKSPACE_ID, {
        provider: 'ollama',
        baseUrl: 'http://localhost:11434',
        apiKey: '',
      }),
    );
  });

  it('probes nothing for a cloud provider the form has no key for', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await waitFor(() => expect(fetchAvailableModels).toHaveBeenCalledTimes(1));

    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: 'Anthropic' }));

    // Switching clears the Gemini key, so there is nothing to ask Anthropic with. A
    // probe here would only send an empty credential and come back rejected.
    expect(fetchAvailableModels).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Refresh models' })).toBeDisabled();
  });

  it('drops the previous provider\u2019s list when the provider changes', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await waitFor(() =>
      expect(fetchAvailableModels).toHaveBeenCalledWith(WORKSPACE_ID, {
        provider: 'gemini',
        baseUrl: '',
        apiKey: 'AIza-test',
      }),
    );

    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: 'Anthropic' }));

    // A key makes the model field usable again. It must not bring Gemini's models back
    // with it: those were never Anthropic's, and offering them would invite the user to
    // save a model id this provider cannot serve.
    await user.type(screen.getByLabelText('API Key'), 'sk-ant-test');
    await user.click(screen.getByRole('button', { expanded: false }));

    expect(
      await screen.findByText('No models available. Check the provider then refresh.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Gemini 2.5 Flash' })).not.toBeInTheDocument();
  });

  it('re-probes after a successful save', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await waitFor(() => expect(fetchAvailableModels).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    // A saved config is the state a later visit loads, so the list the user sees now has
    // to be the one that config describes — not the pre-save answer.
    await waitFor(() => expect(fetchAvailableModels).toHaveBeenCalledTimes(2));
  });

  it('does not probe while the API key is being typed', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await waitFor(() => expect(fetchAvailableModels).toHaveBeenCalledTimes(1));

    await user.type(screen.getByLabelText('API Key'), 'added-chars');

    // One request per keystroke would reach the provider with a half-typed credential
    // and a partial key would only ever be rejected.
    expect(fetchAvailableModels).toHaveBeenCalledTimes(1);
  });

  it('does not probe while the Base URL is being typed', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await waitFor(() => expect(fetchAvailableModels).toHaveBeenCalledTimes(1));

    await user.type(screen.getByLabelText('Base URL'), 'https://proxy.internal/v1');

    // A partial URL names a host that does not exist yet, so the probe waits for the
    // refresh action instead of chasing every keystroke.
    expect(fetchAvailableModels).toHaveBeenCalledTimes(1);
  });

  it('never hands a cloud provider the Ollama endpoint', async () => {
    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'openai',
      model: 'gpt-4o-mini',
      temperature: 0.1,
      maxTokens: 2048,
      // The API answers a cloud provider with no configured endpoint as null, because
      // the Ollama host is Ollama's default and nobody else's.
      baseUrl: null,
      apiKey: 'sk-test',
    });

    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    // Filling the field with the Ollama host would point OpenAI's probe and its
    // extraction at a local Ollama instead of the provider's own default endpoint.
    await waitFor(() =>
      expect(fetchAvailableModels).toHaveBeenCalledWith(WORKSPACE_ID, {
        provider: 'openai',
        baseUrl: '',
        apiKey: 'sk-test',
      }),
    );
    expect(screen.getByLabelText('Base URL')).toHaveValue('');
  });
});

/**
 * The custom-provider path keeps its list on demand for the free-text fields — the
 * Base URL is typed there, and a probe per keystroke would reach the user's external
 * provider with a partial URL. The provider itself is chosen from the registry list, so
 * a saved custom endpoint with a Base URL is probed on load like any other provider.
 */
describe('LLMConfigEditor custom provider', () => {
  const CUSTOM_MODELS = [
    { id: 'deepseek-chat', name: 'DeepSeek Chat' },
    { id: 'deepseek-reasoner', name: 'DeepSeek Reasoner' },
  ];

  /** The registry row the saved config already names. */
  const REGISTERED: CustomProvider = {
    id: 'cp-deepseek',
    workspaceId: WORKSPACE_ID,
    name: 'deepseek',
    createdAt: '2026-09-18T10:00:00Z',
    updatedAt: '2026-09-18T10:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listCustomProviders).mockResolvedValue([REGISTERED]);

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

  it('renders every provider option with the same glyph the trigger shows', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    // The glyph of the provider this editor is on. The row that lists it must show the
    // same one, or the list disagrees with the field right above it. Read from the
    // trigger's own markup: the provider icons are a shared component, so this compares
    // the rendering rather than hard-coding a path that a redraw would change.
    const selectionGlyph = screen.getByLabelText('Provider').querySelector('svg')?.innerHTML;
    expect(selectionGlyph).toBeTruthy();

    await user.click(screen.getByLabelText('Provider'));
    await screen.findByRole('option', { name: 'Add custom provider' });

    // `div > svg` is the label row's icon: the check mark of the selection indicator
    // sits in a `<span>`, so it cannot satisfy this. Custom rows used to be the only
    // bare names in a list of icon+label rows, which is what pulled them out of the
    // component's alignment.
    for (const option of screen.getAllByRole('option')) {
      expect(option.querySelector('div > svg')).not.toBeNull();
    }
    expect(screen.getByRole('option', { name: 'deepseek' }).querySelector('div')?.innerHTML).toContain(
      selectionGlyph,
    );
  });

  it('never makes the provider field editable', async () => {
    await renderCustomEditor();

    // The field is selection-only: the labelled control is the combobox button, and no
    // text field answers to the same label.
    expect(screen.getByLabelText('Provider')).toHaveAttribute('role', 'combobox');
    expect(screen.queryByRole('textbox', { name: 'Provider' })).not.toBeInTheDocument();
  });

  it('probes a custom provider saved with a complete endpoint', async () => {
    await renderCustomEditor();

    // The probe carries the selection the form holds, so a custom workspace can be
    // answered for the provider it is actually saved against — which is the whole
    // reason the old saved-config-only endpoint made this path unusable.
    await waitFor(() =>
      expect(fetchAvailableModels).toHaveBeenCalledWith(WORKSPACE_ID, {
        provider: 'deepseek',
        baseUrl: 'https://api.deepseek.com/v1',
        apiKey: 'sk-deepseek',
      }),
    );
  });

  it('offers the rename action only for a custom provider', async () => {
    await renderCustomEditor();

    expect(screen.getByRole('button', { name: 'Rename custom provider' })).toBeInTheDocument();
  });

  it('opens the add dialog from the select without moving the selection', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: 'Add custom provider' }));

    // The add option is a control, not a value: the saved provider is still selected and
    // the dialog is what opened.
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Provider')).toHaveTextContent('deepseek');
    expect(screen.getByLabelText('Provider name')).toHaveValue('');
  });

  it('registers a provider, selects it, and clears the previous endpoint', async () => {
    const user = userEvent.setup();
    vi.mocked(createCustomProvider).mockResolvedValue({ ...REGISTERED, name: 'groq' });
    await renderCustomEditor();

    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: 'Add custom provider' }));
    await user.type(await screen.findByLabelText('Provider name'), 'groq');
    await user.click(screen.getByRole('button', { name: 'Add provider' }));

    await waitFor(() =>
      expect(createCustomProvider).toHaveBeenCalledWith(WORKSPACE_ID, {
        name: 'groq',
      }),
    );
    // The new provider is the selection, and the DeepSeek credential, endpoint and model
    // are not its values.
    await waitFor(() => expect(screen.getByLabelText('Provider')).toHaveTextContent('groq'));
    expect(screen.getByLabelText('API Key')).toHaveValue('');
    expect(screen.getByLabelText('Base URL')).toHaveValue('');
    expect(screen.getByLabelText('Model')).toHaveValue('');
  });

  it('renames the selected provider and keeps its endpoint and credential', async () => {
    const user = userEvent.setup();
    vi.mocked(renameCustomProvider).mockResolvedValue({ ...REGISTERED, name: 'groq' });
    await renderCustomEditor();

    expect(screen.getByLabelText('API Key')).toHaveValue('sk-deepseek');
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://api.deepseek.com/v1');

    await user.click(screen.getByRole('button', { name: 'Rename custom provider' }));
    const nameInput = await screen.findByLabelText('Provider name');
    // Pre-filled, so a rename starts from the name it is changing.
    expect(nameInput).toHaveValue('deepseek');
    await user.clear(nameInput);
    await user.type(nameInput, 'groq');
    await user.click(screen.getByRole('button', { name: 'Save name' }));

    await waitFor(() =>
      expect(renameCustomProvider).toHaveBeenCalledWith(WORKSPACE_ID, 'cp-deepseek', {
        name: 'groq',
      }),
    );
    // The selection follows the rename, and the endpoint and credential stay: only the
    // name changed.
    await waitFor(() => expect(screen.getByLabelText('Provider')).toHaveTextContent('groq'));
    expect(screen.getByLabelText('API Key')).toHaveValue('sk-deepseek');
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://api.deepseek.com/v1');
  });

  it('reports a duplicate name and keeps the dialog open', async () => {
    const user = userEvent.setup();
    vi.mocked(createCustomProvider).mockRejectedValue(
      new ApiRequestError(409, 'Conflict', 'already exists'),
    );
    await renderCustomEditor();

    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: 'Add custom provider' }));
    await user.type(await screen.findByLabelText('Provider name'), 'groq');
    await user.click(screen.getByRole('button', { name: 'Add provider' }));

    expect(
      await screen.findByText('A provider with this name already exists in this workspace.'),
    ).toBeInTheDocument();
    // Still open, with the name the user typed, so they can correct it.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Provider name')).toHaveValue('groq');
  });

  it('refuses a built-in provider name before sending it', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: 'Add custom provider' }));
    await user.type(await screen.findByLabelText('Provider name'), 'gemini');
    await user.click(screen.getByRole('button', { name: 'Add provider' }));

    expect(
      await screen.findByText('That name is a built-in provider. Choose a different name.'),
    ).toBeInTheDocument();
    expect(createCustomProvider).not.toHaveBeenCalled();
  });

  it('refuses the selector control value before sending it', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    await user.click(screen.getByLabelText('Provider'));
    await user.click(await screen.findByRole('option', { name: 'Add custom provider' }));
    await user.type(await screen.findByLabelText('Provider name'), '__add_custom_provider__');
    await user.click(screen.getByRole('button', { name: 'Add provider' }));

    // The value that opens this dialog is not a provider a workspace can register:
    // it would occupy the select's "Add custom provider…" slot and be unselectable.
    expect(
      await screen.findByText(
        'That name is reserved by the provider selector. Choose a different name.',
      ),
    ).toBeInTheDocument();
    expect(createCustomProvider).not.toHaveBeenCalled();
  });

  it('probes the provider when the custom refresh button is pressed', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    const callsBefore = vi.mocked(fetchAvailableModels).mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Refresh models' }));

    await waitFor(() =>
      expect(vi.mocked(fetchAvailableModels).mock.calls.length).toBe(callsBefore + 1),
    );
    // The refresh is the affordance for the free-text fields, so it must carry what
    // they hold right now rather than only what was saved.
    expect(fetchAvailableModels).toHaveBeenLastCalledWith(WORKSPACE_ID, {
      provider: 'deepseek',
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: 'sk-deepseek',
    });
  });

  it('sends a Base URL typed but not yet saved', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    const baseUrlInput = screen.getByLabelText('Base URL');
    await user.clear(baseUrlInput);
    await user.type(baseUrlInput, 'http://localhost:8000/v1');

    const callsBefore = vi.mocked(fetchAvailableModels).mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Refresh models' }));

    await waitFor(() =>
      expect(vi.mocked(fetchAvailableModels).mock.calls.length).toBe(callsBefore + 1),
    );
    expect(fetchAvailableModels).toHaveBeenLastCalledWith(WORKSPACE_ID, {
      provider: 'deepseek',
      baseUrl: 'http://localhost:8000/v1',
      apiKey: 'sk-deepseek',
    });
  });

  it('probes nothing while a custom provider has no Base URL to ask', async () => {
    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'deepseek',
      model: 'deepseek-chat',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: '',
      apiKey: 'sk-deepseek',
    });
    await renderCustomEditor();

    expect(fetchAvailableModels).not.toHaveBeenCalled();
    // An endpoint-less provider has nothing to ask, so the control that would ask must
    // say which field is missing instead of offering a request that cannot answer.
    expect(screen.getByRole('button', { name: 'Refresh models' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Refresh models' })).toHaveAttribute(
      'title',
      'Add the Base URL first',
    );
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
    // The button is disabled while any probe is in flight (`modelsLoading ||
    // !canProbe`), and `renderCustomEditor` only awaits the field value -- not the
    // auto-probe that value triggers. Asserting without waiting made this line
    // depend on scheduling, and it flaked on a loaded CI runner. What this test is
    // about is the empty key, so wait for the button to settle.
    await waitFor(() => expect(refresh).toBeEnabled());

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
    // Typing opens the catalogue, and an open catalogue makes the rest of the page
    // inert. Close it before reaching the save button.
    await user.keyboard('{Escape}');

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'deepseek-reasoner' }),
      ),
    );
  });

  it('renders the saved model as the field text behind a named chevron trigger', async () => {
    await renderCustomEditor();

    const modelInput = screen.getByLabelText('Model');
    await waitFor(() => expect(modelInput).toHaveValue('deepseek-chat'));

    // The field is typed text, and the chevron is the affordance that reveals the
    // provider's catalogue in one click — a plain text input offered no way to see one.
    expect(
      await screen.findByRole('button', { name: 'Discovered models (2)' }),
    ).toBeInTheDocument();
  });

  it('reveals every discovered model in one click, unfiltered by the saved value', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    await user.click(await screen.findByRole('button', { name: 'Discovered models (2)' }));

    // The field already holds `deepseek-chat`. A popup that filtered itself against that
    // text would list one entry and hide the rest, which is the complaint this replaces.
    //
    // Each entry's accessible name is asserted exactly: the id that gets saved followed by
    // the readable name. The fixtures deliberately pair a distinct id and name, so dropping
    // the name suffix, or rendering the name as the text that gets filled, both fail here.
    expect(
      await screen.findByRole('option', { name: 'deepseek-chat DeepSeek Chat' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('option', { name: 'deepseek-reasoner DeepSeek Reasoner' }),
    ).toBeInTheDocument();
  });

  it('reveals the catalogue by clicking the field itself', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    // `Autocomplete.Root` defaults `openOnInputClick` to `false`, which would make the
    // field look like a dead text box — the original complaint. A click in the text must
    // open the list, the way the known providers' model field and a plain select behave.
    await user.click(screen.getByLabelText('Model'));

    expect(await screen.findByRole('option', { name: /deepseek-reasoner/ })).toBeInTheDocument();
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
    vi.mocked(fetchAvailableModels).mockRejectedValue(new Error('502 Bad Gateway'));
    await renderCustomEditor();

    // The saved endpoint is complete, so the failure reaches the field without waiting
    // for a click: the auto-probe is the same request the refresh button makes.
    expect(
      await screen.findByText('Could not reach the provider. Check your API key and Base URL.'),
    ).toBeInTheDocument();
  });

  it('reports a failure from an explicit refresh', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();
    await waitFor(() => expect(fetchAvailableModels).toHaveBeenCalled());

    vi.mocked(fetchAvailableModels).mockRejectedValueOnce(new Error('502 Bad Gateway'));
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

    // The probe describes the provider the form holds, not whichever one happens to be
    // saved: that coupling is exactly what answered for the wrong provider.
    await waitFor(() =>
      expect(fetchAvailableModels).toHaveBeenCalledWith(WORKSPACE_ID, {
        provider: 'gemini',
        baseUrl: '',
        apiKey: 'AIza-test',
      }),
    );
    await user.click(screen.getByRole('button', { expanded: false }));
    expect(await screen.findByRole('option', { name: 'DeepSeek Chat' })).toBeInTheDocument();
  });

  it('writes the model id, not the displayed name, when an entry is chosen', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    await user.click(await screen.findByRole('button', { name: 'Discovered models (2)' }));
    await user.click(await screen.findByRole('option', { name: /deepseek-reasoner/ }));

    const modelInput = screen.getByLabelText('Model');
    // The entry renders the id followed by its readable name; the field must end up with
    // the id alone, because that is the value the provider is asked for.
    await waitFor(() => expect(modelInput).toHaveValue('deepseek-reasoner'));

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'deepseek-reasoner' }),
      ),
    );
  });

  it('keeps an id the provider never listed, even after blur', async () => {
    const user = userEvent.setup();
    await renderCustomEditor();

    const modelInput = screen.getByLabelText('Model');
    await user.clear(modelInput);
    await user.type(modelInput, 'totally-unlisted-model');
    // Typing opens the catalogue, and an open catalogue makes the rest of the page
    // inert. Close it before leaving the field so the save button stays reachable.
    await user.keyboard('{Escape}');
    await user.tab();

    // In an autocomplete the typed text *is* the value, so there is nothing to revert
    // to. The Combobox this replaces reverted exactly here.
    await waitFor(() => expect(modelInput).toHaveValue('totally-unlisted-model'));

    await user.click(screen.getByRole('button', { name: 'Save LLM Configuration' }));

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ model: 'totally-unlisted-model' }),
      ),
    );
  });

  it('keeps the field editable and names the empty list when nothing is discovered', async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAvailableModels).mockResolvedValue([]);
    await renderCustomEditor();
    await waitFor(() => expect(fetchAvailableModels).toHaveBeenCalled());

    const modelInput = screen.getByLabelText('Model');
    // An empty catalogue is not a dead end: the id stays typable, which is the whole
    // point of keeping this field free text.
    expect(modelInput).not.toHaveAttribute('readonly');

    await user.click(screen.getByRole('button', { name: 'Discovered models (0)' }));

    expect(
      await screen.findByText('The provider returned no models. Type the model id manually.'),
    ).toBeInTheDocument();
  });
});

/**
 * A first-class provider's name is not the workspace's to edit, so the rename action
 * belongs to the custom path alone.
 */
describe('LLMConfigEditor known provider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listCustomProviders).mockResolvedValue([]);
    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'gemini',
      model: 'gemini-2.5-flash',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: '',
      apiKey: 'AIza-test',
    });
    vi.mocked(getPrompts).mockResolvedValue({});
    vi.mocked(fetchAvailableModels).mockResolvedValue([]);
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

  it('offers no rename action', async () => {
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    expect(
      screen.queryByRole('button', { name: 'Rename custom provider' }),
    ).not.toBeInTheDocument();
  });

  it('lists the four known providers and the add option', async () => {
    const user = userEvent.setup();
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await user.click(screen.getByLabelText('Provider'));

    // Queried by accessible name: a provider icon that leaked its own title into the
    // option's name would fail here instead of passing on a looser text match.
    for (const label of ['Ollama (Local)', 'OpenAI', 'Anthropic', 'Gemini']) {
      expect(await screen.findByRole('option', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole('option', { name: 'Add custom provider' })).toBeInTheDocument();
  });

  it('lists the workspace providers alongside them', async () => {
    const user = userEvent.setup();
    vi.mocked(listCustomProviders).mockResolvedValue([
      {
        id: 'cp-1',
        workspaceId: WORKSPACE_ID,
        name: 'groq',
        createdAt: '2026-09-18T10:00:00Z',
        updatedAt: '2026-09-18T10:00:00Z',
      },
    ]);
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    await screen.findByLabelText('Model');

    await user.click(screen.getByLabelText('Provider'));

    for (const label of ['Ollama (Local)', 'OpenAI', 'Anthropic', 'Gemini', 'groq']) {
      expect(await screen.findByRole('option', { name: label })).toBeInTheDocument();
    }

    // Known providers first, then the workspace's own, then the add control.
    const options = await screen.findAllByRole('option');
    expect(options).toHaveLength(6);
    expect(
      within(options[options.length - 1]).getByText('Add custom provider'),
    ).toBeInTheDocument();

    // Selecting one makes it the workspace's provider without touching the registry.
    await user.click(screen.getByRole('option', { name: 'groq' }));
    await waitFor(() => expect(screen.getByLabelText('Provider')).toHaveTextContent('groq'));
    expect(createCustomProvider).not.toHaveBeenCalled();
    expect(renameCustomProvider).not.toHaveBeenCalled();
  });
});

/**
 * The save gate.
 *
 * An incomplete LLM configuration is the one state in which this product cannot do the
 * thing it exists to do, so the form refuses to persist it: the draft is parsed with the
 * same zod schema the readiness answer mirrors, each offending field gets a red message,
 * and the toast names what is still missing.
 */
describe('LLMConfigEditor save gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(getPrompts).mockResolvedValue({
      systemPrompt: 'You are an expert software development lead.',
      instructionTemplate: 'Break this user story into smaller development tasks.',
      fewShotEnabled: true,
      fewShotLimit: 3,
      fewShotThreshold: 0.85,
    });
    vi.mocked(fetchAvailableModels).mockResolvedValue([]);
    vi.mocked(upsertPrompts).mockResolvedValue({});
    vi.mocked(upsertLLMConfig).mockResolvedValue({
      provider: 'ollama',
      model: 'llama3.2',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: 'http://localhost:11434',
      apiKey: '',
    });
  });

  /** Render the editor with a stored configuration the caller chooses. */
  async function renderWith(config: Partial<WorkspaceLLMConfig> = {}) {
    vi.mocked(getLLMConfig).mockResolvedValue({
      provider: 'ollama',
      model: 'llama3.2',
      temperature: 0.1,
      maxTokens: 2048,
      baseUrl: 'http://localhost:11434',
      apiKey: '',
      ...config,
    });
    render(<LLMConfigEditor locale="en" workspaceId={WORKSPACE_ID} />);
    // The editor renders a loading placeholder until both requests settle.
    return screen.findByRole('button', { name: 'Save LLM Configuration' });
  }

  it('states what is missing before anything is attempted', async () => {
    await renderWith({ provider: 'openai', model: '', apiKey: '' });

    const summary = await screen.findByRole('alert');
    expect(
      within(summary).getByText('This workspace cannot extract tasks yet'),
    ).toBeInTheDocument();
    expect(within(summary).getByText('Model')).toBeInTheDocument();
    expect(within(summary).getByText('API Key')).toBeInTheDocument();
    expect(
      within(summary).getByText('Complete these fields to enable extraction:'),
    ).toBeInTheDocument();

    // The summary explains the state without painting every empty field of a fresh
    // workspace red; the per-field messages come from a refused save.
    expect(screen.queryByText('This field is required.')).not.toBeInTheDocument();
  });

  it('refuses to save an incomplete draft and names the gaps in a toast', async () => {
    const user = userEvent.setup();
    const save = await renderWith({ provider: 'openai', model: '', apiKey: '' });

    await user.click(save);

    expect(upsertLLMConfig).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      'The LLM configuration is not complete',
      expect.objectContaining({
        description: 'Extraction stays disabled until you complete these fields: Model, API Key',
      }),
    );
  });

  it('puts a red message under each field that is missing', async () => {
    const user = userEvent.setup();
    const save = await renderWith({ provider: 'openai', model: '', apiKey: '' });

    await user.click(save);

    // One per gap, so the count itself is the assertion that nothing else was flagged.
    expect(await screen.findAllByText('This field is required.')).toHaveLength(2);
  });

  it('clears the red message once the missing value is provided', async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAvailableModels).mockResolvedValue([
      { id: 'llama3.2', name: 'llama3.2' },
    ]);
    const save = await renderWith({ provider: 'ollama', model: '' });

    await user.click(save);
    expect(await screen.findAllByText('This field is required.')).toHaveLength(1);

    await user.click(screen.getByRole('button', { expanded: false }));
    await user.click(await screen.findByRole('option', { name: 'llama3.2' }));

    // Live, not cleared by the next save: the message belongs to the value.
    await waitFor(() =>
      expect(screen.queryByText('This field is required.')).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('refuses an endpoint that is not a full URL and points at that field', async () => {
    const user = userEvent.setup();
    const save = await renderWith({
      provider: 'openai',
      model: 'gpt-4o-mini',
      apiKey: 'sk-test',
      baseUrl: 'localhost:11434',
    });

    await user.click(save);

    expect(upsertLLMConfig).not.toHaveBeenCalled();
    expect(
      await screen.findByText('Enter a full URL, for example https://api.example.com/v1'),
    ).toBeInTheDocument();
    // A malformed value is not a missing one, so the toast names the field rather than
    // claiming something has to be defined.
    expect(toast.error).toHaveBeenCalledWith(
      'The LLM configuration is not complete',
      expect.objectContaining({
        description: 'Extraction stays disabled until you complete these fields: Base URL',
      }),
    );
  });

  it('saves a complete configuration', async () => {
    const user = userEvent.setup();
    const save = await renderWith({ provider: 'ollama', model: 'llama3.2' });

    await user.click(save);

    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(WORKSPACE_ID, {
        provider: 'ollama',
        model: 'llama3.2',
        temperature: 0.1,
        maxTokens: 2048,
        baseUrl: 'http://localhost:11434',
        apiKey: undefined,
      }),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('accepts a custom provider with no credential', async () => {
    const user = userEvent.setup();
    const save = await renderWith({
      provider: 'deepseek',
      model: 'deepseek-chat',
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: '',
    });

    await user.click(save);

    // A self-hosted gateway commonly accepts unauthenticated requests, so the key is
    // not a gap and the save goes through.
    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ provider: 'deepseek', model: 'deepseek-chat' }),
      ),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('stores no endpoint when the field holds only spaces', async () => {
    const user = userEvent.setup();
    const save = await renderWith({ provider: 'ollama', model: 'llama3.2', baseUrl: '   ' });

    await user.click(save);

    // The completeness rule reads a blank endpoint as "use the provider's default", so
    // a value made of spaces must not be stored where the provider would be handed it
    // as a URL of spaces.
    await waitFor(() =>
      expect(upsertLLMConfig).toHaveBeenCalledWith(
        WORKSPACE_ID,
        expect.objectContaining({ baseUrl: undefined }),
      ),
    );
    expect(upsertLLMConfig).not.toHaveBeenCalledWith(
      WORKSPACE_ID,
      expect.objectContaining({ baseUrl: '   ' }),
    );
  });
});
