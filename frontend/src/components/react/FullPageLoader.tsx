'use client';

import { LoadingVeil } from '@/components/react/LoadingVeil';
import { useLoadingStore } from '@/stores/loadingStore';
import { useTranslations, type Locale } from '@/i18n/utils';

/**
 * Full-page blocking overlay raised by the loading store while a
 * user-initiated mutation is in flight. The markup, live region and z-index
 * live in `LoadingVeil`; this wrapper owns the store-driven visibility and the
 * mutation copy (`common.processing`).
 *
 * Reads never raise it (see blocking-requests.ts) — the Kanban board's reads
 * show the same veil through their own local state instead.
 */
export function FullPageLoader({ locale }: { locale: Locale }) {
  // Boolean selector, not an object: zustand v5 subscribes through
  // useSyncExternalStore, and a freshly allocated snapshot would loop.
  const visible = useLoadingStore((s) => s.visible);
  const t = useTranslations(locale);

  if (!visible) return null;

  return <LoadingVeil label={t.common.processing} />;
}
