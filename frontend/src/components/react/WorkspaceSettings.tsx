import { useState, useEffect, useCallback, useMemo } from "react";
import { useUIStore } from "@/stores/uiStore";
import {
  Bot,
  FileText,
  Check,
  X,
  LoaderCircle,
  Users,
  Settings,
  TriangleAlert,
  FlaskConical,
  RotateCw,
  CircleHelp,
} from "lucide-react";
import { toast } from "sonner";
import { getLLMConfig, upsertLLMConfig, fetchAvailableModels } from "@/lib/llm-config-api";
import type { AvailableModel } from "@/lib/llm-config-api";
import { getPrompts, upsertPrompts } from "@/lib/prompts-api";
import { Button } from "@/components/ui/button";
import {
  Combobox,
  ComboboxInput,
  ComboboxContent,
  ComboboxList,
  ComboboxItem,
  ComboboxEmpty,
} from "@/components/ui/combobox";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import {
  Field,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { MemberManagement } from "@/components/react/MemberManagement";
import type { WorkspaceLLMConfig, WorkspacePrompt } from "@/types/workspace";
import { IconPicker, IconTrigger } from "@/components/ui/icon-picker";
import * as workspaceApi from "@/lib/workspace-api";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import en from "@/i18n/en.json";
import es from "@/i18n/es.json";
import { type Locale } from "@/i18n/utils";
import { ProviderIcon } from "@/components/ui/provider-icon";

/* ── Props ─────────────────────────────────────────────────── */

interface WorkspaceSettingsProps {
  locale: Locale;
  workspaceId: string;
}

/* ── WorkspaceSettings Component ────────────────────────────── */

export function WorkspaceSettings({
  locale,
  workspaceId,
}: WorkspaceSettingsProps) {
  const t = locale === "es" ? es : en;
  const { theme: rawTheme } = useUIStore();
  const resolvedTheme: "light" | "dark" =
    rawTheme === "system"
      ? typeof window !== "undefined"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : "light"
      : rawTheme;

  /* ── LLM Config State ── */
  const [llmConfig, setLlmConfig] = useState<WorkspaceLLMConfig>({
    provider: "ollama",
    model: "",
    temperature: 0.1,
    maxTokens: 2048,
    baseUrl: "http://localhost:11434",
    apiKey: "",
  });
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmSaveResult, setLlmSaveResult] = useState<
    "idle" | "success" | "error"
  >("idle");

  /* ── Prompt Config State ── */
  const [prompts, setPrompts] = useState<WorkspacePrompt>({
    systemPrompt: "",
    instructionTemplate: "",
  });
  const [promptSaving, setPromptSaving] = useState(false);
  const [promptSaveResult, setPromptSaveResult] = useState<
    "idle" | "success" | "error"
  >("idle");

  /* ── Available Models State ── */
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);

  const searchTerm = llmConfig.model?.toLowerCase() ?? "";
  const filteredModels = useMemo(
    () =>
      searchTerm
        ? availableModels.filter((m) => m.name.toLowerCase().includes(searchTerm))
        : availableModels,
    [availableModels, searchTerm],
  );

  /* ── Workspace Info State ── */
  const [wsName, setWsName] = useState("");
  const [wsIcon, setWsIcon] = useState("building-2");
  const [wsRole, setWsRole] = useState<"admin" | "member">("member");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [infoSaving, setInfoSaving] = useState(false);

  /* ── Shared State ── */
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  /* ── Fetch Configs ── */
  const loadConfigs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ws, llm, promptData] = await Promise.all([
        workspaceApi.getWorkspace(workspaceId).catch((err) => {
          // If 403, still allow viewing other configs
          if (
            err instanceof Error &&
            (err.message.includes("403") || err.message.includes("admin"))
          ) {
            return null;
          }
          throw err;
        }),
        getLLMConfig(workspaceId).catch((err) => {
          // If 403, the user is not admin — we still allow viewing prompts
          if (
            err instanceof Error &&
            (err.message.includes("403") || err.message.includes("admin"))
          ) {
            return null;
          }
          throw err;
        }),
        getPrompts(workspaceId).catch((err) => {
          if (
            err instanceof Error &&
            (err.message.includes("403") || err.message.includes("admin"))
          ) {
            return null;
          }
          throw err;
        }),
      ]);

      if (llm) {
        setLlmConfig({
          provider: llm.provider || "ollama",
          model: llm.model ?? "",
          temperature: llm.temperature ?? 0.1,
          maxTokens: llm.maxTokens ?? 2048,
          baseUrl: llm.baseUrl ?? "http://localhost:11434",
          apiKey: llm.apiKey ?? "",
        });
      }
      if (promptData) {
        setPrompts({
          systemPrompt: promptData.systemPrompt ?? "",
          instructionTemplate: promptData.instructionTemplate ?? "",
        });
      }
      if (ws) {
        setWsName(ws.name ?? "");
        setWsIcon(ws.icon ?? "building-2");
        setWsRole(ws.role ?? "member");
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.workspace?.loadError ?? "Failed to load settings");
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  /* ── Fetch Available Models ── */
  const loadModels = useCallback(async () => {
    setModelsLoading(true);
    setModelsError(null);
    try {
      const models = await fetchAvailableModels(workspaceId);
      setAvailableModels(models);
    } catch (err) {
      setAvailableModels([]);
      const msg = err instanceof Error ? err.message : String(err);
      // Surface provider errors (bad API key, wrong URL) so the user knows
      // it's a config issue, not a system failure.
      if (msg.includes("502") || msg.includes("Failed to fetch")) {
        setModelsError(t.workspace?.llmModelsFetchError
          ?? "Could not reach the provider. Check your API key and Base URL.");
      } else {
        setModelsError(msg);
      }
    } finally {
      setModelsLoading(false);
    }
  }, [workspaceId, t]);

  useEffect(() => {
    setMounted(true);
    loadConfigs();
  }, [loadConfigs]);

  // Auto-fetch models when provider changes (only after initial load)
  useEffect(() => {
    if (!mounted) return;
    loadModels();
  }, [loadModels, llmConfig.provider, mounted]);

  /* ── LLM Save Handler ── */
  const handleLLMSave = async () => {
    setLlmSaving(true);
    setLlmSaveResult("idle");
    try {
      await upsertLLMConfig(workspaceId, {
        provider: llmConfig.provider,
        model: llmConfig.model || undefined,
        temperature: llmConfig.temperature ?? undefined,
        maxTokens: llmConfig.maxTokens ?? undefined,
        baseUrl: llmConfig.baseUrl || undefined,
        apiKey: llmConfig.apiKey || undefined,
      });
      setLlmSaveResult("success");
      toast.success(t.settings?.llm_saved ?? "LLM configuration saved");
      setTimeout(() => setLlmSaveResult("idle"), 3000);
    } catch (err) {
      setLlmSaveResult("error");
      const message =
        err instanceof Error ? err.message : (t.workspace?.llmSaveError ?? "Failed to save LLM config");
      toast.error(message);
      setTimeout(() => setLlmSaveResult("idle"), 3000);
    } finally {
      setLlmSaving(false);
    }
  };

  /* ── Prompt Save Handler ── */
  const handlePromptSave = async () => {
    setPromptSaving(true);
    setPromptSaveResult("idle");
    try {
      await upsertPrompts(workspaceId, {
        systemPrompt: prompts.systemPrompt || undefined,
        instructionTemplate: prompts.instructionTemplate || undefined,
      });
      setPromptSaveResult("success");
      toast.success(t.workspace?.promptSaved ?? "Prompt configuration saved");
      setTimeout(() => setPromptSaveResult("idle"), 3000);
    } catch (err) {
      setPromptSaveResult("error");
      const message =
        err instanceof Error ? err.message : (t.workspace?.promptSaveError ?? "Failed to save prompts");
      toast.error(message);
      setTimeout(() => setPromptSaveResult("idle"), 3000);
    } finally {
      setPromptSaving(false);
    }
  };

  /* ── Workspace Info Save Handler ── */
  const handleInfoSave = async () => {
    setInfoSaving(true);
    try {
      await useWorkspaceStore.getState().updateWorkspace(workspaceId, {
        name: wsName || undefined,
        icon: wsIcon !== "building-2" ? wsIcon : undefined,
      });
      toast.success(t.workspace?.savedInfo ?? "Workspace updated");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.workspace?.saveInfoError ?? "Failed to update workspace");
      toast.error(message);
    } finally {
      setInfoSaving(false);
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

  /* ── Render ── */
  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-semibold text-(--color-text)">
          {t.workspace?.settingsTitle ?? "Workspace Settings"}
        </h1>
        <p className="mt-1 text-sm text-(--color-text-secondary)">
          {t.workspace?.settingsDescription ?? "Configure LLM, prompts, and manage team members for this workspace."}
        </p>
      </div>

      {/* ── Section 1: General (Workspace Info) ── */}
      {!loading && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Settings className="h-4 w-4 text-(--color-text-secondary)" />
              <CardTitle className="text-base">{t.workspace?.infoTitle ?? "General"}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <IconTrigger
                value={wsIcon}
                onClick={() => setPickerOpen(true)}
                locale={locale}
              />
              <Input
                id="ws-name"
                value={wsName}
                onChange={(e) => setWsName(e.target.value)}
                placeholder={t.workspace?.namePlaceholder ?? "e.g. My Team"}
                disabled={wsRole !== "admin"}
                className="flex-1"
              />
              <Button
                onClick={handleInfoSave}
                disabled={infoSaving || wsRole !== "admin"}
                size="sm"
              >
                {infoSaving ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
                {t.common?.save ?? "Save"}
              </Button>
            </div>

            {wsRole !== "admin" && (
              <p className="mt-2 text-xs text-(--color-text-tertiary)">
                {t.workspace?.infoNonAdminHint ?? "Only admins can edit workspace settings."}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Icon Picker dialog */}
      <IconPicker
        value={wsIcon}
        onChange={setWsIcon}
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        locale={locale}
      />

      {loading ? (
        <div className="flex items-center gap-2 py-12 text-sm text-(--color-text-secondary)">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          {t.workspace?.loading ?? "Loading settings..."}
        </div>
      ) : error ? (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
          <TriangleAlert className="h-5 w-5 shrink-0 text-red-500" />
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-200">
              {error}
            </p>
            <button
              type="button"
              onClick={loadConfigs}
              className="mt-1 text-sm text-red-600 underline hover:text-red-800 dark:text-red-400 dark:hover:text-red-200"
            >
              {t.workspace?.tryAgain ?? "Try again"}
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* Two-column grid: LLM Config + Prompt Config */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* ── Section 1: LLM Configuration ── */}
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-(--color-text-secondary)" />
                  <CardTitle>{t.settings?.llm_title ?? "LLM Configuration"}</CardTitle>
                </div>
                <CardDescription>
                  {t.settings?.llm_description ?? "Configure the AI model used for task extraction in this workspace"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {/* Provider */}
                <Field>
                  <FieldLabel htmlFor="llm-provider">{t.settings?.llm_provider ?? "Provider"}</FieldLabel>
                  <Select
                    value={llmConfig.provider}
                    onValueChange={(val) => {
                      if (val === null) return;
                      setLlmConfig((prev) => ({
                        ...prev,
                        provider: val,
                        model: "",
                        apiKey: "",
                        baseUrl: val === "ollama" ? "http://localhost:11434" : "",
                      }));
                    }}
                  >
                    <SelectTrigger id="llm-provider" className="w-full">
                      <div className="flex items-center gap-2">
                        <ProviderIcon provider={llmConfig.provider} theme={resolvedTheme} className="h-4 w-4 shrink-0" />
                        <span>
                          {llmConfig.provider === "ollama"
                            ? (t.settings?.llm_provider_ollama ?? "Ollama (Local)")
                            : llmConfig.provider === "openai"
                              ? (t.settings?.llm_provider_openai ?? "OpenAI")
                              : (t.settings?.llm_provider_anthropic ?? "Anthropic")}
                        </span>
                      </div>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ollama">
                        <ProviderIcon provider="ollama" theme={resolvedTheme} className="mr-2 h-4 w-4 shrink-0" />
                        {t.settings?.llm_provider_ollama ?? "Ollama (Local)"}
                      </SelectItem>
                      <SelectItem value="openai">
                        <ProviderIcon provider="openai" theme={resolvedTheme} className="mr-2 h-4 w-4 shrink-0" />
                        {t.settings?.llm_provider_openai ?? "OpenAI"}
                      </SelectItem>
                      <SelectItem value="anthropic">
                        <ProviderIcon provider="anthropic" theme={resolvedTheme} className="mr-2 h-4 w-4 shrink-0" />
                        {t.settings?.llm_provider_anthropic ?? "Anthropic"}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <FieldDescription>
                    {t.workspace?.llmProviderDesc ?? "The AI model provider for task extraction."}
                  </FieldDescription>
                </Field>

                {/* Model — Combobox with auto-populated suggestions */}
                <Field>
                  <FieldLabel htmlFor="llm-model">{t.settings?.llm_ollama_model ?? "Model"}</FieldLabel>
                  <div className="flex items-start gap-2">
                    <div className="flex-1">
                      {/* key=provider forces remount when switching; controlled inputValue avoids React warning */}
                      <Combobox
                        key={`model-${llmConfig.provider}`}
                        inputValue={llmConfig.model ?? ""}
                        onValueChange={(val) => {
                          if (val !== null && val !== undefined) {
                            setLlmConfig((prev) => ({ ...prev, model: String(val) }));
                          }
                        }}
                        onInputValueChange={(inputVal) => {
                          setLlmConfig((prev) => ({ ...prev, model: inputVal }));
                        }}
                      >
                        <ComboboxInput
                          id="llm-model"
                          disabled={llmConfig.provider !== "ollama" && !llmConfig.apiKey}
                          placeholder={
                            llmConfig.provider === "ollama"
                              ? (t.settings?.llm_ollama_model_placeholder ?? "llama3.2, mistral")
                              : llmConfig.provider === "openai"
                                ? (t.settings?.llm_openai_model_placeholder ?? "gpt-4o-mini")
                                : (t.settings?.llm_anthropic_model_placeholder ?? "claude-3-haiku")
                          }
                        />
                        <ComboboxContent>
                          <ComboboxList>
                            {filteredModels.map((m) => (
                              <ComboboxItem key={m.id} value={m.id}>
                                {m.name}
                              </ComboboxItem>
                            ))}
                          </ComboboxList>
                          {modelsLoading ? (
                            <ComboboxEmpty>
                              {t.workspace?.llmModelsLoading ?? "Loading models..."}
                            </ComboboxEmpty>
                          ) : filteredModels.length === 0 ? (
                            <ComboboxEmpty>
                              {modelsError
                                ? modelsError
                                : (t.workspace?.llmModelsEmpty ?? "No models found. Type a custom name.")}
                            </ComboboxEmpty>
                          ) : null}
                        </ComboboxContent>
                      </Combobox>
                    </div>
                    <div className="relative">
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={loadModels}
                        disabled={
                          modelsLoading ||
                          (llmConfig.provider !== "ollama" && !llmConfig.apiKey)
                        }
                        title={
                          llmConfig.provider !== "ollama" && !llmConfig.apiKey
                            ? (t.workspace?.llmModelsNoApiKey ?? "Add your API key first")
                            : (t.workspace?.llmRefreshModels ?? "Refresh models")
                        }
                      >
                        <RotateCw
                          className={`h-4 w-4 ${modelsLoading ? "animate-spin" : ""}`}
                        />
                      </Button>
                    </div>
                  </div>
                  <FieldDescription>
                    {modelsError ? (
                      <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                        <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                        {modelsError}
                      </span>
                    ) : llmConfig.provider !== "ollama" && !llmConfig.apiKey ? (
                      <span className="flex items-center gap-1.5 text-(--color-text-tertiary)">
                        <CircleHelp className="h-3.5 w-3.5 shrink-0" />
                        {t.workspace?.llmModelsNoApiKey ?? "Add your API key and save to enable model suggestions."}
                      </span>
                    ) : (
                      t.workspace?.llmModelDesc ?? "The model name to use for task extraction."
                    )}
                  </FieldDescription>
                </Field>

                {/* Temperature */}
                <Field>
                  <FieldLabel htmlFor="llm-temperature">{t.settings?.llm_temperature ?? "Temperature"}</FieldLabel>
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
                    {t.workspace?.llmTemperatureDesc ?? "Lower values = more consistent output. Higher values = more creative."}
                  </FieldDescription>
                </Field>

                {/* Max Tokens */}
                <Field>
                  <FieldLabel htmlFor="llm-max-tokens">{t.settings?.llm_max_tokens ?? "Max Tokens"}</FieldLabel>
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
                    {t.workspace?.llmMaxTokensDesc ?? "Maximum number of tokens the model can generate per response."}
                  </FieldDescription>
                </Field>

                {/* ── Provider-specific fields ── */}
                {llmConfig.provider === "ollama" ? (
                  /* Base URL — required for Ollama */
                  <Field>
                    <FieldLabel htmlFor="llm-base-url">
                      {t.settings?.llm_base_url ?? "Base URL"}
                    </FieldLabel>
                    <Input
                      id="llm-base-url"
                      type="text"
                      value={llmConfig.baseUrl ?? ""}
                      onChange={(e) =>
                        setLlmConfig((prev) => ({
                          ...prev,
                          baseUrl: e.target.value,
                        }))
                      }
                      placeholder="http://localhost:11434"
                    />
                    <FieldDescription>
                      {t.workspace?.llmBaseUrlDesc ?? "The URL where your Ollama instance is running."}
                    </FieldDescription>
                  </Field>
                ) : (
                  <>
                    {/* API Key — required for cloud providers */}
                    <Field>
                      <FieldLabel htmlFor="llm-api-key">
                        {llmConfig.provider === "openai"
                          ? (t.settings?.llm_openai_api_key ?? "API Key")
                          : (t.settings?.llm_anthropic_api_key ?? "API Key")}
                      </FieldLabel>
                      <Input
                        id="llm-api-key"
                        type="password"
                        value={llmConfig.apiKey ?? ""}
                        onChange={(e) =>
                          setLlmConfig((prev) => ({
                            ...prev,
                            apiKey: e.target.value,
                          }))
                        }
                        placeholder={
                          llmConfig.provider === "openai" ? "sk-..." : "sk-ant-..."
                        }
                      />
                      <FieldDescription>
                        {t.workspace?.llmApiKeyDesc ??
                          "Your API key for this provider. Stored encrypted at rest."}
                      </FieldDescription>
                    </Field>

                    {/* Base URL — optional for cloud providers (proxy/custom endpoint) */}
                    <Field>
                      <FieldLabel htmlFor="llm-base-url">
                        {t.settings?.llm_base_url ?? "Base URL"}
                      </FieldLabel>
                      <Input
                        id="llm-base-url"
                        type="text"
                        value={llmConfig.baseUrl ?? ""}
                        onChange={(e) =>
                          setLlmConfig((prev) => ({
                            ...prev,
                            baseUrl: e.target.value,
                          }))
                        }
                        placeholder={
                          llmConfig.provider === "openai"
                            ? "https://api.openai.com/v1"
                            : "https://api.anthropic.com"
                        }
                      />
                      <FieldDescription>
                        {t.workspace?.llmBaseUrlCloudDesc ??
                          "Optional. Leave empty to use the default API endpoint."}
                      </FieldDescription>
                    </Field>
                  </>
                )}

                {/* Save Button */}
                <div className="flex items-center gap-3 pt-1">
                  <Button
                    onClick={handleLLMSave}
                    disabled={llmSaving}
                    className="w-full sm:w-auto"
                  >
                    {llmSaving ? (
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                    ) : llmSaveResult === "success" ? (
                      <Check className="h-4 w-4" />
                    ) : llmSaveResult === "error" ? (
                      <X className="h-4 w-4" />
                    ) : null}
                    {llmSaveResult === "success"
                      ? (t.workspace?.llmSaved ?? "Saved")
                      : (t.settings?.llm_save ?? "Save LLM Configuration")}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* ── Section 2: Prompt Configuration ── */}
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-(--color-text-secondary)" />
                  <CardTitle>{t.workspace?.promptTitle ?? "Prompt Configuration"}</CardTitle>
                </div>
                <CardDescription>
                  {t.workspace?.promptDescription ?? "Customize the prompts used for task extraction in this workspace"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {/* System Prompt */}
                <Field>
                  <FieldLabel htmlFor="system-prompt">{t.workspace?.systemPrompt ?? "System Prompt"}</FieldLabel>
                  <Textarea
                    id="system-prompt"
                    rows={8}
                    className="min-h-[11rem] w-full resize-y"
                    value={prompts.systemPrompt ?? ""}
                    onChange={(e) =>
                      setPrompts((prev) => ({
                        ...prev,
                        systemPrompt: e.target.value,
                      }))
                    }
                    placeholder={t.workspace?.systemPromptPlaceholder ?? "You are an expert software development lead who excels at breaking down user stories into clear, actionable development tasks."}
                  />
                  <FieldDescription>
                    {t.workspace?.systemPromptDesc ?? "The system-level instruction that sets the AI's role and behavior"}
                  </FieldDescription>
                </Field>

                {/* Instruction Template */}
                <Field>
                  <FieldLabel htmlFor="instruction-template">
                    {t.workspace?.instructionTemplate ?? "Instruction Template"}
                  </FieldLabel>
                  <Textarea
                    id="instruction-template"
                    rows={12}
                    className="min-h-[16rem] w-full resize-y"
                    value={prompts.instructionTemplate ?? ""}
                    onChange={(e) =>
                      setPrompts((prev) => ({
                        ...prev,
                        instructionTemplate: e.target.value,
                      }))
                    }
                    placeholder={t.workspace?.instructionTemplatePlaceholder ?? "Break this user story into smaller development tasks..."}
                  />
                  <FieldDescription>
                    {t.workspace?.instructionTemplateDesc ?? "The instruction prompt with format guidelines and few-shot examples"}
                  </FieldDescription>
                </Field>

                {/* Few-Shot Examples (Coming Soon) */}
                <div className="rounded-lg border border-dashed border-(--color-border) bg-(--color-surface-secondary)/30 p-4">
                  <div className="flex items-center gap-2">
                    <FlaskConical className="h-4 w-4 text-(--color-text-tertiary)" />
                    <span className="text-sm font-medium text-(--color-text-secondary)">
                      {t.workspace?.fewShotTitle ?? "Few-Shot Examples"}
                    </span>
                    <span className="rounded-full border border-(--color-border) px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-(--color-text-tertiary)">
                      {t.workspace?.comingSoon ?? "Coming Soon"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-(--color-text-tertiary)">
                    {t.workspace?.fewShotDesc ?? "Custom few-shot examples will be available in a future release."}
                  </p>
                </div>

                {/* Save Button */}
                <div className="flex items-center gap-3 pt-1">
                  <Button
                    onClick={handlePromptSave}
                    disabled={promptSaving}
                    className="w-full sm:w-auto"
                  >
                    {promptSaving ? (
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                    ) : promptSaveResult === "success" ? (
                      <Check className="h-4 w-4" />
                    ) : promptSaveResult === "error" ? (
                      <X className="h-4 w-4" />
                    ) : null}
                    {promptSaveResult === "success"
                      ? (t.workspace?.llmSaved ?? "Saved")
                      : (t.workspace?.savePrompts ?? "Save Prompt Configuration")}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* ── Section 3: Member Management ── */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-(--color-text-secondary)" />
                <CardTitle>{t.workspace?.teamMembersTitle ?? "Team Members"}</CardTitle>
              </div>
              <CardDescription>
                {t.workspace?.teamMembersDesc ?? "Manage members, roles, and ownership for this workspace"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MemberManagement
                locale={locale}
                workspaceId={workspaceId}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
