"use client";

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Field, FieldLabel, FieldError } from '@/components/ui/field';
import { Loader2, X } from 'lucide-react';
import { useTranslations, type Locale } from '@/i18n/utils';
import { useTaskStore } from '@/stores/taskStore';
import { toast } from 'sonner';
import type { Task } from '@/types/task';

interface TaskEditorProps {
  task: Task;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  locale?: Locale;
}

function normalizeTag(tag: string): string {
  return tag.trim().toLowerCase();
}

export function TaskEditor({
  task,
  open,
  onOpenChange,
  locale = 'en',
}: TaskEditorProps) {
  const t = useTranslations(locale);
  const updateTask = useTaskStore((s) => s.updateTask);

  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description);
  const [labels, setLabels] = useState<string[]>(task.labels);
  const [dependencies, setDependencies] = useState<string[]>(task.dependencies);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Tag input refs
  const labelInputRef = useRef<HTMLInputElement>(null);
  const depInputRef = useRef<HTMLInputElement>(null);
  const [labelInput, setLabelInput] = useState('');
  const [depInput, setDepInput] = useState('');

  // Reset form when task or dialog changes
  useEffect(() => {
    if (open) {
      setTitle(task.title);
      setDescription(task.description);
      setLabels(task.labels);
      setDependencies(task.dependencies);
      setSaving(false);
      setErrors({});
      setLabelInput('');
      setDepInput('');
    }
  }, [open, task]);

  /* ── Label helpers ── */

  const addLabel = useCallback(
    (raw: string) => {
      const tag = raw.trim();
      if (!tag) {
        setErrors((prev) => ({ ...prev, labels: t.taskEditor.labels_empty }));
        return;
      }
      if (labels.some((l) => normalizeTag(l) === normalizeTag(tag))) {
        setErrors((prev) => ({ ...prev, labels: t.taskEditor.labels_duplicate }));
        return;
      }
      setLabels((prev) => [...prev, tag]);
      setLabelInput('');
      setErrors((prev) => ({ ...prev, labels: '' }));
    },
    [labels, t.taskEditor],
  );

  const removeLabel = useCallback((index: number) => {
    setLabels((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /* ── Dependency helpers ── */

  const addDependency = useCallback(
    (raw: string) => {
      const dep = raw.trim();
      if (!dep) {
        setErrors((prev) => ({ ...prev, dependencies: t.taskEditor.dependency_empty }));
        return;
      }
      if (normalizeTag(dep) === normalizeTag(task.id)) {
        setErrors((prev) => ({ ...prev, dependencies: t.taskEditor.dependency_self }));
        return;
      }
      if (dependencies.some((d) => normalizeTag(d) === normalizeTag(dep))) {
        return; // silent dedup
      }
      setDependencies((prev) => [...prev, dep]);
      setDepInput('');
      setErrors((prev) => ({ ...prev, dependencies: '' }));
    },
    [dependencies, task.id, t.taskEditor],
  );

  const removeDependency = useCallback((index: number) => {
    setDependencies((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /* ── Key handlers ── */

  const handleLabelKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addLabel(labelInput);
    }
  };

  const handleDepKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addDependency(depInput);
    }
  };

  /* ── Save ── */

  const handleSave = async () => {
    const localErrors: Record<string, string> = {};
    if (!title.trim()) localErrors.title = 'Required';
    if (Object.keys(localErrors).length > 0) {
      setErrors(localErrors);
      return;
    }

    setSaving(true);

    try {
      // Store handles optimistic update + server response + rollback internally.
      // On failure it re-throws so we can show the toast and keep the dialog open.
      await updateTask(task.id, {
        title: title.trim(),
        description,
        labels,
        dependencies,
      });
      setSaving(false);
      toast.success(t.taskEditor.saved);
      onOpenChange(false);
    } catch {
      // Store already rolled back the optimistic update.
      setSaving(false);
      toast.error(t.taskEditor.error_save);
      // Keep dialog open so the user can retry.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.taskEditor.title}</DialogTitle>
          <DialogDescription>{t.taskEditor.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {/* Title */}
          <Field>
            <FieldLabel htmlFor="te-title">{t.taskEditor.title_label}</FieldLabel>
            <Input
              id="te-title"
              value={title}
              onChange={(e) => { setTitle(e.target.value); setErrors((prev) => ({ ...prev, title: '' })); }}
              placeholder={t.taskEditor.title_placeholder}
              aria-invalid={!!errors.title}
              autoFocus
            />
            <FieldError>{errors.title}</FieldError>
          </Field>

          {/* Description */}
          <Field>
            <FieldLabel htmlFor="te-description">{t.taskEditor.description_label}</FieldLabel>
            <Textarea
              id="te-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t.taskEditor.description_placeholder}
              rows={3}
            />
          </Field>

          {/* Labels */}
          <Field>
            <FieldLabel htmlFor="te-labels">{t.taskEditor.labels_label}</FieldLabel>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {labels.map((label, i) => (
                <Badge key={`${label}-${i}`} variant="secondary" className="gap-1 pr-1">
                  {label}
                  <button
                    type="button"
                    onClick={() => removeLabel(i)}
                    className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20 transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
            <Input
              id="te-labels"
              ref={labelInputRef}
              value={labelInput}
              onChange={(e) => { setLabelInput(e.target.value); setErrors((prev) => ({ ...prev, labels: '' })); }}
              onKeyDown={handleLabelKeyDown}
              placeholder={t.taskEditor.labels_placeholder}
              aria-invalid={!!errors.labels}
            />
            <FieldError>{errors.labels}</FieldError>
          </Field>

          {/* Dependencies */}
          <Field>
            <FieldLabel htmlFor="te-deps">{t.taskEditor.dependencies_label}</FieldLabel>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {dependencies.map((dep, i) => (
                <Badge key={`${dep}-${i}`} variant="outline" className="gap-1 pr-1">
                  {dep}
                  <button
                    type="button"
                    onClick={() => removeDependency(i)}
                    className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20 transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
            <Input
              id="te-deps"
              ref={depInputRef}
              value={depInput}
              onChange={(e) => { setDepInput(e.target.value); setErrors((prev) => ({ ...prev, dependencies: '' })); }}
              onKeyDown={handleDepKeyDown}
              placeholder={t.taskEditor.dependencies_placeholder}
              aria-invalid={!!errors.dependencies}
            />
            <FieldError>{errors.dependencies}</FieldError>
          </Field>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            {t.taskEditor.cancel}
          </Button>
          <Button type="button" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {saving ? t.taskEditor.saving : t.taskEditor.save}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
