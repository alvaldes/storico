import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useResolvedTheme } from '@/stores/uiStore';
import {
  Bot,
  Check,
  X,
  LoaderCircle,
  RotateCw,
  CircleHelp,
  TriangleAlert,
  Plus,
  Pencil,
  Gavel,
} from 'lucide-react';
import { toast } from 'sonner';
import { getLLMConfig, upsertLLMConfig, fetchAvailableModels } from '@/lib/llm-config-api';
import type { AvailableModel, ModelProbe } from '@/lib/llm-config-api';
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
import { Field, FieldLabel, FieldDescription, FieldError } from '@/components/ui/field';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
} from '@/components/ui/select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { ProviderIcon } from '@/components/ui/provider-icon';
import { CustomProviderDialog } from '@/components/react/CustomProviderDialog';
import { listCustomProviders } from '@/lib/custom-providers-api';
import {
  READINESS_FIELD_TO_FORM_KEY,
  missingLLMConfigFields,
} from '@/lib/llm-config-readiness';
import { llmConfigDraftSchema } from '@/schemas/workspace';
import type { LLMConfigIssueCode } from '@/schemas/workspace';
import { ADD_CUSTOM_PROVIDER_VALUE, KNOWN_PROVIDERS, isKnownProvider } from '@/lib/llm-providers';
import type { CustomProvider, WorkspaceLLMConfig } from '@/types/workspace';
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

/**
 * The three relationships the judge can state (S11, owner's choices 2026-11-03).
 *
 * The radio labels are the point of the block: instead of four peer fields whose
 * emptiness silently meant "same as extraction", the judge now says outright which of
 * the three configurations it runs on, and the reveal shows exactly the fields that
 * mode needs.
 */
type JudgeMode = 'same' | 'other-model' | 'other-provider';

/**
 * Which mode a stored row loads into.
 *
 * The four judge fields keep their meaning from D9: `judge_provider` set means the
 * judge runs on its own provider; otherwise any other set field means "another model
 * of the extraction provider"; all four empty is the default — the same model.
 */
function deriveJudgeMode(judge: {
  provider: string;
  model: string;
  apiKey: string;
  baseUrl: string;
}): JudgeMode {
  if (judge.provider !== '') return 'other-provider';
  if (judge.model !== '' || judge.apiKey !== '' || judge.baseUrl !== '') return 'other-model';
  return 'same';
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
  // The judge block (D9) is a second, independent LLM configuration held apart from
  // `llmConfig`. Every field falls back independently to the extraction value when
  // empty, and the empty string is what the form sends to clear: the payload keeps
  // a stored value when its key is omitted, so all four judge fields always travel
  // explicitly (the same rule `judgeModel` followed alone under D7).
  const [judgeConfig, setJudgeConfig] = useState({
    provider: '',
    model: '',
    apiKey: '',
    baseUrl: '',
  });
  const [judgeMode, setJudgeMode] = useState<JudgeMode>('same');
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
   * The judge values as the mode maps them onto the persisted row (S11).
   *
   * Same model sends all four empty — which is what clears them; another model of
   * this provider sends `judge_model` only; another provider sends all four. Validating
   * *this* shape rather than the raw form state is what keeps the draft check honest:
   * a stale value left in state by a mode switch is never sent, so it must not be
   * validated either.
   */
  const effectiveJudge =
    judgeMode === 'same'
      ? { provider: '', model: '', apiKey: '', baseUrl: '' }
      : judgeMode === 'other-model'
        ? { provider: '', model: judgeConfig.model, apiKey: '', baseUrl: '' }
        : judgeConfig;

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
    judgeProvider: effectiveJudge.provider,
    judgeModel: effectiveJudge.model,
    judgeApiKey: effectiveJudge.apiKey,
    judgeBaseUrl: effectiveJudge.baseUrl,
  };

  // Recomputed on every render, never stored: an error disappears the moment the value
  // that caused it is fixed, instead of when some handler remembers to clear it.
  const draftIssues: DraftIssue[] = (() => {
    const parsed = llmConfigDraftSchema.safeParse(draftToValidate);
    const issues: DraftIssue[] = parsed.success
      ? []
      : parsed.error.issues.map((issue) => ({
          field: String(issue.path[0] ?? ''),
          code: issue.message as LLMConfigIssueCode,
        }));
    // The modes' own completeness rule (S11): a mode that names its fields must have
    // them filled. The credential stays a warning, not a gate — the run is what
    // refuses a cross-provider judge without one, never the form (D9).
    const modeRequired: string[] =
      judgeMode === 'other-model'
        ? ['judgeModel']
        : judgeMode === 'other-provider'
          ? ['judgeProvider', 'judgeModel']
          : [];
    for (const field of modeRequired) {
      const value = draftToValidate[field as keyof typeof draftToValidate];
      if (typeof value === 'string' && value.trim() === '') {
        issues.push({ field, code: 'required' });
      }
    }
    return issues;
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
    judgeProvider: t.settings?.llm_judge_provider ?? 'Judge provider',
    judgeModel: t.settings?.llm_judge_model ?? 'Judge model',
    judgeApiKey: t.settings?.llm_judge_api_key ?? 'Judge API key',
    judgeBaseUrl: t.settings?.llm_judge_base_url ?? 'Judge Base URL',
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
      const llm = await getLLMConfig(workspaceId).catch((err) => {
        if (
          err instanceof Error &&
          (err.message.includes('403') || err.message.includes('admin'))
        ) {
          return null;
        }
        throw err;
      });

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
        const loadedJudge = {
          provider: llm.judgeProvider ?? '',
          model: llm.judgeModel ?? '',
          apiKey: llm.judgeApiKey ?? '',
          baseUrl: llm.judgeBaseUrl ?? '',
        };
        setJudgeConfig(loadedJudge);
        // The mode is derived from the row, never stored: it is how the four persisted
        // fields read back as one of the three stated relationships.
        setJudgeMode(deriveJudgeMode(loadedJudge));
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.workspace?.loadError ?? 'Failed to load settings');
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, t.workspace]);

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
    // provider left behind are not its values. The judge block is not touched: it is
    // a second, independent configuration under D9, and registering an extraction
    // provider says nothing about how the judge should run.
    setLlmConfig((prev) => ({ ...prev, provider: saved.name, model: '', apiKey: '', baseUrl: '' }));
    setAvailableModels([]);
    setModelsError(null);
    setCustomModelsProbed(false);
  };

  /* ── Judge Mode Switch ── */
  const handleJudgeModeChange = (mode: JudgeMode) => {
    setJudgeMode(mode);
    if (mode === 'other-model') {
      // Dropping a judge that ran on its own provider: the model can carry over (it is
      // the part this mode keeps), but the provider, its credential and its endpoint
      // are not this mode's values — the same non-portability rule the provider
      // switches follow.
      setJudgeConfig((prev) =>
        prev.provider === '' && prev.apiKey === '' && prev.baseUrl === ''
          ? prev
          : { ...prev, provider: '', apiKey: '', baseUrl: '' },
      );
    }
    // 'same' leaves the values in place: nothing is sent from them (the mode maps all
    // four to the empty string), and switching back restores what was on screen.
  };

  /* ── LLM Save Handler ── */
  const handleLLMSave = async () => {
    const parsed = llmConfigDraftSchema.safeParse(draftToValidate);

    if (!parsed.success || draftIssues.length > 0) {
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
        // The four judge fields always travel explicitly, unlike the siblings above:
        // the payload keeps a stored value when its key is omitted (D9), so the
        // explicit empty string is the only way the form can clear one. The mode has
        // already mapped them (`effectiveJudge`): same model sends all four empty,
        // another model sends `judge_model` only, another provider sends all four.
        // The judge endpoint trims like the extraction one, but stays an explicit
        // string so a blank field clears the stored endpoint instead of keeping it.
        judgeProvider: parsed.data.judgeProvider ?? '',
        judgeModel: parsed.data.judgeModel ?? '',
        judgeApiKey: parsed.data.judgeApiKey ?? '',
        judgeBaseUrl: (parsed.data.judgeBaseUrl ?? '').trim(),
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
      <div className="flex items-center gap-3 rounded-lg border border-(--color-destructive-border) bg-(--color-destructive-bg) p-4">
        <TriangleAlert className="h-5 w-5 shrink-0 text-destructive" />
        <div>
          <p className="text-sm font-medium text-(--color-destructive-text)">{error}</p>
          <button
            type="button"
            onClick={loadConfigs}
            className="mt-1 text-sm text-destructive underline hover:text-(--color-destructive-text)"
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

  // The one cross-provider combination D9 classifies as incomplete: a judge on a
  // provider other than the extraction's, without a credential of its own and with
  // no default-free provider (Ollama needs none). The save still goes through — the
  // refusal is the backend's, as a judged failure — so this is a warning, not a gate.
  // A custom provider is complete with an endpoint and no key (its
  // ``required_fields_for`` asks for model and base URL only), so the warning must
  // not fire for it: the endpoint check is what keeps this hint aligned with the
  // backend's readiness rule instead of guessing a stricter one.
  const judgeNeedsOwnCredential =
    judgeConfig.provider !== '' &&
    judgeConfig.provider !== llmConfig.provider &&
    judgeConfig.provider !== 'ollama' &&
    judgeConfig.apiKey.trim() === '' &&
    judgeConfig.baseUrl.trim() === '';

  /* ── The three judge modes (S11), as the radio offers them ── */
  const judgeModeOptions: Array<{
    value: JudgeMode;
    title: string;
    description: string;
  }> = [
    {
      value: 'same',
      title: t.settings?.llm_judge_mode_same ?? 'Same model as extraction',
      description:
        t.settings?.llm_judge_mode_same_desc ??
        'The judge uses the extraction model, provider and credential.',
    },
    {
      value: 'other-model',
      title: t.settings?.llm_judge_mode_other_model ?? 'Another model of this provider',
      description:
        t.settings?.llm_judge_mode_other_model_desc ??
        'The judge uses another model from the extraction provider, with the same credential.',
    },
    {
      value: 'other-provider',
      title: t.settings?.llm_judge_mode_other_provider ?? 'Another provider with its own credential',
      description:
        t.settings?.llm_judge_mode_other_provider_desc ??
        'The judge runs on another provider, with its own model, credential and endpoint.',
    },
  ];

  return (
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
      <CardContent className="max-w-3xl space-y-5">
        {/* The workspace's readiness, stated before anything is attempted. Shown
            while the values on screen cannot extract — which is what makes a fresh
            workspace explain itself here instead of only after a refused save. */}
        {missingFields.length > 0 && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-lg border border-(--color-destructive-border) bg-(--color-destructive-bg) p-3"
          >
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-(--color-destructive-text)">
                {t.workspace?.llmMissingSummaryTitle ??
                  'This workspace cannot extract tasks yet'}
              </p>
              <p className="text-sm text-(--color-destructive-text)">
                {t.workspace?.llmMissingSummaryDesc ??
                  'Complete these fields to enable extraction:'}
              </p>
              <ul className="list-disc pl-5 text-sm text-(--color-destructive-text)">
                {missingFields.map((field) => (
                  <li key={field}>{labelFor(READINESS_FIELD_TO_FORM_KEY[field])}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* ── 1. Connection — the workspace's own provider, credential and endpoint.
               Titled "Conexión" because the field right below it is already
               labelled "Proveedor": a heading that repeats its own first label
               reads as a rendering mistake. ── */}
        <p className="text-sm font-medium text-(--color-text-secondary)">
          {t.settings?.llm_section_connection ?? 'Connection'}
        </p>

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
                  // model id and an API key are not portable between endpoints. The
                  // judge block is deliberately untouched here: its provider,
                  // credential and endpoint are independent under D9, and changing
                  // how the workspace extracts says nothing about how it judges.
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

        {/* ── 2. Extraction — model, temperature, max tokens ── */}
        <p className="text-sm font-medium text-(--color-text-secondary)">
          {t.settings?.llm_section_extraction ?? 'Extraction'}
        </p>

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
                <span className="flex items-center gap-1.5 text-(--color-warning-text)">
                  <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                  {modelsError}
                </span>
              ) : customModelsProbed && availableModels.length === 0 ? (
                <span className="flex items-center gap-1.5 text-(--color-warning-text)">
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
              <span className="flex items-center gap-1.5 text-(--color-warning-text)">
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
              <span className="flex items-center gap-1.5 text-(--color-warning-text)">
                <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                {t.workspace?.llmModelNotInList ??
                  "The saved model is not in the provider's model list."}
              </span>
            ) : modelListUnavailable ? (
              <span className="flex items-center gap-1.5 text-(--color-warning-text)">
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

        {/* ── 3. Judge (D9/S10/S11) ──
            A second, independent LLM configuration, stated as one of three explicit
            modes instead of four peer fields. No probe or test button here: the first
            judged run is the probe, and a bad judge configuration fails as a judged
            failure. */}
        <div className="space-y-4 rounded-lg border border-(--color-border) p-4">
          <div className="flex items-start gap-2">
            <Gavel className="mt-0.5 h-4 w-4 shrink-0 text-(--color-text-secondary)" />
            <div className="space-y-1">
              {/* The group's visible label: the radio group points at it, so the
                  three options are announced as one choice, not three loose radios. */}
              <p className="text-sm font-medium" id="llm-judge-mode-label">
                {t.settings?.llm_judge_title ?? 'Judge configuration'}
              </p>
              <p className="text-sm text-(--color-text-secondary)">
                {t.settings?.llm_judge_description ??
                  'How the judge relates to the extraction configuration:'}
              </p>
            </div>
          </div>

          {/* One accessible radio group; the option labels carry the meaning, so the
              mode is stated outright instead of implied by empty fields. */}
          <RadioGroup
            value={judgeMode}
            onValueChange={(value) => {
              if (typeof value === 'string') handleJudgeModeChange(value as JudgeMode);
            }}
            aria-labelledby="llm-judge-mode-label"
            className="gap-3"
          >
            {judgeModeOptions.map((option) => (
              <div key={option.value} className="flex items-start gap-3">
                <RadioGroupItem
                  id={`llm-judge-mode-${option.value}`}
                  value={option.value}
                  className="mt-0.5"
                />
                <div className="space-y-0.5">
                  <label
                    htmlFor={`llm-judge-mode-${option.value}`}
                    className="block cursor-pointer text-sm font-medium"
                  >
                    {option.title}
                  </label>
                  <p className="text-sm text-(--color-text-secondary)">{option.description}</p>
                </div>
              </div>
            ))}
          </RadioGroup>

          {/* Only the fields the chosen mode needs are on the page; each keeps its
              `<FieldLabel htmlFor>`/id pairing, and the ids survive the restructure
              because tests and API references address them by name. */}
          {judgeMode === 'other-model' && (
            /* Judge model — selection-only, fed by the extraction provider's own
               model list: the mode is "another model of this provider", so the list
               the extraction side already probed is exactly the right catalogue. */
            <Field>
              <FieldLabel htmlFor="llm-judge-model">
                {t.settings?.llm_judge_model ?? 'Judge model'}
              </FieldLabel>
              <Combobox
                key={`judge-model-${llmConfig.provider}`}
                value={judgeConfig.model || null}
                onValueChange={(val) => {
                  if (val !== null && val !== undefined) {
                    setJudgeConfig((prev) => ({ ...prev, model: String(val) }));
                  }
                }}
              >
                <ComboboxInput
                  id="llm-judge-model"
                  readOnly
                  placeholder={t.settings?.llm_model_placeholder ?? 'Select a model'}
                />
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
                    <ComboboxEmpty>{modelsError ? modelsError : noModelsMessage}</ComboboxEmpty>
                  ) : null}
                </ComboboxContent>
              </Combobox>
              <FieldDescription>
                {t.settings?.llm_judge_model_from_list_desc ??
                  "Picked from the extraction provider's model list, with the same credential."}
              </FieldDescription>
              {fieldErrorFor('judgeModel')}
            </Field>
          )}

          {judgeMode === 'other-provider' && (
            <>
              {/* A warning, not a gate: saving is allowed, and the first judged run is
                  what reports an incomplete judge configuration. */}
              {judgeNeedsOwnCredential && (
                <div
                  role="status"
                  className="flex items-start gap-2 rounded-lg border border-(--color-warning-border) bg-(--color-warning-bg) p-3"
                >
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-(--color-warning-text)" />
                  <p className="text-sm text-(--color-warning-text)">
                    {t.workspace?.llmJudgeCredentialWarn ??
                      'The judge will need its own credential: a key for one provider is never sent to another.'}
                  </p>
                </div>
              )}

              {/* Judge provider */}
              <Field>
                <FieldLabel htmlFor="llm-judge-provider">
                  {t.settings?.llm_judge_provider ?? 'Judge provider'}
                </FieldLabel>
                <Select
                  value={judgeConfig.provider === '' ? undefined : judgeConfig.provider}
                  onValueChange={(val) => {
                    if (val === null) return;
                    // Switching to another provider follows the same invariant the
                    // extraction provider switch applies: a model id, a credential and
                    // an endpoint are not portable between providers, so the values the
                    // previous one owned are dropped. The reset is the visible state of
                    // the fields themselves, never a silent one.
                    setJudgeConfig((prev) =>
                      prev.provider === val
                        ? prev
                        : { provider: val, model: '', apiKey: '', baseUrl: '' },
                    );
                  }}
                >
                  <SelectTrigger id="llm-judge-provider" className="w-full">
                    <div className="flex items-center gap-2">
                      {judgeConfig.provider !== '' && (
                        <ProviderIcon
                          provider={judgeConfig.provider}
                          theme={resolvedTheme}
                          className="h-4 w-4 shrink-0"
                          aria-hidden="true"
                        />
                      )}
                      <span>
                        {judgeConfig.provider === ''
                          ? (t.settings?.llm_judge_provider_placeholder ?? 'Select a provider')
                          : providerLabel(judgeConfig.provider)}
                      </span>
                    </div>
                  </SelectTrigger>
                  <SelectContent>
                    {/* The same provider options the extraction select offers, minus
                        the add and rename controls: those belong to the extraction
                        selection, and "same as extraction" is the radio's first mode,
                        not an option inside this one. */}
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
                        <ProviderIcon
                          provider={name}
                          theme={resolvedTheme}
                          className="mr-2 h-4 w-4 shrink-0"
                          aria-hidden="true"
                        />
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription>
                  {t.workspace?.llmJudgeProviderDesc ??
                    'The provider the judge calls. Its credential is configured below, never borrowed from the extraction.'}
                </FieldDescription>
                {fieldErrorFor('judgeProvider')}
              </Field>

              {/* Judge model — free text: no probe path for the judge on another
                  provider, and a model id typed once is exactly what the run sends. */}
              <Field>
                <FieldLabel htmlFor="llm-judge-model">
                  {t.settings?.llm_judge_model ?? 'Judge model'}
                </FieldLabel>
                <Input
                  id="llm-judge-model"
                  type="text"
                  value={judgeConfig.model}
                  onChange={(e) => setJudgeConfig((prev) => ({ ...prev, model: e.target.value }))}
                />
                <FieldDescription>
                  {t.workspace?.llmJudgeModelDesc ??
                    'The model id the judge provider expects, for example gpt-4o-mini.'}
                </FieldDescription>
                {fieldErrorFor('judgeModel')}
              </Field>

              {/* Judge credential — masked like the extraction key, the convention it
                  already follows: it loads back into the field but never renders in
                  clear text. */}
              <Field>
                <FieldLabel htmlFor="llm-judge-api-key">
                  {t.settings?.llm_judge_api_key ?? 'Judge API key'}
                </FieldLabel>
                <Input
                  id="llm-judge-api-key"
                  type="password"
                  value={judgeConfig.apiKey}
                  onChange={(e) => setJudgeConfig((prev) => ({ ...prev, apiKey: e.target.value }))}
                  placeholder="sk-..."
                />
                <FieldDescription>
                  {t.workspace?.llmJudgeApiKeyDesc ??
                    'The credential the judge uses when it runs on another provider. It is stored with this workspace on the server, like the extraction key.'}
                </FieldDescription>
                {fieldErrorFor('judgeApiKey')}
              </Field>

              {/* Judge endpoint */}
              <Field>
                <FieldLabel htmlFor="llm-judge-base-url">
                  {t.settings?.llm_judge_base_url ?? 'Judge Base URL'}
                </FieldLabel>
                <Input
                  id="llm-judge-base-url"
                  type="text"
                  value={judgeConfig.baseUrl}
                  onChange={(e) => setJudgeConfig((prev) => ({ ...prev, baseUrl: e.target.value }))}
                  placeholder="https://api.example.com/v1"
                />
                <FieldDescription>
                  {t.workspace?.llmJudgeBaseUrlDesc ??
                    "Optional. Leave empty to use the provider's default endpoint, or the extraction endpoint when the judge uses the same provider."}
                </FieldDescription>
                {fieldErrorFor('judgeBaseUrl')}
              </Field>
            </>
          )}
        </div>

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

      <CustomProviderDialog
        locale={locale}
        workspaceId={workspaceId}
        provider={providerDialogTarget}
        open={providerDialogOpen}
        onOpenChange={setProviderDialogOpen}
        onSaved={handleProviderSaved}
      />
    </Card>
  );
}
