'use client';

import { useState } from 'react';
import { AlertCircle, Check, ChevronDown, Copy, RotateCw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { useTranslations, type Locale } from '@/i18n/utils';

export interface BackendError {
  /** Friendly/user-facing message (can be translated) */
  friendlyMessage: string;
  /** Raw backend error detail - could be string, object, or array */
  rawDetail?: unknown;
  /** HTTP status code if available */
  status?: number;
  /** Optional error code from backend */
  errorCode?: string;
  /** Optional action label for retry button */
  retryLabel?: string;
  /** Optional retry handler */
  onRetry?: () => void;
  /** Optional dismiss handler */
  onDismiss?: () => void;
  /**
   * Locale for the component's own copy (it called useTranslations before
   * the placeholder rewrite in 353224f). Callers already pass it.
   */
  locale?: Locale;
}

/**
 * The collapsible raw response, with its own copy affordance.
 *
 * Its own component so the copy state lives with the thing it reports on, and so the card
 * above stays a short render instead of one block of nested conditionals.
 */
function RawDetail({ detail, locale }: { detail: string; locale: Locale }) {
  const t = useTranslations(locale);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      // Straight to the browser API: a function whose whole body is this one call would be
      // a seam with nothing behind it.
      await navigator.clipboard.writeText(detail);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // The clipboard API is not available in every context; the detail stays readable.
    }
  };

  return (
    <Collapsible className="group/collapsible space-y-2 border-t border-destructive/20 pt-3">
      <CollapsibleTrigger
        // A stable name and `aria-expanded` from the primitive, rather than a label that
        // swaps with the state: a disclosure button's name describes what it discloses, and
        // two labels in the DOM (one hidden by CSS, which jsdom cannot see) would be read as
        // one concatenated name wherever the stylesheet is not applied.
        aria-label={t.errorDisplay.raw_response}
        render={
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start px-0 text-xs text-destructive/80 hover:text-destructive"
          />
        }
      >
        <ChevronDown className="mr-1 h-3.5 w-3.5 transition-transform group-data-open/collapsible:rotate-180" />
        <span aria-hidden="true" className="group-data-open/collapsible:hidden">
          {t.errorDisplay.show_details}
        </span>
        <span aria-hidden="true" className="hidden group-data-open/collapsible:inline">
          {t.errorDisplay.hide_details}
        </span>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div
          role="region"
          aria-label={t.errorDisplay.raw_response}
          className="space-y-2 rounded bg-background/50 p-3"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              {t.errorDisplay.raw_response}
            </p>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleCopy}
              aria-label={copied ? t.errorDisplay.copied : t.errorDisplay.copy}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              {copied ? (
                <Check className="h-3.5 w-3.5 text-emerald-500" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
          <pre className="max-h-60 overflow-auto font-mono text-[10px] break-all whitespace-pre-wrap text-foreground/90">
            {detail}
          </pre>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

/**
 * The card a failed operation shows: what went wrong, what to do about it, and the raw
 * response behind it.
 *
 * It was parked as a placeholder that rendered `null` (`353224f`), which left every call
 * site blank — including the Kanban board, where the error state replaces the whole page.
 * The render below is that prior implementation (`dad9039`) plus the retry action the
 * interface already promised and the call sites already pass: it did not render one.
 *
 * The message itself belongs to the caller: this component only renders its own chrome.
 */
export function ErrorDisplay({
  friendlyMessage,
  rawDetail,
  status,
  errorCode,
  retryLabel,
  onRetry,
  onDismiss,
  locale = 'en',
}: BackendError) {
  const t = useTranslations(locale);

  const formattedDetail = formatRawDetail(rawDetail);
  // Worth disclosing when there is a detail at all and it has something to say. Testing the
  // formatted text for the placeholder string would drop a caller whose detail *is* that
  // literal text, and testing only for `null` would open an empty panel for `""`.
  const hasDetail =
    rawDetail !== undefined && rawDetail !== null && formattedDetail !== '';

  return (
    <div
      data-slot="error-display"
      className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
        <div
          // Announced, and only this: a banner appears in response to a failure, so a screen
          // reader has to hear it — but `role="alert"` is atomic, so putting it on the whole
          // card would re-read the card (raw JSON included) every time the detail is
          // expanded or collapsed.
          role="alert"
          className="min-w-0 flex-1"
        >
          <p className="text-sm font-medium text-destructive">{friendlyMessage}</p>
          {(status || errorCode) && (
            <p className="mt-1 font-mono text-xs text-destructive/70">
              {status ? `HTTP ${status}` : null}
              {status && errorCode ? ' • ' : null}
              {errorCode ?? null}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RotateCw className="mr-1 h-3.5 w-3.5" />
              {retryLabel ?? t.common.retry}
            </Button>
          )}
          {onDismiss && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onDismiss}
              aria-label={t.errorDisplay.dismiss}
              className="text-destructive/60 hover:text-destructive"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {hasDetail && <RawDetail detail={formattedDetail} locale={locale} />}
    </div>
  );
}

/**
 * Format raw backend error detail into a readable string.
 */
function formatRawDetail(detail: unknown): string {
  if (detail === undefined || detail === null) {
    return '(no detail provided)';
  }
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => formatRawDetail(item)).join('\n\n---\n\n');
  }
  if (typeof detail === 'object') {
    try {
      return JSON.stringify(detail, null, 2);
    } catch {
      return String(detail);
    }
  }
  return String(detail);
}

/**
 * Extract error info from various error shapes.
 * Useful for normalizing errors before passing to ErrorDisplay or toasts.
 */
export function extractErrorInfo(err: unknown): {
  friendlyMessage: string;
  rawDetail?: unknown;
  status?: number;
  errorCode?: string;
} {
  // ApiRequestError from our api.ts
  if (err && typeof err === 'object' && 'detail' in err && 'status' in err) {
    const apiErr = err as {
      detail: unknown;
      status: number;
      errorCode?: string;
      message: string;
    };
    return {
      friendlyMessage: apiErr.message,
      rawDetail: apiErr.detail,
      status: apiErr.status,
      errorCode: apiErr.errorCode,
    };
  }

  // Standard Error
  if (err instanceof Error) {
    return {
      friendlyMessage: err.message,
      rawDetail: err.message,
    };
  }

  // String
  if (typeof err === 'string') {
    return {
      friendlyMessage: err,
      rawDetail: err,
    };
  }

  // Unknown shape
  return {
    friendlyMessage: 'An unknown error occurred',
    rawDetail: err,
  };
}
