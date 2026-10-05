'use client';

import { LoaderCircle } from 'lucide-react';
import { useLoadingStore } from '@/stores/loadingStore';
import { useTranslations, type Locale } from '@/i18n/utils';

/**
 * Full-page blocking overlay raised by the loading store while a
 * user-initiated mutation is in flight.
 *
 * z-[60] is deliberate: it sits above the shadcn dialogs (z-50, Dialog /
 * AlertDialog) so the veil also covers the dialog the user just confirmed,
 * and below sonner (z-index: 999999999 in sonner/dist/styles.css) so a
 * success toast fired as the request settles stays readable.
 *
 * No pointer-events-none: the overlay must swallow clicks — blocking is the
 * point. Reads never raise it (see blocking-requests.ts).
 */
export function FullPageLoader({ locale }: { locale: Locale }) {
  // Boolean selector, not an object: zustand v5 subscribes through
  // useSyncExternalStore, and a freshly allocated snapshot would loop.
  const visible = useLoadingStore((s) => s.visible);
  const t = useTranslations(locale);

  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-background/70 backdrop-blur-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-col items-center gap-3">
        <LoaderCircle className="h-8 w-8 animate-spin text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">{t.common.processing}</p>
      </div>
    </div>
  );
}
