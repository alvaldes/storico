'use client';

import { LoaderCircle } from 'lucide-react';

/**
 * Presentational full-screen loading veil: the markup, the live region and the
 * spinner, taking only the label. Visibility and copy belong to the caller, so
 * the consumers — `FullPageLoader` (mutations, store-driven) and the Kanban
 * board's reads — cannot drift apart in markup or accessibility behaviour.
 *
 * z-[60] is deliberate: it sits above the shadcn dialogs (z-50, Dialog /
 * AlertDialog) so the veil also covers the dialog the user just confirmed,
 * and below sonner (z-index: 999999999 in sonner/dist/styles.css) so a
 * success toast fired as the request settles stays readable.
 *
 * No pointer-events-none: the overlay must swallow clicks while it is up.
 */
export function LoadingVeil({ label }: { label: string }) {
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-background/70 backdrop-blur-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-col items-center gap-3">
        <LoaderCircle className="h-8 w-8 animate-spin text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}
