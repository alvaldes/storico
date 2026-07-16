import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Field, FieldLabel, FieldDescription, FieldError } from '@/components/ui/field';
import { Loader2 } from 'lucide-react';
import { useTranslations, type Locale } from '@/i18n/utils';
import { createProjectSchema } from '@/schemas';
import { IconPicker, IconTrigger } from '@/components/ui/icon-picker';

const NAME_MAX = 120;
const DESC_MAX = 500;

interface ProjectFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: { name: string; description: string; icon?: string }) => Promise<void>;
  locale?: Locale;
  initialData?: { name: string; description: string; icon?: string };
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
  const [icon, setIcon] = useState(initialData?.icon ?? 'folder-kanban');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  /* ── sync local state from initialData when dialog opens ── */
  useEffect(() => {
    if (open) {
      setName(initialData?.name ?? '');
      setDescription(initialData?.description ?? '');
      setIcon(initialData?.icon ?? 'folder-kanban');
      setErrors({});
    }
  }, [open, initialData]);

  const clearError = (field: string) => {
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: '' }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    const result = createProjectSchema.safeParse({ name, description, icon });
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
      setIcon('folder-kanban');
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
          <Field>
            <FieldLabel htmlFor="name">{t.projects.name_label}</FieldLabel>
            <div className="flex items-center gap-2">
              <IconTrigger
                value={icon}
                onClick={() => setPickerOpen(true)}
                locale={locale}
              />
              <Input
                id="name"
                value={name}
                onChange={(e) => { setName(e.target.value); clearError('name'); }}
                placeholder={t.projects.name_placeholder}
                maxLength={NAME_MAX}
                required
                autoFocus
                className="flex-1"
              />
            </div>
            <FieldDescription>A short, descriptive name for your project.</FieldDescription>
            <div className="flex justify-between text-xs">
              <FieldError>{nameError}</FieldError>
              <span className="text-muted-foreground">{name.length}/{NAME_MAX}</span>
            </div>
          </Field>

          <Field>
            <FieldLabel htmlFor="description">{t.projects.description_label}</FieldLabel>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => { setDescription(e.target.value); clearError('description'); }}
              placeholder={t.projects.description_placeholder}
              maxLength={DESC_MAX}
              rows={3}
            />
            <FieldDescription>Optional. Describe the project's purpose, goals, or any relevant context.</FieldDescription>
            <div className="flex justify-between text-xs">
              <FieldError>{descError}</FieldError>
              <span className="text-muted-foreground">{description.length}/{DESC_MAX}</span>
            </div>
          </Field>

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

      <IconPicker
        value={icon}
        onChange={setIcon}
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        locale={locale}
      />
    </Dialog>
  );
}
