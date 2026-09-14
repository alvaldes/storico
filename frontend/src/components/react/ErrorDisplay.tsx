'use client';

import { useState } from 'react';
import { ChevronDown, AlertCircle, X, Copy, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { type Locale } from '@/i18n/utils';

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
 * Placeholder ErrorDisplay component.
 * Keep this file in the codebase for future implementation.
 * Currently renders nothing to avoid breaking imports.
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
  return null;
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
 * Copy text to clipboard.
 */
function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
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
