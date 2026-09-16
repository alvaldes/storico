import { Layers } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Field, FieldLabel, FieldDescription } from '@/components/ui/field';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

interface FewShotConfigEditorProps {
  locale: 'en' | 'es';
  enabled: boolean;
  limit: number;
  threshold: number;
  onChange: (value: { enabled: boolean; limit: number; threshold: number }) => void;
}

export function FewShotConfigEditor({
  locale,
  enabled,
  limit,
  threshold,
  onChange,
}: FewShotConfigEditorProps) {
  const t = locale === 'es' ? es : en;

  const setEnabled = (next: boolean) => onChange({ enabled: next, limit, threshold });
  const setLimit = (next: number) => onChange({ enabled, limit: next, threshold });
  const setThreshold = (next: number) => onChange({ enabled, limit, threshold: next });

  return (
    <div className="space-y-4">
      {/* ── Enabled toggle ── */}
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-(--color-text-secondary)" />
            <span className="text-sm font-medium text-(--color-text)">
              {t.workspace?.fewShotEnabled ?? 'Automatic few-shot examples'}
            </span>
          </div>
          <p className="text-xs text-(--color-text-tertiary)">
            {t.workspace?.fewShotEnabledDesc ??
              'Retrieve similar past extractions from this workspace and use them to guide the model.'}
          </p>
        </div>
        <Switch
          checked={enabled}
          onCheckedChange={(next) => setEnabled(next)}
          aria-label={t.workspace?.fewShotEnabled ?? 'Automatic few-shot examples'}
        />
      </div>

      {/* ── Limit ── */}
      <Field>
        <FieldLabel id="few-shot-limit-label">
          {t.workspace?.fewShotLimit ?? 'Max examples'}
        </FieldLabel>
        <div className="flex items-center gap-3">
          <Slider
            aria-labelledby="few-shot-limit-label"
            value={[limit]}
            onValueChange={(value) => setLimit(Array.isArray(value) ? value[0] : value)}
            min={1}
            max={10}
            step={1}
            disabled={!enabled}
            className="flex-1"
          />
          <span className="min-w-[2.5rem] text-sm font-medium tabular-nums text-(--color-text-secondary)">
            {limit}
          </span>
        </div>
        <FieldDescription>
          {t.workspace?.fewShotLimitDesc ?? '1–10, how many examples to inject.'}
        </FieldDescription>
      </Field>

      {/* ── Threshold ── */}
      <Field>
        <FieldLabel id="few-shot-threshold-label">
          {t.workspace?.fewShotThreshold ?? 'Similarity threshold'}
        </FieldLabel>
        <div className="flex items-center gap-3">
          <Slider
            aria-labelledby="few-shot-threshold-label"
            value={[threshold]}
            onValueChange={(value) => setThreshold(Array.isArray(value) ? value[0] : value)}
            min={0}
            max={1}
            step={0.05}
            disabled={!enabled}
            className="flex-1"
          />
          <span className="min-w-[2.5rem] text-sm font-medium tabular-nums text-(--color-text-secondary)">
            {threshold.toFixed(2)}
          </span>
        </div>
        <FieldDescription>
          {t.workspace?.fewShotThresholdDesc ??
            'Minimum similarity (0.0–1.0) for an example to be considered.'}
        </FieldDescription>
      </Field>
    </div>
  );
}
