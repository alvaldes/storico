import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Loader2 } from 'lucide-react';
import { useTranslations, type Locale } from '@/i18n/utils';

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actor.trim() || !feature.trim() || !benefit.trim()) return;
    setSaving(true);
    try {
      const generatedRaw = rawText.trim() || `As a(n) ${actor.trim()}, I want ${feature.trim()}, so that ${benefit.trim()}`;
      await onSubmit({ actor: actor.trim(), feature: feature.trim(), benefit: benefit.trim(), rawText: generatedRaw });
      onOpenChange(false);
      setActor('');
      setFeature('');
      setBenefit('');
      setRawText('');
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
              onChange={(e) => setActor(e.target.value)}
              placeholder={t.stories.actor_placeholder}
              required
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="feature">{t.stories.feature_label}</Label>
            <Input
              id="feature"
              value={feature}
              onChange={(e) => setFeature(e.target.value)}
              placeholder={t.stories.feature_placeholder}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="benefit">{t.stories.benefit_label}</Label>
            <Input
              id="benefit"
              value={benefit}
              onChange={(e) => setBenefit(e.target.value)}
              placeholder={t.stories.benefit_placeholder}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="rawText">{t.stories.raw_text_label}</Label>
            <Textarea
              id="rawText"
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder={t.stories.raw_text_placeholder}
              rows={2}
            />
            <p className="text-xs text-muted-foreground">
              {t.stories.raw_text_label} — auto-generated if left empty
            </p>
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
            <Button type="submit" disabled={saving || !actor.trim() || !feature.trim() || !benefit.trim()}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t.common.create}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
