import { useState, useMemo } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Field, FieldLabel, FieldDescription, FieldError } from '@/components/ui/field';
import { InputGroup, InputGroupAddon, InputGroupText, InputGroupInput } from '@/components/ui/input-group';
import { Loader2, Check, X, Eye } from 'lucide-react';
import { useTranslations, type Locale } from '@/i18n/utils';

const ACTOR_MAX = 100;
const FEATURE_MAX = 300;
const BENEFIT_MAX = 300;
const RAW_TEXT_MAX = 2000;

type StoryMode = 'parts' | 'full';

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

/** Simple regex-based validation: does the text look like a standard user story? */
function validateKeywords(text: string) {
  return {
    asA: /\bas\s+a(?:\(n\))?\b/i.test(text),
    iWant: /\bI\s+want\b/i.test(text),
    soThat: /\bso\s+that\b/i.test(text),
  };
}

/** Parse a full user story into actor, feature, benefit. Returns null if it can't parse. */
function parseUserStory(text: string): { actor: string; feature: string; benefit: string } | null {
  const regex = /As\s+a(?:\(n\))?\s+(.+?),\s+I\s+want\s+(.+?),\s+so\s+that\s+(.+)/i;
  const match = text.match(regex);
  if (match) {
    return {
      actor: match[1].trim(),
      feature: match[2].trim(),
      benefit: match[3].trim(),
    };
  }
  return null;
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

  // Mode state
  const [mode, setMode] = useState<StoryMode>('parts');

  // Parts mode fields
  const [actor, setActor] = useState(initialData?.actor ?? '');
  const [feature, setFeature] = useState(initialData?.feature ?? '');
  const [benefit, setBenefit] = useState(initialData?.benefit ?? '');

  // Full mode fields
  const [fullText, setFullText] = useState(initialData?.rawText ?? '');

  // Shared state
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Derived: live preview in parts mode
  const livePreview = useMemo(() => {
    const a = actor.trim();
    const f = feature.trim();
    const b = benefit.trim();
    if (!a && !f && !b) return '';
    const parts: string[] = [];
    if (a) parts.push(`${t.stories?.keyword_as_a ?? 'As a(n)'} ${a}`);
    else parts.push(`${t.stories?.keyword_as_a ?? 'As a(n)'} […]`);
    if (f) parts.push(`${t.stories?.keyword_i_want ?? 'I want'} ${f}`);
    else parts.push(`${t.stories?.keyword_i_want ?? 'I want'} […]`);
    if (b) parts.push(`${t.stories?.keyword_so_that ?? 'so that'} ${b}`);
    else parts.push(`${t.stories?.keyword_so_that ?? 'so that'} […]`);
    return parts.join(', ');
  }, [actor, feature, benefit]);

  // Derived: keyword validation in full mode
  const keywordCheck = useMemo(() => {
    if (!fullText.trim()) return null;
    return validateKeywords(fullText.trim());
  }, [fullText]);

  const allKeywordsValid = keywordCheck && keywordCheck.asA && keywordCheck.iWant && keywordCheck.soThat;

  const clearError = (field: string) => {
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: '' }));
  };

  /** Switch mode, preserving data when possible. */
  const switchMode = (newMode: StoryMode) => {
    if (newMode === mode) return;
    if (newMode === 'full' && mode === 'parts') {
      // Going parts → full: populate fullText from parts if empty
      const a = actor.trim();
      const f = feature.trim();
      const b = benefit.trim();
      if (a || f || b) {
        const preview = [];
        if (a) preview.push(`As a(n) ${a}`);
        if (f) preview.push(`I want ${f}`);
        if (b) preview.push(`so that ${b}`);
        setFullText(preview.join(', ') || '');
      }
    }
    if (newMode === 'parts' && mode === 'full') {
      // Going full → parts: try to parse if parts are empty
      if (!actor.trim() && !feature.trim() && !benefit.trim()) {
        const parsed = parseUserStory(fullText.trim());
        if (parsed) {
          setActor(parsed.actor);
          setFeature(parsed.feature);
          setBenefit(parsed.benefit);
        }
      }
    }
    setMode(newMode);
    setErrors({});
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    let submitData: StoryFormData;

    if (mode === 'parts') {
      // Validate fields
      const localErrors: Record<string, string> = {};
      if (!actor.trim()) localErrors.actor = t.stories?.validationRequired ?? 'Required';
      if (!feature.trim()) localErrors.feature = t.stories?.validationRequired ?? 'Required';
      if (!benefit.trim()) localErrors.benefit = t.stories?.validationRequired ?? 'Required';
      if (actor.length > ACTOR_MAX) localErrors.actor = (t.stories?.validationMaxChars ?? 'Max {count} characters').replace('{count}', String(ACTOR_MAX));
      if (feature.length > FEATURE_MAX) localErrors.feature = (t.stories?.validationMaxChars ?? 'Max {count} characters').replace('{count}', String(FEATURE_MAX));
      if (benefit.length > BENEFIT_MAX) localErrors.benefit = (t.stories?.validationMaxChars ?? 'Max {count} characters').replace('{count}', String(BENEFIT_MAX));

      if (Object.keys(localErrors).length > 0) {
        setErrors(localErrors);
        return;
      }

      const generatedRaw = `As a(n) ${actor.trim()}, I want ${feature.trim()}, so that ${benefit.trim()}`;
      submitData = {
        actor: actor.trim(),
        feature: feature.trim(),
        benefit: benefit.trim(),
        rawText: generatedRaw,
      };
    } else {
      // Full text mode
      const text = fullText.trim();
      if (!text) {
        setErrors({ fullText: t.stories?.validationRequired ?? 'Required' });
        return;
      }
      if (text.length > RAW_TEXT_MAX) {
        setErrors({ fullText: (t.stories?.validationMaxChars ?? 'Max {count} characters').replace('{count}', String(RAW_TEXT_MAX)) });
        return;
      }

      // Validate keywords
      const keywords = validateKeywords(text);
      if (!keywords.asA || !keywords.iWant || !keywords.soThat) {
        setErrors({ fullText: t.stories.keyword_invalid });
        return;
      }

      // Parse to extract parts
      const parsed = parseUserStory(text);
      if (parsed) {
        // Ensure each parsed part respects max length
        submitData = {
          actor: parsed.actor.slice(0, ACTOR_MAX),
          feature: parsed.feature.slice(0, FEATURE_MAX),
          benefit: parsed.benefit.slice(0, BENEFIT_MAX),
          rawText: text,
        };
      } else {
        // Fallback — shouldn't happen if keywords pass, but guard anyway
        setErrors({ fullText: t.stories?.parseError ?? 'Could not parse the user story. Try switching to parts mode.' });
        return;
      }
    }

    setSaving(true);
    try {
      await onSubmit(submitData);
      onOpenChange(false);
      // Reset
      setActor('');
      setFeature('');
      setBenefit('');
      setFullText('');
      setMode('parts');
      setErrors({});
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {title ?? t.stories.create_title}
          </DialogTitle>
          <DialogDescription>
            {t.stories.create_description}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Mode toggle */}
          <div className="flex rounded-lg border border-border p-0.5 bg-muted/50" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'parts'}
              onClick={() => switchMode('parts')}
              className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-all ${
                mode === 'parts'
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.stories.mode_parts}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'full'}
              onClick={() => switchMode('full')}
              className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-all ${
                mode === 'full'
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.stories.mode_full}
            </button>
          </div>

          {/* ─── PARTS MODE ─── */}
          {mode === 'parts' && (
            <div className="min-h-[280px] space-y-4">
              <Field>
                <FieldLabel htmlFor="actor">{t.stories.actor_label}</FieldLabel>
                <InputGroup>
                  <InputGroupAddon>
                    <InputGroupText>As a(n)</InputGroupText>
                  </InputGroupAddon>
                  <InputGroupInput
                    id="actor"
                    value={actor}
                    onChange={(e) => { setActor(e.target.value); clearError('actor'); }}
                    placeholder={t.stories.actor_placeholder}
                    maxLength={ACTOR_MAX}
                    required
                    autoFocus
                    aria-invalid={!!errors.actor}
                  />
                </InputGroup>
                <div className="flex justify-between text-xs">
                  <FieldError>{errors.actor}</FieldError>
                  <span className="text-muted-foreground">{actor.length}/{ACTOR_MAX}</span>
                </div>
              </Field>

              <Field>
                <FieldLabel htmlFor="feature">{t.stories.feature_label}</FieldLabel>
                <InputGroup>
                  <InputGroupAddon>
                    <InputGroupText>I want</InputGroupText>
                  </InputGroupAddon>
                  <InputGroupInput
                    id="feature"
                    value={feature}
                    onChange={(e) => { setFeature(e.target.value); clearError('feature'); }}
                    placeholder={t.stories.feature_placeholder}
                    maxLength={FEATURE_MAX}
                    required
                    aria-invalid={!!errors.feature}
                  />
                </InputGroup>
                <div className="flex justify-between text-xs">
                  <FieldError>{errors.feature}</FieldError>
                  <span className="text-muted-foreground">{feature.length}/{FEATURE_MAX}</span>
                </div>
              </Field>

              <Field>
                <FieldLabel htmlFor="benefit">{t.stories.benefit_label}</FieldLabel>
                <InputGroup>
                  <InputGroupAddon>
                    <InputGroupText>so that</InputGroupText>
                  </InputGroupAddon>
                  <InputGroupInput
                    id="benefit"
                    value={benefit}
                    onChange={(e) => { setBenefit(e.target.value); clearError('benefit'); }}
                    placeholder={t.stories.benefit_placeholder}
                    maxLength={BENEFIT_MAX}
                    required
                    aria-invalid={!!errors.benefit}
                  />
                </InputGroup>
                <div className="flex justify-between text-xs">
                  <FieldError>{errors.benefit}</FieldError>
                  <span className="text-muted-foreground">{benefit.length}/{BENEFIT_MAX}</span>
                </div>
              </Field>

              {/* Live preview — always visible */}
              <div className="rounded-lg border border-border/50 bg-muted/30 p-4 space-y-2">
                <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  <Eye className="h-3.5 w-3.5" />
                  {t.stories.preview_label}
                </div>
                {livePreview ? (
                  <p className="text-sm text-foreground leading-relaxed">
                    {livePreview}
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    {t.stories.preview_empty}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* ─── FULL TEXT MODE ─── */}
          {mode === 'full' && (
            <div className="min-h-[280px] space-y-4">
              <Field>
                <FieldLabel htmlFor="fullText">{t.stories.raw_text_label}</FieldLabel>
                <Textarea
                  id="fullText"
                  value={fullText}
                  onChange={(e) => { setFullText(e.target.value); clearError('fullText'); }}
                  placeholder={t.stories.raw_text_placeholder}
                  maxLength={RAW_TEXT_MAX}
                  rows={4}
                  autoFocus
                  aria-invalid={!!errors.fullText}
                  className="min-h-[100px] resize-y"
                />
                <FieldDescription>{"Write a complete user story in the format: As a(n) [role], I want [feature], so that [benefit]."}</FieldDescription>
                <div className="flex justify-between text-xs">
                  <FieldError>{errors.fullText}</FieldError>
                  <span className="text-muted-foreground">{fullText.length}/{RAW_TEXT_MAX}</span>
                </div>
              </Field>

              {/* Keyword validation — always visible */}
              <div className="rounded-lg border border-border/50 bg-muted/30 p-4 space-y-3">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {t.stories.keyword_validation}
                </p>
                {fullText.trim().length > 0 ? (
                  <>
                    <div className="space-y-2">
                      <KeywordIndicator
                        label={t.stories.keyword_as_a}
                        valid={keywordCheck?.asA ?? false}
                      />
                      <KeywordIndicator
                        label={t.stories.keyword_i_want}
                        valid={keywordCheck?.iWant ?? false}
                      />
                      <KeywordIndicator
                        label={t.stories.keyword_so_that}
                        valid={keywordCheck?.soThat ?? false}
                      />
                    </div>
                    {allKeywordsValid ? (
                      <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                        {t.stories.keyword_valid}
                      </p>
                    ) : (
                      <div className="space-y-1">
                        <p className="text-xs text-destructive font-medium">
                          {t.stories.keyword_invalid}
                        </p>
                        <button
                          type="button"
                          onClick={() => switchMode('parts')}
                          className="text-xs text-primary hover:underline"
                        >
                          {t.stories.switch_to_parts}
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    {t.stories.keyword_empty}
                  </p>
                )}
              </div>

              <p
                className="text-xs text-muted-foreground leading-relaxed"
                dangerouslySetInnerHTML={{ __html: t.stories.story_format_hint }}
              />
            </div>
          )}

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

/** Small inline indicator showing whether a keyword was found. */
function KeywordIndicator({ label, valid }: { label: string; valid: boolean }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {valid ? (
        <Check className="h-4 w-4 text-emerald-500 shrink-0" />
      ) : (
        <X className="h-4 w-4 text-destructive shrink-0" />
      )}
      <span className={valid ? 'text-foreground' : 'text-muted-foreground'}>
        {label}
      </span>
    </div>
  );
}
