import { useState, useEffect, useMemo } from "react";
import {
  User,
  Bot,
  Palette,
  Download,
  Info,
  TriangleAlert,
  Eye,
  EyeOff,
  Check,
  X,
  LoaderCircle,
  ExternalLink,
  BookOpen,
  Activity,
  Code,
  Github,
} from "lucide-react";
import { useTranslations, type Locale, localizedPath } from "@/i18n/utils";
import { useSettingsStore } from "@/stores/settingsStore";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";
import { testLLMConnection } from "@/lib/settings-api";
import { UserAvatar } from "@/components/react/UserAvatar";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group";
import { Field, FieldLabel, FieldDescription } from "@/components/ui/field";
import type { LLMProvider, ExportFormat } from "@/types/settings";
import pkg from "../../../package.json";

/* ── Helpers ─────────────────────────────────────────────────── */

/* ── Provider-specific LLM Form ──────────────────────────────── */

interface LLMFormState {
  provider: LLMProvider;
  ollama: { baseUrl: string; model: string };
  openai: { apiKey: string; model: string };
  anthropic: { apiKey: string; model: string };
  temperature: number;
  maxTokens: number;
}

interface LLMFormProps {
  t: ReturnType<typeof useTranslations>;
  initial: LLMFormState;
  onSave: (state: LLMFormState) => void;
  apiSaving: boolean;
  lastSaveResult: "idle" | "success" | "error";
}

function LLMForm({
  t,
  initial,
  onSave,
  apiSaving,
  lastSaveResult,
}: LLMFormProps) {
  const [form, setForm] = useState<LLMFormState>(initial);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"idle" | "success" | "error">(
    "idle",
  );
  const [showOpenAI, setShowOpenAI] = useState(false);
  const [showAnthropic, setShowAnthropic] = useState(false);

  // Reset form when initial changes (e.g. after external reset)
  useEffect(() => {
    setForm(initial);
  }, [initial]);

  const updateField = <K extends keyof LLMFormState>(
    key: K,
    value: LLMFormState[K],
  ) => setForm((prev) => ({ ...prev, [key]: value }));

  const updateNested = (
    section: "ollama" | "openai" | "anthropic",
    field: string,
    value: string,
  ) =>
    setForm((prev) => ({
      ...prev,
      [section]: { ...prev[section], [field]: value },
    }));

  const handleSave = () => {
    onSave(form);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult("idle");
    try {
      const params = {
        provider: form.provider,
        model:
          form.provider === "ollama"
            ? form.ollama.model
            : form.provider === "openai"
              ? form.openai.model
              : form.anthropic.model,
        ...(form.provider === "ollama"
          ? { base_url: form.ollama.baseUrl }
          : {}),
        ...(form.provider === "openai" && form.openai.apiKey
          ? { api_key: form.openai.apiKey }
          : {}),
        ...(form.provider === "anthropic" && form.anthropic.apiKey
          ? { api_key: form.anthropic.apiKey }
          : {}),
      };
      const result = await testLLMConnection(params);
      setTestResult(result.success ? "success" : "error");
    } catch {
      setTestResult("error");
    } finally {
      setTesting(false);
      setTimeout(() => setTestResult("idle"), 4000);
    }
  };

  const providerOptions: { value: LLMProvider; label: string }[] = [
    { value: "ollama", label: t.settings.llm_provider_ollama },
    { value: "openai", label: t.settings.llm_provider_openai },
    { value: "anthropic", label: t.settings.llm_provider_anthropic },
  ];

  return (
    <div className="space-y-5">
      {/* Provider selection */}
      <Field>
        <FieldLabel>{t.settings.llm_provider}</FieldLabel>
        <ToggleGroup
          value={[form.provider]}
          onValueChange={(value) => {
            updateField("provider", value as unknown as LLMProvider)
          }}
          variant="outline"
        >
          {providerOptions.map((opt) => (
            <ToggleGroupItem key={opt.value} value={opt.value}>
              {opt.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>

      {/* Ollama fields */}
      {form.provider === "ollama" && (
        <div className="space-y-4 rounded-lg border border-(--color-border) bg-(--color-surface-secondary)/50 p-4">
          <Field>
            <FieldLabel htmlFor="ollama-url">
              {t.settings.llm_ollama_url}
            </FieldLabel>
            <Input
              id="ollama-url"
              type="text"
              value={form.ollama.baseUrl}
              onChange={(e) =>
                updateNested("ollama", "baseUrl", e.target.value)
              }
              placeholder="http://localhost:11434"
            />
            <FieldDescription>
              Base URL for your local Ollama instance
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="ollama-model">
              {t.settings.llm_ollama_model}
            </FieldLabel>
            <Input
              id="ollama-model"
              type="text"
              value={form.ollama.model}
              onChange={(e) => updateNested("ollama", "model", e.target.value)}
              placeholder={t.settings.llm_ollama_model_placeholder}
            />
            <FieldDescription>
              Model name as listed in your Ollama installation
            </FieldDescription>
          </Field>
        </div>
      )}

      {/* OpenAI fields */}
      {form.provider === "openai" && (
        <div className="space-y-4 rounded-lg border border-(--color-border) bg-(--color-surface-secondary)/50 p-4">
          <Field>
            <FieldLabel htmlFor="openai-key">
              {t.settings.llm_openai_api_key}
            </FieldLabel>
            <div className="relative">
              <Input
                id="openai-key"
                type={showOpenAI ? "text" : "password"}
                value={form.openai.apiKey}
                onChange={(e) =>
                  updateNested("openai", "apiKey", e.target.value)
                }
                placeholder="sk-..."
              />
              <button
                type="button"
                onClick={() => setShowOpenAI(!showOpenAI)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-(--color-text-tertiary) hover:text-(--color-text)"
                tabIndex={-1}
              >
                {showOpenAI ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
            <FieldDescription>
              API key from your OpenAI account dashboard
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="openai-model">
              {t.settings.llm_openai_model}
            </FieldLabel>
            <Input
              id="openai-model"
              type="text"
              value={form.openai.model}
              onChange={(e) =>
                updateNested("openai", "model", e.target.value)
              }
              placeholder="gpt-4o-mini"
            />
            <FieldDescription>
              Model identifier (e.g., gpt-4o-mini, gpt-4)
            </FieldDescription>
          </Field>
        </div>
      )}

      {/* Anthropic fields */}
      {form.provider === "anthropic" && (
        <div className="space-y-4 rounded-lg border border-(--color-border) bg-(--color-surface-secondary)/50 p-4">
          <Field>
            <FieldLabel htmlFor="anthropic-key">
              {t.settings.llm_anthropic_api_key}
            </FieldLabel>
            <div className="relative">
              <Input
                id="anthropic-key"
                type={showAnthropic ? "text" : "password"}
                value={form.anthropic.apiKey}
                onChange={(e) =>
                  updateNested("anthropic", "apiKey", e.target.value)
                }
                placeholder="sk-ant-..."
              />
              <button
                type="button"
                onClick={() => setShowAnthropic(!showAnthropic)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-(--color-text-tertiary) hover:text-(--color-text)"
                tabIndex={-1}
              >
                {showAnthropic ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
            <FieldDescription>
              API key from your Anthropic Console
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="anthropic-model">
              {t.settings.llm_anthropic_model}
            </FieldLabel>
            <Input
              id="anthropic-model"
              type="text"
              value={form.anthropic.model}
              onChange={(e) =>
                updateNested("anthropic", "model", e.target.value)
              }
              placeholder="claude-3-haiku"
            />
            <FieldDescription>
              Model identifier (e.g., claude-3-haiku, claude-3-sonnet)
            </FieldDescription>
          </Field>
        </div>
      )}

      {/* Shared parameters */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field>
          <FieldLabel htmlFor="llm-temperature">
            {t.settings.llm_temperature}
          </FieldLabel>
          <div className="flex items-center gap-3">
            <Slider
              id="llm-temperature"
              value={[form.temperature]}
              onValueChange={(value) => updateField("temperature", Array.isArray(value) ? value[0] : value)}
              min={0}
              max={2}
              step={0.1}
              className="flex-1"
            />
            <span className="min-w-[2.5rem] text-sm font-medium tabular-nums text-(--color-text-secondary)">
              {form.temperature.toFixed(1)}
            </span>
          </div>
          <FieldDescription>
            Controls randomness in generated responses. Lower values produce
            more deterministic outputs.
          </FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="llm-max-tokens">
            {t.settings.llm_max_tokens}
          </FieldLabel>
          <Input
            id="llm-max-tokens"
            type="number"
            value={form.maxTokens}
            onChange={(e) =>
              updateField("maxTokens", parseInt(e.target.value, 10) || 0)
            }
            min={256}
            max={8192}
            step={256}
          />
          <FieldDescription>
            Maximum tokens in the generated response (256-8192)
          </FieldDescription>
        </Field>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={handleSave} disabled={apiSaving} className="w-full sm:w-auto">
          {apiSaving ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : lastSaveResult === "success" ? (
            <Check className="h-4 w-4" />
          ) : lastSaveResult === "error" ? (
            <X className="h-4 w-4" />
          ) : null}
          {lastSaveResult === "success"
            ? t.settings.llm_saved
            : t.settings.llm_save}
        </Button>

        <Button variant="outline" onClick={handleTest} disabled={testing} className="w-full sm:w-auto">
          {testing ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : testResult === "success" ? (
            <Check className="h-4 w-4 text-(--color-success)" />
          ) : testResult === "error" ? (
            <X className="h-4 w-4 text-red-500" />
          ) : null}
          {t.settings.llm_test}
        </Button>

        {testResult === "success" && (
          <span className="text-sm text-(--color-success-text)">
            {t.settings.llm_test_success}
          </span>
        )}
        {testResult === "error" && (
          <span className="text-sm text-red-500">
            {t.settings.llm_test_error}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Provider detection ────────────────────────────────────────── */

function formatProvider(user: { email: string; authProvider?: string }): string {
  if (user.authProvider) {
    return user.authProvider.charAt(0).toUpperCase() + user.authProvider.slice(1)
  }
  // Fallback when backend hasn't stored authProvider yet
  const email = user.email.toLowerCase()
  if (email.endsWith("@gmail.com") || email.includes("google")) return "Google"
  if (email.includes("github")) return "GitHub"
  return "OAuth"
}

/* ── Main Settings Page Component ────────────────────────────── */

interface SettingsPageProps {
  locale: Locale;
}

export function SettingsPage({ locale }: SettingsPageProps) {
  const t = useTranslations(locale);
  const {
    settings,
    setLLMProvider,
    setOllamaConfig,
    setOpenAIConfig,
    setAnthropicConfig,
    setExportFormat,
    loadFromApi,
    syncToApi,
    apiSaving,
    lastSaveResult,
  } = useSettingsStore();
  const { user, loading: authLoading } = useAuthStore();
  const { theme, setTheme } = useUIStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    loadFromApi();
  }, [loadFromApi]);

  /* ── Build LLMForm initial state from store (memoized) ── */
  const llmInitial = useMemo<LLMFormState>(
    () => ({
      provider: settings.llm.provider,
      ollama: {
        baseUrl: settings.llm.ollama.baseUrl,
        model: settings.llm.ollama.model,
      },
      openai: {
        apiKey: settings.llm.openai.apiKey,
        model: settings.llm.openai.model,
      },
      anthropic: {
        apiKey: settings.llm.anthropic.apiKey,
        model: settings.llm.anthropic.model,
      },
      temperature: settings.llm.ollama.temperature,
      maxTokens: settings.llm.ollama.maxTokens,
    }),
    [
      settings.llm.provider,
      settings.llm.ollama.baseUrl,
      settings.llm.ollama.model,
      settings.llm.ollama.temperature,
      settings.llm.ollama.maxTokens,
      settings.llm.openai.apiKey,
      settings.llm.openai.model,
      settings.llm.anthropic.apiKey,
      settings.llm.anthropic.model,
    ],
  );

  const handleLLMSave = (state: LLMFormState) => {
    setLLMProvider(state.provider);
    setOllamaConfig({
      baseUrl: state.ollama.baseUrl,
      model: state.ollama.model,
      temperature: state.temperature,
      maxTokens: state.maxTokens,
    });
    setOpenAIConfig({
      apiKey: state.openai.apiKey,
      model: state.openai.model,
      temperature: state.temperature,
      maxTokens: state.maxTokens,
    });
    setAnthropicConfig({
      apiKey: state.anthropic.apiKey,
      model: state.anthropic.model,
      temperature: state.temperature,
      maxTokens: state.maxTokens,
    });
    syncToApi({
      loading: t.settings.llm_saving,
      success: t.settings.llm_saved,
      successDesc: t.settings.llm_saved_description,
      error: t.settings.llm_save_error,
    });
  };

  if (!mounted) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-(--color-border) border-t-(--color-primary-500)" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 pb-12">
      {/* ── Page Header ── */}
      <div>
        <h1 className="text-2xl font-semibold text-(--color-text)">
          {t.settings.page_title}
        </h1>
        <p className="mt-1 text-sm text-(--color-text-secondary)">
          {t.settings.page_description}
        </p>
      </div>

      {/* ── Profile ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.profile_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.profile_description}</CardDescription>
        </CardHeader>
        <CardContent>
          {authLoading ? (
            <div className="flex items-center gap-2 text-sm text-(--color-text-secondary)">
              <LoaderCircle className="h-4 w-4 animate-spin" />
              {t.common.loading}
            </div>
          ) : user ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
              <UserAvatar src={user.avatar_url} name={user.name} size="lg" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-(--color-text)">
                  {user.name}
                </p>
                <p className="text-sm text-(--color-text-secondary)">
                  {user.email}
                </p>
              </div>
              <Badge variant="outline" className="w-full text-xs sm:w-auto">
                {t.settings.profile_signed_in_with}{" "}
                {formatProvider(user)}
              </Badge>
            </div>
          ) : (
            <p className="text-sm text-(--color-text-secondary)">
              {t.settings.profile_not_signed_in}
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── LLM Configuration ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.llm_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.llm_description}</CardDescription>
        </CardHeader>
        <CardContent>
          <LLMForm
            t={t}
            initial={llmInitial}
            onSave={handleLLMSave}
            apiSaving={apiSaving}
            lastSaveResult={lastSaveResult}
          />
        </CardContent>
      </Card>

      {/* ── Appearance ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Palette className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.appearance_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.appearance_description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Theme */}
          <Field>
            <FieldLabel>{t.settings.appearance_theme}</FieldLabel>
            <ToggleGroup
              value={[theme]}
              onValueChange={(value) => {
                setTheme(value as unknown as "light" | "dark" | "system")
              }}
              variant="outline"
            >
              {(["light", "dark", "system"] as const).map((tVal) => (
                <ToggleGroupItem key={tVal} value={tVal}>
                  {tVal === "light"
                    ? t.settings.appearance_theme_light
                    : tVal === "dark"
                      ? t.settings.appearance_theme_dark
                      : t.settings.appearance_theme_system}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>

          {/* Language */}
          <Field>
            <FieldLabel>{t.settings.appearance_language}</FieldLabel>
            <ToggleGroup
              value={[locale]}
              onValueChange={(value) => {
                const lang = value as unknown as string
                if (lang !== locale) {
                  window.location.href = localizedPath("/settings", lang as "en" | "es")
                }
              }}
              variant="outline"
            >
              {(["en", "es"] as const).map((lang) => (
                <ToggleGroupItem key={lang} value={lang}>
                  {lang === "en"
                    ? t.settings.appearance_language_en
                    : t.settings.appearance_language_es}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>
        </CardContent>
      </Card>

      {/* ── Export Defaults ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Download className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.export_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.export_description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Field>
            <FieldLabel htmlFor="export-format">
              {t.settings.export_format}
            </FieldLabel>
            <Select
              value={settings.export.defaultFormat}
              onValueChange={(value) => setExportFormat(value as ExportFormat)}
            >
              <SelectTrigger id="export-format" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="trello">{t.settings.export_format_trello}</SelectItem>
                <SelectItem value="json">{t.settings.export_format_json}</SelectItem>
                <SelectItem value="markdown">
                  {t.settings.export_format_markdown}
                </SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </CardContent>
      </Card>

      {/* ── About ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.about_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.about_description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <span className="text-sm text-(--color-text-secondary)">
              {t.settings.about_version}:
            </span>{" "}
            <span className="text-sm font-medium text-(--color-text)">
              v{pkg.version}
            </span>
          </div>
          <div>
            <p className="mb-1.5 text-sm font-medium text-(--color-text)">
              {t.settings.about_links}
            </p>
            <div className="flex flex-wrap gap-2">
              <a
                href={localizedPath("/docs", locale)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-(--color-border) px-3 py-1.5 text-sm text-(--color-text-secondary) transition-colors hover:border-(--color-primary-300) hover:text-(--color-text)"
              >
                <BookOpen className="h-3.5 w-3.5" />
                {t.settings.about_docs}
                <ExternalLink className="h-3 w-3" />
              </a>
              <a
                href={localizedPath("/api", locale)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-(--color-border) px-3 py-1.5 text-sm text-(--color-text-secondary) transition-colors hover:border-(--color-primary-300) hover:text-(--color-text)"
              >
                <Code className="h-3.5 w-3.5" />
                {t.settings.about_api}
                <ExternalLink className="h-3 w-3" />
              </a>
              <a
                href={localizedPath("/status", locale)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-(--color-border) px-3 py-1.5 text-sm text-(--color-text-secondary) transition-colors hover:border-(--color-primary-300) hover:text-(--color-text)"
              >
                <Activity className="h-3.5 w-3.5" />
                {t.settings.about_status}
                <ExternalLink className="h-3 w-3" />
              </a>
              <a
                href="https://github.com/alvaldes/storico"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-(--color-border) px-3 py-1.5 text-sm text-(--color-text-secondary) transition-colors hover:border-(--color-primary-300) hover:text-(--color-text)"
              >
                <Github className="h-3.5 w-3.5" />
                GitHub
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Danger Zone ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <TriangleAlert className="h-4 w-4 text-red-500" />
            <CardTitle className="text-red-600">
              {t.settings.danger_title}
            </CardTitle>
          </div>
          <CardDescription>{t.settings.danger_description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
            <p className="text-sm font-medium text-red-800 dark:text-red-200">
              {t.settings.danger_delete_account}
            </p>
            <p className="mt-1 text-sm text-red-600 dark:text-red-300">
              {t.settings.danger_delete_description}
            </p>
            <Button
              variant="outline"
              disabled
              className="mt-3 border-red-300 text-red-600 hover:bg-red-100 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/50"
            >
              {t.settings.danger_delete_account}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
