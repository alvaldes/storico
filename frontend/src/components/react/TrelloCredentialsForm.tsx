import { useState, useEffect, useCallback } from 'react';
import { Check, KeyRound, LoaderCircle, RotateCw, TriangleAlert } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  getTrelloConfig,
  getTrelloConfigStatus,
  upsertTrelloConfig,
  type TrelloConfigStatus,
} from '@/lib/trello-api';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

interface TrelloCredentialsFormProps {
  locale: 'en' | 'es';
  workspaceId: string;
  /**
   * Whether the current user may read and write the credential pair. The page
   * knows the role from its workspace read, so the split arrives as a prop: a
   * member never even attempts the admin GET, rather than discovering it in a 403.
   */
  isAdmin: boolean;
}

/**
 * The workspace's Trello credential pair, mirroring `LLMConfigEditor` in shape
 * and behavior: a settings card, two fields, one save — with the difference the
 * feature asks to be visible: the member-readable status line.
 *
 * The status endpoint (`GET .../settings/trello/status`) is readable by any
 * member and answers field *names*, never values, so the card renders for
 * everyone and only the admin fields are gated. That is what lets a member
 * learn the workspace is not configured before triggering an export that
 * cannot finish.
 */
export function TrelloCredentialsForm({ locale, workspaceId, isAdmin }: TrelloCredentialsFormProps) {
  const t = locale === 'es' ? es : en;

  /* ── Credential fields (admin only) ── */
  const [apiKey, setApiKey] = useState('');
  const [token, setToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  /* ── Shared state ── */
  const [status, setStatus] = useState<TrelloConfigStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  /**
   * Load the member-readable status always, the admin pair only for an admin.
   *
   * The fields are filled with exactly what the API returned and nothing else:
   * when the answer carries `null` for a field, the field stays empty — the
   * form never echoes a secret the API did not hand over.
   */
  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const nextStatus = await getTrelloConfigStatus(workspaceId);
      setStatus(nextStatus);
      if (isAdmin) {
        const config = await getTrelloConfig(workspaceId);
        setApiKey(config.apiKey ?? '');
        setToken(config.token ?? '');
      }
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, isAdmin]);

  useEffect(() => {
    void load();
  }, [load]);

  /** The human label for one status field code, reusing the inputs' own labels. */
  const fieldLabels: Record<string, string> = {
    api_key: t.settings.trello_field_api_key,
    token: t.settings.trello_field_token,
  };
  const fieldLabel = (code: string) => fieldLabels[code] ?? code;

  /* ── Save handler ── */
  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      // A blank field is "leave the stored one" — the backend merges the pair,
      // and the sibling LLM editor gives an empty field the same meaning.
      await upsertTrelloConfig(workspaceId, {
        apiKey: apiKey.trim() || undefined,
        token: token.trim() || undefined,
      });
      toast.success(t.settings.trello_saved);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      // Reread so the status line flips with the save, and the fields hold what
      // the API now returns — never a value the API chose not to send.
      await load();
    } catch (err) {
      const message = err instanceof Error ? err.message : undefined;
      toast.error(t.settings.trello_save_error, {
        description: message,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-(--color-text-secondary)" />
          <CardTitle>{t.settings.trello_title}</CardTitle>
        </div>
        <CardDescription>{t.settings.trello_description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-(--color-text-secondary)">
            <LoaderCircle className="h-4 w-4 animate-spin" />
            {t.workspace?.loading ?? 'Loading settings...'}
          </div>
        ) : loadError || !status ? (
          <div className="flex items-center gap-3 rounded-lg border border-(--color-destructive-border) bg-(--color-destructive-bg) p-3">
            <TriangleAlert className="h-4 w-4 shrink-0 text-destructive" />
            <p className="text-sm text-(--color-destructive-text)">
              {t.settings.trello_load_error}
            </p>
            <button
              type="button"
              onClick={() => void load()}
              className="ml-auto text-sm text-destructive underline"
            >
              {t.workspace?.tryAgain ?? 'Try again'}
            </button>
          </div>
        ) : (
          <>
            {/* The member-readable status line: field names, never values. */}
            <div className="space-y-1">
              <p className="text-sm text-(--color-text)">
                {status.configured
                  ? t.settings.trello_configured
                  : t.settings.trello_not_configured}
              </p>
              {!status.configured && status.missing.length > 0 && (
                <p className="text-xs text-(--color-text-tertiary)">
                  {t.settings.trello_missing_suffix.replace(
                    '{fields}',
                    status.missing.map(fieldLabel).join(', '),
                  )}
                </p>
              )}
              {!isAdmin && (
                <p className="text-xs text-(--color-text-tertiary)">
                  {t.settings.trello_member_hint}
                </p>
              )}
            </div>

            {isAdmin && (
              <div className="space-y-4">
                <label className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-(--color-text)">
                    {t.settings.trello_api_key}
                  </span>
                  <Input
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    type="password"
                    autoComplete="off"
                    placeholder={t.settings.trello_api_key}
                  />
                </label>
                <label className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-(--color-text)">
                    {t.settings.trello_token}
                  </span>
                  <Input
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    type="password"
                    autoComplete="off"
                    placeholder={t.settings.trello_token}
                  />
                </label>
                <Button onClick={handleSave} disabled={saving} size="sm">
                  {saving ? (
                    <RotateCw className="h-4 w-4 animate-spin" />
                  ) : saved ? (
                    <Check className="h-4 w-4" />
                  ) : null}
                  {t.settings.trello_save}
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
