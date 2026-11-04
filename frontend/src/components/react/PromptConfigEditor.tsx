import { useState, useEffect, useCallback } from 'react';
import { FileText, Check, X, LoaderCircle, RotateCw, TriangleAlert } from 'lucide-react';
import { toast } from 'sonner';
import { getPrompts, upsertPrompts } from '@/lib/prompts-api';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Field, FieldLabel, FieldDescription } from '@/components/ui/field';
import { FewShotConfigEditor } from '@/components/react/FewShotConfigEditor';
import type { WorkspacePrompt } from '@/types/workspace';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

interface PromptConfigEditorProps {
  locale: 'en' | 'es';
  workspaceId: string;
}

/**
 * The Prompts tab: the prompt configuration that used to be the second half of the
 * settings page's LLM card, extracted verbatim into its own component with its own
 * load, its own error handling and its own save button. This is a move, not a
 * rewrite: the fields, the endpoints, the validation posture and the copy are the
 * ones the merged card had.
 */
export function PromptConfigEditor({ locale, workspaceId }: PromptConfigEditorProps) {
  const t = locale === 'es' ? es : en;

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

  /* ── Shared State ── */
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  /* ── Fetch Prompts ── */
  const loadPrompts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const promptData = await getPrompts(workspaceId).catch((err) => {
        if (
          err instanceof Error &&
          (err.message.includes('403') || err.message.includes('admin'))
        ) {
          return null;
        }
        throw err;
      });
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
  }, [workspaceId, t.workspace]);

  useEffect(() => {
    setMounted(true);
    loadPrompts();
  }, [loadPrompts]);

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
      <div className="flex items-center gap-3 rounded-lg border border-(--color-destructive-border) bg-(--color-destructive-bg) p-4">
        <TriangleAlert className="h-5 w-5 shrink-0 text-destructive" />
        <div>
          <p className="text-sm font-medium text-(--color-destructive-text)">{error}</p>
          <button
            type="button"
            onClick={loadPrompts}
            className="mt-1 text-sm text-destructive underline hover:text-(--color-destructive-text)"
          >
            {t.workspace?.tryAgain ?? 'Try again'}
          </button>
        </div>
      </div>
    );
  }

  return (
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
          <Button onClick={handlePromptSave} disabled={promptSaving} className="w-full sm:w-auto">
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
  );
}
