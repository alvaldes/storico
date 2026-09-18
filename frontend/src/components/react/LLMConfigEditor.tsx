import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useResolvedTheme } from '@/stores/uiStore';
import {
  Bot,
  FileText,
  Check,
  X,
  LoaderCircle,
  RotateCw,
  CircleHelp,
  TriangleAlert,
  Plus,
  Pencil,
} from 'lucide-react';
import { toast } from 'sonner';
import { getLLMConfig, upsertLLMConfig, fetchAvailableModels } from '@/lib/llm-config-api';
import type { AvailableModel, ModelProbe } from '@/lib/llm-config-api';
import { getPrompts, upsertPrompts } from '@/lib/prompts-api';
import { Button } from '@/components/ui/button';
import {
  Combobox,
  ComboboxInput,
  ComboboxContent,
  ComboboxList,
  ComboboxItem,
  ComboboxEmpty,
} from '@/components/ui/combobox';
import {
  Autocomplete,
  AutocompleteInput,
  AutocompletePopup,
  AutocompleteList,
  AutocompleteItem,
  AutocompleteEmpty,
} from '@/components/ui/autocomplete';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { Field, FieldLabel, FieldDescription, FieldError } from '@/components/ui/field';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
} from '@/components/ui/select';
import { ProviderIcon } from '@/components/ui/provider-icon';
import { FewShotConfigEditor } from '@/components/react/FewShotConfigEditor';
import { CustomProviderDialog } from '@/components/react/CustomProviderDialog';
import { listCustomProviders } from '@/lib/custom-providers-api';
import {
  READINESS_FIELD_TO_FORM_KEY,
  missingLLMConfigFields,
} from '@/lib/llm-config-readiness';
import { llmConfigDraftSchema } from '@/schemas/workspace';
import type { LLMConfigIssueCode } from '@/schemas/workspace';
import { ADD_CUSTOM_PROVIDER_VALUE, KNOWN_PROVIDERS, isKnownProvider } from '@/lib/llm-providers';
import type { CustomProvider, WorkspaceLLMConfig, WorkspacePrompt } from '@/types/workspace';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

interface LLMConfigEditorProps {
  locale: 'en' | 'es';
  workspaceId: string;
}

/** One draft-validation failure, in the two facts the form needs to render it. */
interface DraftIssue {
  /** The form field it belongs to, as the schema reports it. */
  field: string;
  /** The stable message code, translated where it is rendered. */
  code: LLMConfigIssueCode;
}

export function LLMConfigEditor({ locale, workspaceId }: LLMConfigEditorProps) {
  const t = locale === 'es' ? es : en;
  const resolvedTheme = useResolvedTheme();

  /* ── LLM Config State ── */
  const [llmConfig, setLlmConfig] = useState<WorkspaceLLMConfig>({
    provider: 'ollama',
    model: '',
    temperature: 0.1,
    maxTokens: 2048,
    baseUrl: 'http://localhost:11434',
    apiKey: '',
  });
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmSaveResult, setLlmSaveResult] = useState<'idle' | 'success' | 'error'>('idle');

  /* ── Custom Provider Registry State ── */
  const [customProviders, setCustomProviders] = useState<CustomProvider[]>([]);
  // The select's popup is controlled so choosing the add option can close it without
  // the selection moving.
  const [providerSelectOpen, setProviderSelectOpen] = useState(false);
  const [providerDialogOpen, setProviderDialogOpen] = useState(false);
  // `null` registers a new provider; a row renames that one.
  const [providerDialogTarget, setProviderDialogTarget] = useState<CustomProvider | null>(null);

  // Declared here rather than beside the other provider choices because the model-probe
  // effect below reads it, and a `const` read before its declaration is a runtime error.
  // Derived, never a stored flag: whether the provider is custom follows from the name
  // itself, so a second source of truth cannot fall out of step with the saved config.
  const isCustomProvider = !isKnownProvider(llmConfig.provider);

  /* ── Draft validation ── */

  /**
   * The draft exactly as `llmConfigDraftSchema` reads it.
   *
   * The form holds what the API would store as `null` in an empty string, and always
   * holds a number for the two numeric controls, so this is the one place that maps
   * form state to the validated shape. Both the save path and the red messages parse
   * this same object, which is why they can never disagree.
   */
  const draftToValidate = {
    provider: llmConfig.provider,
    model: llmConfig.model ?? '',
    temperature: llmConfig.temperature ?? 0.1,
    maxTokens: llmConfig.maxTokens ?? 2048,
    baseUrl: llmConfig.baseUrl ?? '',
    apiKey: llmConfig.apiKey ?? '',
  };

  // Recomputed on every render, never stored: an error disappears the moment the value
  // that caused it is fixed, instead of when some handler remembers to clear it.
  const draftIssues: DraftIssue[] = (() => {
    const parsed = llmConfigDraftSchema.safeParse(draftToValidate);
    if (parsed.success) return [];
    return parsed.error.issues.map((issue) => ({
      field: String(issue.path[0] ?? ''),
      code: issue.message as LLMConfigIssueCode,
    }));
  })();

  // Before the first save attempt the form explains itself with the summary below
  // rather than painting every empty field of a fresh workspace red.
  const [llmSaveAttempted, setLlmSaveAttempted] = useState(false);

  /**
   * What this workspace cannot extract without, read from the values on screen.
   *
   * Derived, so it describes the form as it is right now rather than as the last save
   * left it — which is what makes the summary trustworthy before anything is attempted.
   */
  const missingFields = missingLLMConfigFields(llmConfig);

  // Labels the summary points with. Reused from the fields already on screen so the
  // summary and the input it names cannot disagree.
  const fieldLabels: Record<string, string> = {
    model: t.settings?.llm_ollama_model ?? 'Model',
    apiKey: t.settings?.llm_openai_api_key ?? 'API Key',
    baseUrl: t.settings?.llm_base_url ?? 'Base URL',
  };
  const labelFor = (field: string) => fieldLabels[field] ?? field;

  // `zod`'s own prose is not UI copy — it would arrive in English inside a Spanish
  // page — so the schema carries these codes and the translation happens here.
  const issueCopy: Record<LLMConfigIssueCode, string> = {
    required: t.workspace?.llmErrorRequired ?? 'This field is required.',
    too_long: t.workspace?.llmErrorTooLong ?? 'This value is too long.',
    invalid_url:
      t.workspace?.llmErrorInvalidUrl ?? 'Enter a full URL, for example https://api.example.com/v1',
    out_of_range: t.workspace?.llmErrorOutOfRange ?? 'This value is out of the allowed range.',
  };

  /** The red message for one field, or nothing when that field is fine. */
  const fieldErrorFor = (field: string) => {
    if (!llmSaveAttempted) return null;
    const issue = draftIssues.find((candidate) => candidate.field === field);
    return issue ? <FieldError>{issueCopy[issue.code]}</FieldError> : null;
  };

  /* ── Prompt Config State ── */
  const [prompts, setPrompts] = useState<WorkspacePrompt>({
    systemPrompt: '',
    instructionTemplate: '',
    fewShotEnabled: true,
    fewShotLimit: 3,
    fewShotThreshold: 0.85,
  });
  const [promptSaving, setPromptSaving] = useState(false);
  const [promptSaveResult, setPromptSaveResult] = useState<'idle' | 'success' | 'error'>('idle');

  /* ── Available Models State ── */
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  // A custom-provider list exists only because the user asked for one, so the empty and
  // error hints must stay silent until a probe has actually settled.
  const [customModelsProbed, setCustomModelsProbed] = useState(false);

  /* ── Shared State ── */
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  /* ── Fetch Configs ── */
  const loadConfigs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [llm, promptData] = await Promise.all([
        getLLMConfig(workspaceId).catch((err) => {
          if (
            err instanceof Error &&
            (err.message.includes('403') || err.message.includes('admin'))
          ) {
            return null;
          }
          throw err;
        }),
        getPrompts(workspaceId).catch((err) => {
          if (
            err instanceof Error &&
            (err.message.includes('403') || err.message.includes('admin'))
          ) {
            return null;
          }
          throw err;
        }),
      ]);

      if (llm) {
        const loadedProvider = llm.provider || 'ollama';
        setLlmConfig({
          provider: loadedProvider,
          model: llm.model ?? '',
          temperature: llm.temperature ?? 0.1,
          maxTokens: llm.maxTokens ?? 2048,
          // Never default to the Ollama host: it is Ollama's endpoint, and every other
          // provider has its own. The field's placeholder names the provider's default,
          // and an empty value is what tells the backend to use it.
          baseUrl: llm.baseUrl ?? '',
          apiKey: llm.apiKey ?? '',
        });
      }
      if (promptData) {
        setPrompts({
          systemPrompt: promptData.systemPrompt ?? '',
          instructionTemplate: promptData.instructionTemplate ?? '',
          fewShotEnabled: promptData.fewShotEnabled ?? true,
          fewShotLimit: promptData.fewShotLimit ?? 3,
          fewShotThreshold: promptData.fewShotThreshold ?? 0.85,
        });
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.workspace?.loadError ?? 'Failed to load settings');
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  /* ── Fetch Available Models ── */

  /**
   * The selection the form holds right now.
   *
   * Memoised on the three scalars so it keeps its identity across unrelated renders:
   * the auto-probe effect depends on it, and a fresh object every render would restart
   * that effect continuously.
   */
  const pendingProbe = useMemo<ModelProbe>(
    () => ({
      provider: llmConfig.provider,
      baseUrl: llmConfig.baseUrl ?? '',
      apiKey: llmConfig.apiKey ?? '',
    }),
    [llmConfig.provider, llmConfig.baseUrl, llmConfig.apiKey],
  );

  // `loadModels` keeps a stable identity by taking the selection as an argument. Were
  // the selection a dependency instead, every keystroke in the API key or the Base URL
  // would give this callback a new identity and drag the auto-probe effect along.
  const loadModels = useCallback(
    async (probe: ModelProbe) => {
      setModelsLoading(true);
      setModelsError(null);
      try {
        setAvailableModels(await fetchAvailableModels(workspaceId, probe));
      } catch (err) {
        setAvailableModels([]);
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes('502') || msg.includes('Failed to fetch')) {
          setModelsError(
            t.workspace?.llmModelsFetchError ??
              'Could not reach the provider. Check your API key and Base URL.',
          );
        } else {
          setModelsError(msg);
        }
      } finally {
        setModelsLoading(false);
      }
    },
    [workspaceId, t],
  );

  // Whether the selection holds enough to ask the provider anything. Ollama needs
  // nothing, a cloud provider needs a key, and a custom provider needs the endpoint to
  // ask — its key stays optional because self-hosted gateways commonly accept
  // unauthenticated requests.
  const canProbe =
    llmConfig.provider === 'ollama' ||
    (isCustomProvider
      ? (llmConfig.baseUrl ?? '').trim() !== ''
      : (llmConfig.apiKey ?? '').trim() !== '');

  /** Why the refresh action is unavailable, or `null` when it is available. */
  const probeBlockedReason = canProbe
    ? null
    : isCustomProvider
      ? (t.workspace?.llmModelsNoBaseUrl ?? 'Add the Base URL first')
      : (t.workspace?.llmModelsNoApiKey ?? 'Add your API key first');

  /* ── Custom Provider Registry ── */
  const loadCustomProviders = useCallback(async () => {
    try {
      setCustomProviders(await listCustomProviders(workspaceId));
    } catch (err) {
      // The select stays usable without the registry — the known providers and the
      // saved selection are still offered — so a failed list is reported without
      // blocking the field. A member who cannot read the admin-only endpoint keeps
      // exactly the behaviour they had before, which is why that case stays silent.
      setCustomProviders([]);
      if (err instanceof Error && (err.message.includes('403') || err.message.includes('admin'))) {
        return;
      }
      toast.error(
        t.workspace?.llmCustomProviderLoadError ?? 'Could not load the custom providers.',
      );
    }
  }, [workspaceId, t]);

  /* ── Explicit Model Refresh ── */
  const handleRefreshModels = useCallback(async () => {
    await loadModels(pendingProbe);
    // `loadModels` never rejects, so this records a settled probe on failure too.
    setCustomModelsProbed(true);
  }, [loadModels, pendingProbe]);

  useEffect(() => {
    setMounted(true);
    loadConfigs();
  }, [loadConfigs]);

  useEffect(() => {
    loadCustomProviders();
  }, [loadCustomProviders]);

  // The provider whose list the field currently stands for. It also gates the probe, so
  // it is a ref: remembering it must not render anything.
  const probedProviderRef = useRef<string | null>(null);

  // Auto-probe the selected provider's list, once per provider.
  //
  // The probe carries the *pending* selection, so the answer describes the provider the
  // user picked instead of whichever one happens to be saved — the coupling that used to
  // make every provider answer for the saved one. Free-text fields are deliberately not
  // a trigger: probing per keystroke would reach the provider with a half-typed key or a
  // partial URL, so the refresh action is the affordance for those.
  useEffect(() => {
    if (!mounted || loading) return;
    if (probedProviderRef.current === llmConfig.provider) return;
    probedProviderRef.current = llmConfig.provider;

    // A list describes exactly one provider. The new one has no list until its own probe
    // answers, so the previous provider's models must not keep standing in for them.
    setAvailableModels([]);
    setModelsError(null);

    if (!canProbe) return;
    void loadModels(pendingProbe);
  }, [canProbe, loadModels, pendingProbe, llmConfig.provider, mounted, loading]);

  /* ── Provider Saved (create or rename) ── */
  const handleProviderSaved = (saved: CustomProvider) => {
    setCustomProviders((prev) =>
      [...prev.filter((p) => p.id !== saved.id), saved].sort((a, b) =>
        a.name.localeCompare(b.name),
      ),
    );

    if (providerDialogTarget) {
      // A rename changes the name and nothing else: the endpoint, credential and model
      // still belong to the same provider. The backend already followed it into the
      // saved selection, so the field follows too, but only when it was pointing there.
      if (llmConfig.provider === providerDialogTarget.name) {
        setLlmConfig((prev) => ({ ...prev, provider: saved.name }));
      }
      return;
    }

    // A new provider has no endpoint, key or model yet, and the ones the previous
    // provider left behind are not its values.
    setLlmConfig((prev) => ({ ...prev, provider: saved.name, model: '', apiKey: '', baseUrl: '' }));
    setAvailableModels([]);
    setModelsError(null);
    setCustomModelsProbed(false);
  };

  /* ── LLM Save Handler ── */
  const handleLLMSave = async () => {
    const parsed = llmConfigDraftSchema.safeParse(draftToValidate);

    if (!parsed.success) {
      // Nothing is persisted. An incomplete configuration is exactly what leaves the
      // workspace unable to extract, so saving it would only make that state durable.
      setLlmSaveAttempted(true);
      setLlmSaveResult('error');
      // Name what still has to be defined, preferring the missing fields: a value out
      // of range is already pointed at under its own input.
      const missing = draftIssues.filter((issue) => issue.code === 'required');
      const named = Array.from(
        new Set((missing.length > 0 ? missing : draftIssues).map((issue) => labelFor(issue.field))),
      );
      toast.error(t.workspace?.llmValidationBlocked ?? 'The LLM configuration is not complete', {
        description: (
          t.workspace?.llmValidationBlockedDesc ??
          'Extraction stays disabled until you complete these fields: {fields}'
        ).replace('{fields}', named.join(', ')),
      });
      setTimeout(() => setLlmSaveResult('idle'), 3000);
      return;
    }

    setLlmSaving(true);
    setLlmSaveResult('idle');
    try {
      await upsertLLMConfig(workspaceId, {
        provider: parsed.data.provider,
        model: parsed.data.model || undefined,
        temperature: parsed.data.temperature,
        maxTokens: parsed.data.maxTokens,
        // Trimmed before it is stored: an all-whitespace endpoint means "use the
        // provider's default" to the completeness rule, so persisting it verbatim
        // would store a value that rule reads as absent while the provider is handed
        // it as a URL made of spaces.
        baseUrl: parsed.data.baseUrl.trim() || undefined,
        apiKey: parsed.data.apiKey || undefined,
      });
      setLlmSaveResult('success');
      toast.success(t.settings?.llm_saved ?? 'LLM configuration saved');
      setTimeout(() => setLlmSaveResult('idle'), 3000);
      // The saved row is what the next visit loads, so the list on screen has to be the
      // one that row describes. Without this the field keeps the pre-save answer until
      // the user happens to press refresh.
      if (canProbe) await loadModels(pendingProbe);
    } catch (err) {
      setLlmSaveResult('error');
      const message =
        err instanceof Error
          ? err.message
          : (t.workspace?.llmSaveError ?? 'Failed to save LLM config');
      toast.error(message);
      setTimeout(() => setLlmSaveResult('idle'), 3000);
    } finally {
      setLlmSaving(false);
    }
  };

  /* ── Prompt Save Handler ── */
  const handlePromptSave = async () => {
    setPromptSaving(true);
    setPromptSaveResult('idle');
    try {
      await upsertPrompts(workspaceId, {
        systemPrompt: prompts.systemPrompt || undefined,
        instructionTemplate: prompts.instructionTemplate || undefined,
        fewShotEnabled: prompts.fewShotEnabled,
        fewShotLimit: prompts.fewShotLimit,
        fewShotThreshold: prompts.fewShotThreshold,
      });
      setPromptSaveResult('success');
      toast.success(t.workspace?.promptSaved ?? 'Prompt configuration saved');
      setTimeout(() => setPromptSaveResult('idle'), 3000);
    } catch (err) {
      setPromptSaveResult('error');
      const message =
        err instanceof Error
          ? err.message
          : (t.workspace?.promptSaveError ?? 'Failed to save prompts');
      toast.error(message);
      setTimeout(() => setPromptSaveResult('idle'), 3000);
    } finally {
      setPromptSaving(false);
    }
  };

  /* ── Loading State ── */
  if (!mounted) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-(--color-border) border-t-(--color-primary-500)" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-12 text-sm text-(--color-text-secondary)">
        <LoaderCircle className="h-4 w-4 animate-spin" />
        {t.workspace?.loading ?? 'Loading settings...'}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
        <TriangleAlert className="h-5 w-5 shrink-0 text-red-500" />
        <div>
          <p className="text-sm font-medium text-red-800 dark:text-red-200">{error}</p>
          <button
            type="button"
            onClick={loadConfigs}
            className="mt-1 text-sm text-red-600 underline hover:text-red-800 dark:text-red-400 dark:hover:text-red-200"
          >
            {t.workspace?.tryAgain ?? 'Try again'}
          </button>
        </div>
      </div>
    );
  }

  /* ── Provider choices ── */

  const providerLabels: Record<string, string> = {
    ollama: t.settings?.llm_provider_ollama ?? 'Ollama (Local)',
    openai: t.settings?.llm_provider_openai ?? 'OpenAI',
    anthropic: t.settings?.llm_provider_anthropic ?? 'Anthropic',
    gemini: t.settings?.llm_provider_gemini ?? 'Gemini',
  };
  const providerLabel = (provider: string) => providerLabels[provider] ?? provider;

  // The row the pencil renames. A custom provider without one has nothing to rename: it
  // is a name the config holds that the registry does not, so the add action is the way
  // to register it.
  const selectedCustomProvider = customProviders.find((p) => p.name === llmConfig.provider);

  // Names to offer, including the current selection when the registry does not hold it
  // (an unreachable list, or a name configured before the registry existed). Without
  // that fallback the select would render an empty value for a provider that is saved.
  const customProviderNames = Array.from(
    new Set([
      ...customProviders.map((p) => p.name),
      ...(isCustomProvider ? [llmConfig.provider] : []),
    ]),
  ).sort((a, b) => a.localeCompare(b));

  // Only meaningful once a list actually arrived; an empty list means "unknown", not
  // "missing", and the error hint already covers the unreachable case.
  const savedModelMissingFromList =
    llmConfig.model !== '' &&
    !modelsLoading &&
    availableModels.length > 0 &&
    !availableModels.some((m) => m.id === llmConfig.model);

  // The field is selection-only, so an empty list is a hard stop rather than a hint
  // to type something: name it where the user is already looking.
  const modelListUnavailable = !modelsLoading && availableModels.length === 0;
  const noModelsMessage =
    t.workspace?.llmModelsEmpty ?? 'No models available. Check the provider then refresh.';

  return (
    <div className="space-y-6">
      {/* Two-column grid: LLM Config + Prompt Config */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ── Section 1: LLM Configuration ── */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-(--color-text-secondary)" />
              <CardTitle>{t.settings?.llm_title ?? 'LLM Configuration'}</CardTitle>
            </div>
            <CardDescription>
              {t.settings?.llm_description ??
                'Configure the AI model used for task extraction in this workspace'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* The workspace's readiness, stated before anything is attempted. Shown
                while the values on screen cannot extract — which is what makes a fresh
                workspace explain itself here instead of only after a refused save. */}
            {missingFields.length > 0 && (
              <div
                role="alert"
                className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/30"
              >
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                <div className="space-y-1">
                  <p className="text-sm font-medium text-red-800 dark:text-red-200">
                    {t.workspace?.llmMissingSummaryTitle ??
                      'This workspace cannot extract tasks yet'}
                  </p>
                  <p className="text-sm text-red-700 dark:text-red-300">
                    {t.workspace?.llmMissingSummaryDesc ??
                      'Complete these fields to enable extraction:'}
                  </p>
                  <ul className="list-disc pl-5 text-sm text-red-700 dark:text-red-300">
                    {missingFields.map((field) => (
                      <li key={field}>{labelFor(READINESS_FIELD_TO_FORM_KEY[field])}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Provider */}
            <Field>
              <FieldLabel htmlFor="llm-provider">
                {t.settings?.llm_provider ?? 'Provider'}
              </FieldLabel>
              <div className="flex items-start gap-2">
                <div className="flex-1">
                  {/* Always a select: the name is chosen or registered, never typed into
                      this field. */}
                  <Select
                    value={llmConfig.provider}
                    open={providerSelectOpen}
                    onOpenChange={setProviderSelectOpen}
                    onValueChange={(val) => {
                      if (val === null) return;
                      // The add option is a control, not a provider: it opens the dialog
                      // and leaves the selection exactly where it was.
                      if (val === ADD_CUSTOM_PROVIDER_VALUE) {
                        setProviderDialogTarget(null);
                        setProviderDialogOpen(true);
                        setProviderSelectOpen(false);
                        return;
                      }
                      // Switching provider drops the values the previous one owned: a
                      // model id and an API key are not portable between endpoints.
                      setLlmConfig((prev) => ({
                        ...prev,
                        provider: val,
                        model: '',
                        apiKey: '',
                        baseUrl: val === 'ollama' ? 'http://localhost:11434' : '',
                      }));
                    }}
                  >
                    <SelectTrigger id="llm-provider" className="w-full">
                      <div className="flex items-center gap-2">
                        {/* Decorative: the label sits beside it. Marking it so keeps the
                            icon's own accessible name — the Anthropic SVGs carry a
                            `<title>` that repeats the label — out of the field's name. */}
                        <ProviderIcon
                          provider={llmConfig.provider}
                          theme={resolvedTheme}
                          className="h-4 w-4 shrink-0"
                          aria-hidden="true"
                        />
                        <span>{providerLabel(llmConfig.provider)}</span>
                      </div>
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWN_PROVIDERS.map((provider) => (
                        <SelectItem key={provider} value={provider}>
                          <ProviderIcon
                            provider={provider}
                            theme={resolvedTheme}
                            className="mr-2 h-4 w-4 shrink-0"
                            aria-hidden="true"
                          />
                          {providerLabel(provider)}
                        </SelectItem>
                      ))}
                      {customProviderNames.length > 0 && <SelectSeparator />}
                      {customProviderNames.map((name) => (
                        <SelectItem key={name} value={name}>
                          {/* The same component the trigger above uses, which falls back
                              to a neutral server glyph for anything outside the four
                              built-ins: that is what a custom selection already shows in
                              the collapsed field, so the item and the trigger cannot
                              disagree about the same provider. */}
                          <ProviderIcon
                            provider={name}
                            theme={resolvedTheme}
                            className="mr-2 h-4 w-4 shrink-0"
                            aria-hidden="true"
                          />
                          {name}
                        </SelectItem>
                      ))}
                      <SelectSeparator />
                      <SelectItem value={ADD_CUSTOM_PROVIDER_VALUE}>
                        <Plus className="mr-2 h-4 w-4 shrink-0" />
                        {t.workspace?.llmAddCustomProvider ?? 'Add custom provider'}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {/* Rename sits beside the select, and only for a registered custom
                    provider: a known provider's name is not the workspace's to edit. */}
                {selectedCustomProvider && (
                  <div className="relative">
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      title={t.workspace?.llmCustomProviderRenameTitle ?? 'Rename custom provider'}
                      onClick={() => {
                        setProviderDialogTarget(selectedCustomProvider);
                        setProviderDialogOpen(true);
                      }}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
              <FieldDescription>
                {isCustomProvider
                  ? (t.workspace?.llmCustomProviderDesc ??
                    'Enter the provider name. You will need to set the Base URL and API Key manually.')
                  : (t.workspace?.llmProviderDesc ?? 'The AI model provider for task extraction.')}
              </FieldDescription>
            </Field>

            {/* Model — Combobox for known providers, free Input for custom */}
            <Field>
              <FieldLabel htmlFor="llm-model">{t.settings?.llm_ollama_model ?? 'Model'}</FieldLabel>
              <div className="flex items-start gap-2">
                <div className="flex-1">
                  {isCustomProvider ? (
                    /* Custom provider — the typed text is the model, and the popup is a
                       catalogue of everything the provider reported. */
                    <Autocomplete
                      value={llmConfig.model ?? ''}
                      onValueChange={(val) =>
                        setLlmConfig((prev) => ({
                          ...prev,
                          model: val,
                        }))
                      }
                      // No built-in filtering. The popup opens as a complete catalogue:
                      // narrowing it against the field's current text would hide every
                      // other model, which is the complaint this field exists to fix.
                      filter={null}
                      // `Autocomplete.Root` hard-codes this to `false`, so a click in the
                      // text would reveal nothing. Turned back on so the field behaves
                      // like the known providers' model field and like a plain select:
                      // one click anywhere in it opens the catalogue.
                      openOnInputClick
                    >
                      <AutocompleteInput
                        id="llm-model"
                        placeholder={
                          t.workspace?.llmCustomModelPlaceholder ??
                          'e.g. deepseek-chat, groq-llama-3.3-70b'
                        }
                        // The chevron is the explicit affordance for the catalogue, so its
                        // name carries what the list holds.
                        triggerLabel={`${t.workspace?.llmCustomModelsDiscovered ?? 'Discovered models'} (${availableModels.length})`}
                      />
                      <AutocompletePopup>
                        <AutocompleteList>
                          {availableModels.map((m) => (
                            // The item's `value` is the model id, and its rendered text
                            // starts with that same id: pressing the entry must write the
                            // id the provider expects, never the readable name.
                            <AutocompleteItem key={m.id} value={m.id}>
                              {m.id}
                              {/* The space is an explicit text node: JSX drops the
                                  whitespace around a line break, which would jam the id
                                  and the readable name together in the accessible name. */}
                              {m.name !== m.id && (
                                <>
                                  {' '}
                                  <span className="text-(--color-text-tertiary)">{m.name}</span>
                                </>
                              )}
                            </AutocompleteItem>
                          ))}
                        </AutocompleteList>
                        {modelsLoading ? (
                          <AutocompleteEmpty>
                            {t.workspace?.llmModelsLoading ?? 'Loading models...'}
                          </AutocompleteEmpty>
                        ) : availableModels.length === 0 ? (
                          <AutocompleteEmpty>
                            {modelsError
                              ? modelsError
                              : (t.workspace?.llmCustomModelsEmpty ??
                                'The provider returned no models. Type the model id manually.')}
                          </AutocompleteEmpty>
                        ) : null}
                      </AutocompletePopup>
                    </Autocomplete>
                  ) : (
                    /* Known providers — Combobox with auto-populated suggestions */
                    <Combobox
                      key={`model-${llmConfig.provider}`}
                      // Controlled on the persisted model id: without `value` the input starts
                      // empty, so the field only ever shows its placeholder and the saved
                      // model stays invisible until the user re-picks it from the list.
                      value={llmConfig.model || null}
                      onValueChange={(val) => {
                        if (val !== null && val !== undefined) {
                          setLlmConfig((prev) => ({
                            ...prev,
                            model: String(val),
                          }));
                        }
                      }}
                    >
                      <ComboboxInput
                        id="llm-model"
                        disabled={llmConfig.provider !== 'ollama' && !llmConfig.apiKey}
                        // `readOnly` rides on the input element, not on the combobox root:
                        // the root would also lock the list selection, while the DOM
                        // attribute only removes typing. base-ui commits a model solely
                        // through `onValueChange`, so typed text would show up in the field
                        // and then revert on blur — a field that looks editable and is not.
                        readOnly
                        // No provider default here: any model name in the placeholder reads
                        // as a model that is already chosen.
                        placeholder={t.settings?.llm_model_placeholder ?? 'Select a model'}
                      />
                      {/* The input text is the model id — the value that gets saved; the
                          list renders each model's friendly `name` instead. */}
                      <ComboboxContent>
                        <ComboboxList>
                          {availableModels.map((m) => (
                            <ComboboxItem key={m.id} value={m.id}>
                              {m.name}
                            </ComboboxItem>
                          ))}
                        </ComboboxList>
                        {modelsLoading ? (
                          <ComboboxEmpty>
                            {t.workspace?.llmModelsLoading ?? 'Loading models...'}
                          </ComboboxEmpty>
                        ) : availableModels.length === 0 ? (
                          <ComboboxEmpty>
                            {modelsError ? modelsError : noModelsMessage}
                          </ComboboxEmpty>
                        ) : null}
                      </ComboboxContent>
                    </Combobox>
                  )}
                </div>
                <div className="relative">
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={handleRefreshModels}
                    disabled={modelsLoading || !canProbe}
                    // A stable name: the button is always the refresh action, and its
                    // title carries the reason when it cannot run.
                    aria-label={t.workspace?.llmRefreshModels ?? 'Refresh models'}
                    title={probeBlockedReason ?? t.workspace?.llmRefreshModels ?? 'Refresh models'}
                  >
                    <RotateCw className={`h-4 w-4 ${modelsLoading ? 'animate-spin' : ''}`} />
                  </Button>
                </div>
              </div>
              {/* A single suggestion mechanism: one dropdown. A native `datalist` was
                  invisible in Firefox, and an always-visible button block flooded the
                  card once a provider answered with a dozen models. */}
              <FieldDescription>
                {isCustomProvider ? (
                  /* Custom hints report real state in priority order: a failed probe,
                     then a probe that came back empty, then the typing hint. Nothing
                     claims a list is empty before the user has asked for one. */
                  modelsError ? (
                    <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                      <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                      {modelsError}
                    </span>
                  ) : customModelsProbed && availableModels.length === 0 ? (
                    <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                      <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                      {t.workspace?.llmCustomModelsEmpty ??
                        'The provider returned no models. Type the model id manually.'}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-(--color-text-tertiary)">
                      <CircleHelp className="h-3.5 w-3.5 shrink-0" />
                      {t.workspace?.llmCustomModelHint ??
                        "Type the model id the provider expects, or load the provider's list for suggestions."}
                    </span>
                  )
                ) : modelsError ? (
                  <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                    <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                    {modelsError}
                  </span>
                ) : llmConfig.provider !== 'ollama' && !llmConfig.apiKey ? (
                  <span className="flex items-center gap-1.5 text-(--color-text-tertiary)">
                    <CircleHelp className="h-3.5 w-3.5 shrink-0" />
                    {t.workspace?.llmModelsNoApiKey ??
                      'Add your API key and save to enable model suggestions.'}
                  </span>
                ) : savedModelMissingFromList ? (
                  <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                    <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                    {t.workspace?.llmModelNotInList ??
                      "The saved model is not in the provider's model list."}
                  </span>
                ) : modelListUnavailable ? (
                  <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                    <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                    {noModelsMessage}
                  </span>
                ) : (
                  (t.workspace?.llmModelDesc ??
                  "The model to use for task extraction, picked from the provider's list.")
                )}
              </FieldDescription>
              {fieldErrorFor('model')}
            </Field>

            {/* Temperature */}
            <Field>
              <FieldLabel htmlFor="llm-temperature">
                {t.settings?.llm_temperature ?? 'Temperature'}
              </FieldLabel>
              <div className="flex items-center gap-3">
                <Slider
                  id="llm-temperature"
                  value={[llmConfig.temperature ?? 0.1]}
                  onValueChange={(value) =>
                    setLlmConfig((prev) => ({
                      ...prev,
                      temperature: Array.isArray(value) ? value[0] : value,
                    }))
                  }
                  min={0}
                  max={2}
                  step={0.1}
                  className="flex-1"
                />
                <span className="min-w-[2.5rem] text-sm font-medium tabular-nums text-(--color-text-secondary)">
                  {(llmConfig.temperature ?? 0.1).toFixed(1)}
                </span>
              </div>
              <FieldDescription>
                {t.workspace?.llmTemperatureDesc ??
                  'Lower values = more consistent output. Higher values = more creative.'}
              </FieldDescription>
              {fieldErrorFor('temperature')}
            </Field>

            {/* Max Tokens */}
            <Field>
              <FieldLabel htmlFor="llm-max-tokens">
                {t.settings?.llm_max_tokens ?? 'Max Tokens'}
              </FieldLabel>
              <Input
                id="llm-max-tokens"
                type="number"
                value={llmConfig.maxTokens ?? 2048}
                onChange={(e) =>
                  setLlmConfig((prev) => ({
                    ...prev,
                    maxTokens: parseInt(e.target.value, 10) || 0,
                  }))
                }
                min={256}
                max={8192}
                step={256}
              />
              <FieldDescription>
                {t.workspace?.llmMaxTokensDesc ??
                  'Maximum number of tokens the model can generate per response.'}
              </FieldDescription>
              {fieldErrorFor('maxTokens')}
            </Field>

            {/* ── Provider-specific fields ── */}
            {llmConfig.provider === 'ollama' ? (
              /* Base URL — required for Ollama */
              <Field>
                <FieldLabel htmlFor="llm-base-url">
                  {t.settings?.llm_base_url ?? 'Base URL'}
                </FieldLabel>
                <Input
                  id="llm-base-url"
                  type="text"
                  value={llmConfig.baseUrl ?? ''}
                  onChange={(e) =>
                    setLlmConfig((prev) => ({
                      ...prev,
                      baseUrl: e.target.value,
                    }))
                  }
                  placeholder="http://localhost:11434"
                />
                <FieldDescription>
                  {t.workspace?.llmBaseUrlDesc ?? 'The URL where your Ollama instance is running.'}
                </FieldDescription>
                {fieldErrorFor('baseUrl')}
              </Field>
            ) : (
              <>
                {/* API Key — required for cloud providers */}
                <Field>
                  <FieldLabel htmlFor="llm-api-key">
                    {llmConfig.provider === 'openai'
                      ? (t.settings?.llm_openai_api_key ?? 'API Key')
                      : llmConfig.provider === 'gemini'
                        ? (t.settings?.llm_gemini_api_key ?? 'API Key')
                        : (t.settings?.llm_anthropic_api_key ?? 'API Key')}
                  </FieldLabel>
                  <Input
                    id="llm-api-key"
                    type="password"
                    value={llmConfig.apiKey ?? ''}
                    onChange={(e) =>
                      setLlmConfig((prev) => ({
                        ...prev,
                        apiKey: e.target.value,
                      }))
                    }
                    placeholder={
                      isCustomProvider || llmConfig.provider === 'openai'
                        ? 'sk-...'
                        : llmConfig.provider === 'gemini'
                          ? 'AIzaSyD-...'
                          : 'sk-ant-...'
                    }
                  />
                  <FieldDescription>
                    {t.workspace?.llmApiKeyDesc ??
                      'Your API key for this provider. It is stored with this workspace on the server — readable only by its admins, and never saved in your browser.'}
                  </FieldDescription>
                  {fieldErrorFor('apiKey')}
                </Field>

                {/* Base URL — optional for cloud providers (proxy/custom endpoint) */}
                <Field>
                  <FieldLabel htmlFor="llm-base-url">
                    {t.settings?.llm_base_url ?? 'Base URL'}
                  </FieldLabel>
                  <Input
                    id="llm-base-url"
                    type="text"
                    value={llmConfig.baseUrl ?? ''}
                    onChange={(e) =>
                      setLlmConfig((prev) => ({
                        ...prev,
                        baseUrl: e.target.value,
                      }))
                    }
                    placeholder={
                      isCustomProvider || llmConfig.provider === 'openai'
                        ? 'https://api.openai.com/v1'
                        : 'https://api.anthropic.com'
                    }
                  />
                  <FieldDescription>
                    {t.workspace?.llmBaseUrlCloudDesc ??
                      'Optional. Leave empty to use the default API endpoint.'}
                  </FieldDescription>
                  {fieldErrorFor('baseUrl')}
                </Field>
              </>
            )}

            {/* Save Button */}
            <div className="flex items-center gap-3 pt-1">
              <Button onClick={handleLLMSave} disabled={llmSaving} className="w-full sm:w-auto">
                {llmSaving ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : llmSaveResult === 'success' ? (
                  <Check className="h-4 w-4" />
                ) : llmSaveResult === 'error' ? (
                  <X className="h-4 w-4" />
                ) : null}
                {llmSaveResult === 'success'
                  ? (t.workspace?.llmSaved ?? 'Saved')
                  : (t.settings?.llm_save ?? 'Save LLM Configuration')}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* ── Section 2: Prompt Configuration ── */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-(--color-text-secondary)" />
              <CardTitle>{t.workspace?.promptTitle ?? 'Prompt Configuration'}</CardTitle>
            </div>
            <CardDescription>
              {t.workspace?.promptDescription ??
                'Customize the prompts used for task extraction in this workspace'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* System Prompt */}
            <Field>
              <FieldLabel htmlFor="system-prompt">
                {t.workspace?.systemPrompt ?? 'System Prompt'}
              </FieldLabel>
              <Textarea
                id="system-prompt"
                rows={8}
                className="min-h-20 h-20 w-full resize-y"
                value={prompts.systemPrompt ?? ''}
                onChange={(e) =>
                  setPrompts((prev) => ({
                    ...prev,
                    systemPrompt: e.target.value,
                  }))
                }
                placeholder={
                  t.workspace?.systemPromptPlaceholder ??
                  'You are an expert software development lead who excels at breaking down user stories into clear, actionable development tasks.'
                }
              />
              <FieldDescription>
                {t.workspace?.systemPromptDesc ??
                  "The system-level instruction that sets the AI's role and behavior"}
              </FieldDescription>
            </Field>

            {/* Instruction Template */}
            <Field>
              <FieldLabel htmlFor="instruction-template">
                {t.workspace?.instructionTemplate ?? 'Instruction Template'}
              </FieldLabel>
              <Textarea
                id="instruction-template"
                rows={12}
                className="min-h-36 h-36 w-full resize-y"
                value={prompts.instructionTemplate ?? ''}
                onChange={(e) =>
                  setPrompts((prev) => ({
                    ...prev,
                    instructionTemplate: e.target.value,
                  }))
                }
                placeholder={
                  t.workspace?.instructionTemplatePlaceholder ??
                  'Break this user story into smaller development tasks...'
                }
              />
              <FieldDescription>
                {t.workspace?.instructionTemplateDesc ??
                  'The instruction prompt with format guidelines and few-shot examples'}
              </FieldDescription>
            </Field>

            {/* Few-Shot Config Editor */}
            <FewShotConfigEditor
              locale={locale}
              enabled={prompts.fewShotEnabled ?? true}
              limit={prompts.fewShotLimit ?? 3}
              threshold={prompts.fewShotThreshold ?? 0.85}
              onChange={(value) =>
                // The editor speaks a generic { enabled, limit, threshold } payload;
                // the persisted prompt row speaks fewShot*. Map explicitly so the
                // compiler catches a rename instead of a silent no-op: a spread of the
                // payload into `prompts` writes keys nobody reads back, which leaves
                // this controlled switch frozen and the saved values unchanged.
                setPrompts((prev) => ({
                  ...prev,
                  fewShotEnabled: value.enabled,
                  fewShotLimit: value.limit,
                  fewShotThreshold: value.threshold,
                }))
              }
            />

            {/* Save Button */}
            <div className="flex items-center gap-3 pt-1">
              <Button
                onClick={handlePromptSave}
                disabled={promptSaving}
                className="w-full sm:w-auto"
              >
                {promptSaving ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : promptSaveResult === 'success' ? (
                  <Check className="h-4 w-4" />
                ) : promptSaveResult === 'error' ? (
                  <X className="h-4 w-4" />
                ) : null}
                {promptSaveResult === 'success'
                  ? (t.workspace?.llmSaved ?? 'Saved')
                  : (t.workspace?.savePrompts ?? 'Save Prompt Configuration')}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <CustomProviderDialog
        locale={locale}
        workspaceId={workspaceId}
        provider={providerDialogTarget}
        open={providerDialogOpen}
        onOpenChange={setProviderDialogOpen}
        onSaved={handleProviderSaved}
      />
    </div>
  );
}
