import { useState, useEffect, useCallback } from "react";
import {
  Bot,
  FileText,
  Check,
  X,
  LoaderCircle,
  Users,
  TriangleAlert,
  FlaskConical,
} from "lucide-react";
import { toast } from "sonner";
import { getLLMConfig, upsertLLMConfig } from "@/lib/llm-config-api";
import { getPrompts, upsertPrompts } from "@/lib/prompts-api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { MemberManagement } from "@/components/react/MemberManagement";
import type { WorkspaceLLMConfig, WorkspacePrompt } from "@/types/workspace";
import en from "@/i18n/en.json";
import es from "@/i18n/es.json";

/* ── Props ─────────────────────────────────────────────────── */

interface WorkspaceSettingsProps {
  locale: string;
  workspaceId: string;
}

/* ── WorkspaceSettings Component ────────────────────────────── */

export function WorkspaceSettings({
  locale,
  workspaceId,
}: WorkspaceSettingsProps) {
  const t = locale === "es" ? es : en;

  /* ── LLM Config State ── */
  const [llmConfig, setLlmConfig] = useState<WorkspaceLLMConfig>({
    provider: "ollama",
    model: "",
    temperature: 0.1,
    maxTokens: 2048,
    baseUrl: "http://localhost:11434",
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
        });
      }
      if (promptData) {
        setPrompts({
          systemPrompt: promptData.systemPrompt ?? "",
          instructionTemplate: promptData.instructionTemplate ?? "",
        });
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load settings";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    setMounted(true);
    loadConfigs();
  }, [loadConfigs]);

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
      });
      setLlmSaveResult("success");
      toast.success("LLM configuration saved");
      setTimeout(() => setLlmSaveResult("idle"), 3000);
    } catch (err) {
      setLlmSaveResult("error");
      const message =
        err instanceof Error ? err.message : "Failed to save LLM config";
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
      toast.success("Prompt configuration saved");
      setTimeout(() => setPromptSaveResult("idle"), 3000);
    } catch (err) {
      setPromptSaveResult("error");
      const message =
        err instanceof Error ? err.message : "Failed to save prompts";
      toast.error(message);
      setTimeout(() => setPromptSaveResult("idle"), 3000);
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

  /* ── Render ── */
  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-semibold text-(--color-text)">
          Workspace Settings
        </h1>
        <p className="mt-1 text-sm text-(--color-text-secondary)">
          Configure LLM, prompts, and manage team members for this workspace.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-12 text-sm text-(--color-text-secondary)">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Loading settings...
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
              Try again
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
                  <CardTitle>LLM Configuration</CardTitle>
                </div>
                <CardDescription>
                  Configure the AI model used for task extraction in this
                  workspace
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {/* Provider */}
                <div className="space-y-2">
                  <Label htmlFor="llm-provider">Provider</Label>
                  <Select
                    value={llmConfig.provider}
                    onValueChange={(val) =>
                      setLlmConfig((prev) => ({ ...prev, provider: val }))
                    }
                  >
                    <SelectTrigger id="llm-provider" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ollama">Ollama (Local)</SelectItem>
                      <SelectItem value="openai">OpenAI</SelectItem>
                      <SelectItem value="anthropic">Anthropic</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Model */}
                <div className="space-y-2">
                  <Label htmlFor="llm-model">Model</Label>
                  <Input
                    id="llm-model"
                    type="text"
                    value={llmConfig.model ?? ""}
                    onChange={(e) =>
                      setLlmConfig((prev) => ({
                        ...prev,
                        model: e.target.value,
                      }))
                    }
                    placeholder={
                      llmConfig.provider === "ollama"
                        ? "llama3.2, mistral"
                        : llmConfig.provider === "openai"
                          ? "gpt-4o-mini"
                          : "claude-3-haiku"
                    }
                  />
                </div>

                {/* Temperature */}
                <div className="space-y-2">
                  <Label htmlFor="llm-temperature">Temperature</Label>
                  <div className="flex items-center gap-3">
                    <input
                      id="llm-temperature"
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={llmConfig.temperature ?? 0.1}
                      onChange={(e) =>
                        setLlmConfig((prev) => ({
                          ...prev,
                          temperature: parseFloat(e.target.value),
                        }))
                      }
                      className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-(--color-border) accent-(--color-primary-500)"
                    />
                    <span className="min-w-[2.5rem] text-sm font-medium tabular-nums text-(--color-text-secondary)">
                      {(llmConfig.temperature ?? 0.1).toFixed(1)}
                    </span>
                  </div>
                </div>

                {/* Max Tokens */}
                <div className="space-y-2">
                  <Label htmlFor="llm-max-tokens">Max Tokens</Label>
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
                </div>

                {/* Base URL (shown for Ollama) */}
                <div className="space-y-2">
                  <Label htmlFor="llm-base-url">Base URL</Label>
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
                  {llmConfig.provider !== "ollama" && (
                    <p className="text-xs text-(--color-text-tertiary)">
                      Optional for cloud providers
                    </p>
                  )}
                </div>

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
                      ? "Saved"
                      : "Save LLM Configuration"}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* ── Section 2: Prompt Configuration ── */}
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-(--color-text-secondary)" />
                  <CardTitle>Prompt Configuration</CardTitle>
                </div>
                <CardDescription>
                  Customize the prompts used for task extraction in this
                  workspace
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {/* System Prompt */}
                <div className="space-y-2">
                  <Label htmlFor="system-prompt">System Prompt</Label>
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
                    placeholder="You are an expert software development lead who excels at breaking down user stories into clear, actionable development tasks."
                  />
                  <p className="text-xs text-(--color-text-tertiary)">
                    The system-level instruction that sets the AI's role and
                    behavior
                  </p>
                </div>

                {/* Instruction Template */}
                <div className="space-y-2">
                  <Label htmlFor="instruction-template">
                    Instruction Template
                  </Label>
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
                    placeholder="Break this user story into smaller development tasks..."
                  />
                  <p className="text-xs text-(--color-text-tertiary)">
                    The instruction prompt with format guidelines and few-shot
                    examples
                  </p>
                </div>

                {/* Few-Shot Examples (Coming Soon) */}
                <div className="rounded-lg border border-dashed border-(--color-border) bg-(--color-surface-secondary)/30 p-4">
                  <div className="flex items-center gap-2">
                    <FlaskConical className="h-4 w-4 text-(--color-text-tertiary)" />
                    <span className="text-sm font-medium text-(--color-text-secondary)">
                      Few-Shot Examples
                    </span>
                    <span className="rounded-full border border-(--color-border) px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-(--color-text-tertiary)">
                      Coming Soon
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-(--color-text-tertiary)">
                    Custom few-shot examples will be available in a future
                    release.
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
                      ? "Saved"
                      : "Save Prompt Configuration"}
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
                <CardTitle>Team Members</CardTitle>
              </div>
              <CardDescription>
                Manage members, roles, and ownership for this workspace
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
