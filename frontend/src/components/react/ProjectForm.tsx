import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Loader2 } from 'lucide-react';
import { useTranslations, type Locale } from '@/i18n/utils';
import { createProjectSchema } from '@/schemas';

const NAME_MAX = 120;
const DESC_MAX = 500;

interface ProjectFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: { name: string; description: string }) => Promise<void>;
  locale?: Locale;
  initialData?: { name: string; description: string };
  title?: string;
}

export function ProjectForm({
  open,
  onOpenChange,
  onSubmit,
  locale = 'en',
  initialData,
  title,
}: ProjectFormProps) {
  const t = useTranslations(locale);
  const [name, setName] = useState(initialData?.name ?? '');
  const [description, setDescription] = useState(initialData?.description ?? '');
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const clearError = (field: string) => {
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: '' }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    const result = createProjectSchema.safeParse({ name, description });
    if (!result.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of result.error.issues) {
        if (issue.path.length > 0) {
          fieldErrors[String(issue.path[0])] = issue.message;
        }
      }
      setErrors(fieldErrors);
      return;
    }

    setSaving(true);
    try {
      await onSubmit(result.data);
      onOpenChange(false);
      setName('');
      setDescription('');
      setErrors({});
    } finally {
      setSaving(false);
    }
  };

  const nameError = errors.name;
  const descError = errors.description;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {title ?? t.projects.create_title}
          </DialogTitle>
          <DialogDescription>
            {t.projects.create_description}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="name" className="text-sm font-medium text-foreground">
              {t.projects.name_label}
            </label>
            <Input
              id="name"
              value={name}
              onChange={(e) => { setName(e.target.value); clearError('name'); }}
              placeholder={t.projects.name_placeholder}
              maxLength={NAME_MAX}
              required
              autoFocus
              aria-invalid={!!nameError}
            />
            <div className="flex justify-between text-xs">
              {nameError ? (
                <span className="text-destructive">{nameError}</span>
              ) : (
                <span />
              )}
              <span className="text-muted-foreground">{name.length}/{NAME_MAX}</span>
            </div>
          </div>

          <div className="space-y-2">
            <label htmlFor="description" className="text-sm font-medium text-foreground">
              {t.projects.description_label}
            </label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => { setDescription(e.target.value); clearError('description'); }}
              placeholder={t.projects.description_placeholder}
              maxLength={DESC_MAX}
              rows={3}
              aria-invalid={!!descError}
            />
            <div className="flex justify-between text-xs">
              {descError ? (
                <span className="text-destructive">{descError}</span>
              ) : (
                <span />
              )}
              <span className="text-muted-foreground">{description.length}/{DESC_MAX}</span>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              {t.common.cancel}
            </Button>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {initialData ? t.common.save : t.common.create}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
