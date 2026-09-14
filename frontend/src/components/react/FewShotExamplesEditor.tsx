import { useState } from 'react';
import { Trash2, ChevronUp, ChevronDown, AlertCircle, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import type { FewShotExample } from '@/types/workspace';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

interface FewShotExamplesEditorProps {
  locale: 'en' | 'es';
  examples: FewShotExample[];
  onChange: (examples: FewShotExample[]) => void;
  maxExamples?: number;
}

const TASKS_FORMAT_HINT = `1. summary: Set up database schema for transactions
description: Create the necessary database tables and indexes to store transaction history records with fields for date, amount, type, and notes.

2. summary: Implement transaction listing API endpoint
description: Build a REST API endpoint that returns paginated transaction history for a given user, with support for date filtering and sorting.`;

export function FewShotExamplesEditor({
  locale,
  examples: initialExamples,
  onChange,
  maxExamples = 3,
}: FewShotExamplesEditorProps) {
  const t = locale === 'es' ? es : en;

  const [examples, setExamples] = useState<FewShotExample[]>(initialExamples);
  const [errors, setErrors] = useState<Record<number, { userStory?: string; tasks?: string }>>({});

  const validate = (idx: number, field: 'userStory' | 'tasks', value: string) => {
    const newErrors = { ...errors };
    if (field === 'userStory' && value.trim().length < 10) {
      newErrors[idx] = {
        ...newErrors[idx],
        userStory: t.workspace?.fewShotUserStoryMin ?? 'User Story must be at least 10 characters',
      };
    } else if (field === 'tasks' && value.trim().length < 20) {
      newErrors[idx] = {
        ...newErrors[idx],
        tasks: t.workspace?.fewShotTasksMin ?? 'Tasks must be at least 20 characters',
      };
    } else if (newErrors[idx]) {
      delete newErrors[idx][field];
      if (Object.keys(newErrors[idx]).length === 0) delete newErrors[idx];
    }
    setErrors(newErrors);
  };

  const handleUserStoryChange = (idx: number, value: string) => {
    const next = [...examples];
    next[idx] = { ...next[idx], userStory: value };
    setExamples(next);
    onChange(next);
    validate(idx, 'userStory', value);
  };

  const handleTasksChange = (idx: number, value: string) => {
    const next = [...examples];
    next[idx] = { ...next[idx], tasks: value };
    setExamples(next);
    onChange(next);
    validate(idx, 'tasks', value);
  };

  const addExample = () => {
    if (examples.length >= maxExamples) return;
    const next = [...examples, { userStory: '', tasks: '' }];
    setExamples(next);
    onChange(next);
  };

  const removeExample = (idx: number) => {
    const next = examples.filter((_, i) => i !== idx);
    setExamples(next);
    onChange(next);
    const newErrors = { ...errors };
    delete newErrors[idx];
    setErrors(
      Object.fromEntries(
        Object.entries(newErrors).map(([k, v]) => [
          parseInt(k, 10) > idx ? parseInt(k, 10) - 1 : parseInt(k, 10),
          v,
        ]),
      ),
    );
  };

  const moveExample = (fromIdx: number, toIdx: number) => {
    if (toIdx < 0 || toIdx >= examples.length) return;
    const next = [...examples];
    const [item] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, item);
    setExamples(next);
    onChange(next);
    const newErrors: Record<number, (typeof errors)[number]> = {};
    Object.entries(errors).forEach(([k, v]) => {
      const oldIdx = parseInt(k, 10);
      let newIdx = oldIdx;
      if (oldIdx === fromIdx) newIdx = toIdx;
      else if (fromIdx < toIdx && oldIdx > fromIdx && oldIdx <= toIdx) newIdx = oldIdx - 1;
      else if (fromIdx > toIdx && oldIdx >= toIdx && oldIdx < fromIdx) newIdx = oldIdx + 1;
      newErrors[newIdx] = v;
    });
    setErrors(newErrors);
  };

  const hasErrors = Object.keys(errors).length > 0;

  return (
    <Card>
      <CardContent className="pt-0">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-sm font-medium text-(--color-text)">
            {t.workspace?.fewShotTitle ?? 'Few-Shot Examples'}
          </h4>
          <span className="text-xs text-(--color-text-tertiary)">
            {examples.length} / {maxExamples}
          </span>
        </div>

        <div className="space-y-3">
          {examples.map((ex, idx) => (
            <div
              key={idx}
              className="space-y-2 p-3 rounded-lg border border-(--color-border) bg-(--color-surface-secondary)/30"
            >
              <div className="flex items-start gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-(--color-text-tertiary) hover:text-(--color-text) shrink-0"
                  onClick={() => moveExample(idx, idx - 1)}
                  disabled={idx === 0}
                  aria-label={t.workspace?.moveUp ?? 'Move up'}
                >
                  <ChevronUp className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-(--color-text-tertiary) hover:text-(--color-text) shrink-0"
                  onClick={() => moveExample(idx, idx + 1)}
                  disabled={idx === examples.length - 1}
                  aria-label={t.workspace?.moveDown ?? 'Move down'}
                >
                  <ChevronDown className="h-4 w-4" />
                </Button>
                <div className="flex-1" />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-red-500 hover:text-red-600 shrink-0"
                  onClick={() => removeExample(idx)}
                  aria-label={t.workspace?.removeExample ?? 'Remove example'}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-(--color-text)">
                  {t.workspace?.fewShotUserStoryLabel ?? 'User Story'}
                </label>
                <Textarea
                  value={ex.userStory}
                  onChange={(e) => handleUserStoryChange(idx, e.target.value)}
                  rows={3}
                  placeholder={
                    t.workspace?.fewShotUserStoryPlaceholder ??
                    'As a user, I want to log in so that I can access my account'
                  }
                  className={`min-h-[5rem] ${errors[idx]?.userStory ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20' : ''}`}
                />
                {errors[idx]?.userStory && (
                  <p className="text-xs text-red-500 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" />
                    {errors[idx].userStory}
                  </p>
                )}
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-(--color-text)">
                  {t.workspace?.fewShotTasksLabel ?? 'Expected Tasks Output'}
                </label>
                <Textarea
                  value={ex.tasks}
                  onChange={(e) => handleTasksChange(idx, e.target.value)}
                  rows={6}
                  placeholder={TASKS_FORMAT_HINT}
                  className={`min-h-[10rem] font-mono text-sm ${errors[idx]?.tasks ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20' : ''}`}
                />
                {errors[idx]?.tasks && (
                  <p className="text-xs text-red-500 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" />
                    {errors[idx].tasks}
                  </p>
                )}
              </div>

              {idx < examples.length - 1 && <Separator />}
            </div>
          ))}

          {examples.length < maxExamples && (
            <Button type="button" variant="outline" className="w-full" onClick={addExample}>
              <span className="flex items-center justify-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                {t.workspace?.addExample ?? 'Add Example'}
              </span>
            </Button>
          )}

          {examples.length >= maxExamples && (
            <p className="text-xs text-(--color-text-tertiary) text-center">
              {t.workspace?.maxExamplesReached ?? 'Maximum of 3 few-shot examples reached'}
            </p>
          )}
        </div>

        {hasErrors && (
          <div className="mt-3 p-3 rounded-lg border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30">
            <p className="text-sm text-red-800 dark:text-red-200">
              {t.workspace?.fixValidationErrors ?? 'Fix validation errors before saving'}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
