import { useState, useEffect } from "react";
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
  Github,
  BookOpen,
  Activity,
  Code,
} from "lucide-react";
import { useTranslations, type Locale, localizedPath } from "@/i18n/utils";
import { useSettingsStore } from "@/stores/settingsStore";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { LLMProvider, ExportFormat } from "@/types/settings";
import pkg from "../../../package.json";

/* ── Helpers ─────────────────────────────────────────────────── */

function inputClass(hasError?: boolean): string {
  const base =
    "flex h-9 w-full rounded-lg border bg-(--color-surface) px-3 py-1 text-sm text-(--color-text) transition-colors placeholder:text-(--color-text-tertiary) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-primary-500) disabled:cursor-not-allowed disabled:opacity-50";
  const error = "border-red-500 focus-visible:ring-red-500";
  return `${base} ${hasError ? error : "border-(--color-border)"}`;
}

function labelClass(): string {
  return "block text-sm font-medium text-(--color-text) mb-1.5";
}

function radioGroupClass(): string {
  return "flex flex-wrap gap-2";
}

function radioOptionClass(selected: boolean): string {
  const base =
    "inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-sm font-medium cursor-pointer transition-colors";
  if (selected) {
    return `${base} border-(--color-primary-500) bg-(--color-primary-500)/10 text-(--color-primary-600)`;
  }
  return `${base} border-(--color-border) text-(--color-text-secondary) hover:border-(--color-primary-300) hover:text-(--color-text)`;
}

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
}

function LLMForm({ t, initial, onSave }: LLMFormProps) {
  const [form, setForm] = useState<LLMFormState>(initial);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
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
    setSaving(true);
    // Simulate async save — store is sync/localStorage
    setTimeout(() => {
      onSave(form);
      setSaving(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }, 300);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult("idle");
    // Simulate test — in real implementation, this would call the backend endpoint
    setTimeout(() => {
      setTesting(false);
      setTestResult("success");
      setTimeout(() => setTestResult("idle"), 3000);
    }, 1500);
  };

  const providerOptions: { value: LLMProvider; label: string }[] = [
    { value: "ollama", label: t.settings.llm_provider_ollama },
    { value: "openai", label: t.settings.llm_provider_openai },
    { value: "anthropic", label: t.settings.llm_provider_anthropic },
  ];

  return (
    <div className="space-y-5">
      {/* Provider selection */}
      <fieldset>
        <legend className={labelClass()}>{t.settings.llm_provider}</legend>
        <div className={radioGroupClass()}>
          {providerOptions.map((opt) => (
            <label
              key={opt.value}
              className={radioOptionClass(form.provider === opt.value)}
            >
              <input
                type="radio"
                name="llm-provider"
                value={opt.value}
                checked={form.provider === opt.value}
                onChange={() => updateField("provider", opt.value)}
                className="sr-only"
              />
              {opt.label}
            </label>
          ))}
        </div>
      </fieldset>

      {/* Ollama fields */}
      {form.provider === "ollama" && (
        <div className="space-y-4 rounded-lg border border-(--color-border) bg-(--color-surface-secondary)/50 p-4">
          <div>
            <label htmlFor="ollama-url" className={labelClass()}>
              {t.settings.llm_ollama_url}
            </label>
            <input
              id="ollama-url"
              type="text"
              className={inputClass()}
              value={form.ollama.baseUrl}
              onChange={(e) =>
                updateNested("ollama", "baseUrl", e.target.value)
              }
              placeholder="http://localhost:11434"
            />
          </div>
          <div>
            <label htmlFor="ollama-model" className={labelClass()}>
              {t.settings.llm_ollama_model}
            </label>
            <input
              id="ollama-model"
              type="text"
              className={inputClass()}
              value={form.ollama.model}
              onChange={(e) => updateNested("ollama", "model", e.target.value)}
              placeholder={t.settings.llm_ollama_model_placeholder}
            />
          </div>
        </div>
      )}

      {/* OpenAI fields */}
      {form.provider === "openai" && (
        <div className="space-y-4 rounded-lg border border-(--color-border) bg-(--color-surface-secondary)/50 p-4">
          <div>
            <label htmlFor="openai-key" className={labelClass()}>
              {t.settings.llm_openai_api_key}
            </label>
            <div className="relative">
              <input
                id="openai-key"
                type={showOpenAI ? "text" : "password"}
                className={inputClass()}
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
          </div>
          <div>
            <label htmlFor="openai-model" className={labelClass()}>
              {t.settings.llm_openai_model}
            </label>
            <input
              id="openai-model"
              type="text"
              className={inputClass()}
              value={form.openai.model}
              onChange={(e) => updateNested("openai", "model", e.target.value)}
              placeholder="gpt-4o-mini"
            />
          </div>
        </div>
      )}

      {/* Anthropic fields */}
      {form.provider === "anthropic" && (
        <div className="space-y-4 rounded-lg border border-(--color-border) bg-(--color-surface-secondary)/50 p-4">
          <div>
            <label htmlFor="anthropic-key" className={labelClass()}>
              {t.settings.llm_anthropic_api_key}
            </label>
            <div className="relative">
              <input
                id="anthropic-key"
                type={showAnthropic ? "text" : "password"}
                className={inputClass()}
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
          </div>
          <div>
            <label htmlFor="anthropic-model" className={labelClass()}>
              {t.settings.llm_anthropic_model}
            </label>
            <input
              id="anthropic-model"
              type="text"
              className={inputClass()}
              value={form.anthropic.model}
              onChange={(e) =>
                updateNested("anthropic", "model", e.target.value)
              }
              placeholder="claude-3-haiku"
            />
          </div>
        </div>
      )}

      {/* Shared parameters */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="llm-temperature" className={labelClass()}>
            {t.settings.llm_temperature}
          </label>
          <div className="flex items-center gap-3">
            <input
              id="llm-temperature"
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={form.temperature}
              onChange={(e) =>
                updateField("temperature", parseFloat(e.target.value))
              }
              className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-(--color-border) accent-(--color-primary-500)"
            />
            <span className="min-w-[2.5rem] text-sm font-medium tabular-nums text-(--color-text-secondary)">
              {form.temperature.toFixed(1)}
            </span>
          </div>
        </div>
        <div>
          <label htmlFor="llm-max-tokens" className={labelClass()}>
            {t.settings.llm_max_tokens}
          </label>
          <input
            id="llm-max-tokens"
            type="number"
            className={inputClass()}
            value={form.maxTokens}
            onChange={(e) =>
              updateField("maxTokens", parseInt(e.target.value, 10) || 0)
            }
            min={256}
            max={8192}
            step={256}
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : saved ? (
            <Check className="h-4 w-4" />
          ) : null}
          {saved ? t.settings.llm_saved : t.settings.llm_save}
        </Button>

        <Button variant="outline" onClick={handleTest} disabled={testing}>
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
  } = useSettingsStore();
  const { user, loading: authLoading } = useAuthStore();
  const { theme, setTheme } = useUIStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  /* ── Build LLMForm initial state from store ── */
  const llmInitial: LLMFormState = {
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
  };

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
            <div className="flex items-center gap-4">
              {user.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt={user.name}
                  className="h-12 w-12 rounded-full object-cover ring-2 ring-(--color-border)"
                />
              ) : (
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-(--color-primary-500)/10 text-lg font-semibold text-(--color-primary-600)">
                  {user.name?.charAt(0)?.toUpperCase() || "?"}
                </div>
              )}
              <div className="flex-1">
                <p className="text-sm font-medium text-(--color-text)">
                  {user.name}
                </p>
                <p className="text-sm text-(--color-text-secondary)">
                  {user.email}
                </p>
              </div>
              <Badge variant="outline" className="text-xs">
                {t.settings.profile_signed_in_with}{" "}
                {user.email?.includes("google") ? "Google" : "GitHub"}
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
          <LLMForm t={t} initial={llmInitial} onSave={handleLLMSave} />
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
          <fieldset>
            <legend className={labelClass()}>
              {t.settings.appearance_theme}
            </legend>
            <div className={radioGroupClass()}>
              {(["light", "dark", "system"] as const).map((tVal) => (
                <label key={tVal} className={radioOptionClass(theme === tVal)}>
                  <input
                    type="radio"
                    name="theme"
                    value={tVal}
                    checked={theme === tVal}
                    onChange={() => setTheme(tVal)}
                    className="sr-only"
                  />
                  {tVal === "light"
                    ? t.settings.appearance_theme_light
                    : tVal === "dark"
                      ? t.settings.appearance_theme_dark
                      : t.settings.appearance_theme_system}
                </label>
              ))}
            </div>
          </fieldset>

          {/* Language */}
          <fieldset>
            <legend className={labelClass()}>
              {t.settings.appearance_language}
            </legend>
            <div className={radioGroupClass()}>
              {(["en", "es"] as const).map((lang) => (
                <a
                  key={lang}
                  href={localizedPath("/settings", lang)}
                  className={radioOptionClass(locale === lang)}
                >
                  {lang === "en"
                    ? t.settings.appearance_language_en
                    : t.settings.appearance_language_es}
                </a>
              ))}
            </div>
          </fieldset>
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
          <div>
            <label htmlFor="export-format" className={labelClass()}>
              {t.settings.export_format}
            </label>
            <select
              id="export-format"
              className={inputClass()}
              value={settings.export.defaultFormat}
              onChange={(e) => setExportFormat(e.target.value as ExportFormat)}
            >
              <option value="trello">{t.settings.export_format_trello}</option>
              <option value="json">{t.settings.export_format_json}</option>
              <option value="markdown">
                {t.settings.export_format_markdown}
              </option>
            </select>
          </div>
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
            <p className={labelClass()}>{t.settings.about_links}</p>
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
