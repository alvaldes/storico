import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Loader2 } from 'lucide-react';
import { useTranslations, type Locale } from '@/i18n/utils';
import { createStorySchema } from '@/schemas';

const ACTOR_MAX = 100;
const FEATURE_MAX = 300;
const BENEFIT_MAX = 300;
const RAW_TEXT_MAX = 2000;

/** Schema for form validation — same as createStorySchema, minus projectId. */
const storyFormSchema = createStorySchema.omit({ projectId: true });

interface StoryFormData {
  actor: string;
  feature: string;
  benefit: string;
  rawText: string;
}

interface StoryFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: StoryFormData) => Promise<void>;
  locale?: Locale;
  initialData?: Partial<StoryFormData>;
  title?: string;
}

export function StoryForm({
  open,
  onOpenChange,
  onSubmit,
  locale = 'en',
  initialData,
  title,
}: StoryFormProps) {
  const t = useTranslations(locale);
  const [actor, setActor] = useState(initialData?.actor ?? '');
  const [feature, setFeature] = useState(initialData?.feature ?? '');
  const [benefit, setBenefit] = useState(initialData?.benefit ?? '');
  const [rawText, setRawText] = useState(initialData?.rawText ?? '');
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const clearError = (field: string) => {
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: '' }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    const result = storyFormSchema.safeParse({ actor, feature, benefit, rawText });
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
      const { actor: a, feature: f, benefit: b, rawText: r } = result.data;
      const generatedRaw = r.trim() || `As a(n) ${a.trim()}, I want ${f.trim()}, so that ${b.trim()}`;
      await onSubmit({ actor: a.trim(), feature: f.trim(), benefit: b.trim(), rawText: generatedRaw });
      onOpenChange(false);
      setActor('');
      setFeature('');
      setBenefit('');
      setRawText('');
      setErrors({});
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {title ?? t.stories.create_title}
          </DialogTitle>
          <DialogDescription>
            {t.stories.create_description}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="actor">{t.stories.actor_label}</Label>
            <Input
              id="actor"
              value={actor}
              onChange={(e) => { setActor(e.target.value); clearError('actor'); }}
              placeholder={t.stories.actor_placeholder}
              maxLength={ACTOR_MAX}
              required
              autoFocus
              aria-invalid={!!errors.actor}
            />
            <div className="flex justify-between text-xs">
              {errors.actor ? (
                <span className="text-destructive">{errors.actor}</span>
              ) : (
                <span />
              )}
              <span className="text-muted-foreground">{actor.length}/{ACTOR_MAX}</span>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="feature">{t.stories.feature_label}</Label>
            <Input
              id="feature"
              value={feature}
              onChange={(e) => { setFeature(e.target.value); clearError('feature'); }}
              placeholder={t.stories.feature_placeholder}
              maxLength={FEATURE_MAX}
              required
              aria-invalid={!!errors.feature}
            />
            <div className="flex justify-between text-xs">
              {errors.feature ? (
                <span className="text-destructive">{errors.feature}</span>
              ) : (
                <span />
              )}
              <span className="text-muted-foreground">{feature.length}/{FEATURE_MAX}</span>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="benefit">{t.stories.benefit_label}</Label>
            <Input
              id="benefit"
              value={benefit}
              onChange={(e) => { setBenefit(e.target.value); clearError('benefit'); }}
              placeholder={t.stories.benefit_placeholder}
              maxLength={BENEFIT_MAX}
              required
              aria-invalid={!!errors.benefit}
            />
            <div className="flex justify-between text-xs">
              {errors.benefit ? (
                <span className="text-destructive">{errors.benefit}</span>
              ) : (
                <span />
              )}
              <span className="text-muted-foreground">{benefit.length}/{BENEFIT_MAX}</span>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="rawText">{t.stories.raw_text_label}</Label>
            <Textarea
              id="rawText"
              value={rawText}
              onChange={(e) => { setRawText(e.target.value); clearError('rawText'); }}
              placeholder={t.stories.raw_text_placeholder}
              maxLength={RAW_TEXT_MAX}
              rows={2}
              aria-invalid={!!errors.rawText}
            />
            <div className="flex justify-between text-xs">
              {errors.rawText ? (
                <span className="text-destructive">{errors.rawText}</span>
              ) : (
                <span className="text-muted-foreground">auto-generated if left empty</span>
              )}
              <span className="text-muted-foreground">{rawText.length}/{RAW_TEXT_MAX}</span>
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
              {t.common.create}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
