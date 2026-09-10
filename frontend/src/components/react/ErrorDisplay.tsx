"use client";

import { useState } from "react";
import { ChevronDown, AlertCircle, X, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslations, type Locale } from "@/i18n/utils";

export interface BackendError {
  /** Friendly/user-facing message (can be translated) */
  friendlyMessage: string;
  /** Raw backend error detail - could be string, object, or array */
  rawDetail?: unknown;
  /** HTTP status code if available */
  status?: number;
  /** Optional error code from backend */
  errorCode?: string;
  /** Optional dismiss handler */
  onDismiss?: () => void;
}

function formatRawDetail(detail: unknown): string {
  if (detail === undefined || detail === null) {
    return "(no detail provided)";
  }
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => formatRawDetail(item)).join("\n\n---\n\n");
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail, null, 2);
    } catch {
      return String(detail);
    }
  }
  return String(detail);
}

function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}

export function ErrorDisplay({
  friendlyMessage,
  rawDetail,
  status,
  errorCode,
  onDismiss,
  locale = "en",
}: BackendError) {
  const t = useTranslations(locale);
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const formattedDetail = formatRawDetail(rawDetail);
  const hasDetail =
    rawDetail !== undefined &&
    rawDetail !== null &&
    formattedDetail !== "(no detail provided)";

  const showDetailsLabel =
    t?.errorDisplay?.show_details ?? "Show backend error details";
  const hideDetailsLabel =
    t?.errorDisplay?.hide_details ?? "Hide backend error details";
  const rawResponseLabel =
    t?.errorDisplay?.raw_response ?? "Raw backend response";
  const copyLabel = t?.errorDisplay?.copy ?? "Copy error details";

  const handleCopy = async () => {
    try {
      await copyToClipboard(formattedDetail);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API might not be available in all contexts
    }
  };

  const handleDismiss = () => {
    onDismiss?.();
  };

  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 space-y-3">
      {/* Friendly message + actions */}
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-destructive" />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-destructive font-medium">
            {friendlyMessage}
          </p>
          {(status || errorCode) && (
            <p className="mt-1 text-xs text-destructive/70 font-mono">
              {status && `HTTP ${status}`}
              {status && errorCode && " • "}
              {errorCode && errorCode}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {onDismiss && (
            <Button
              variant="ghost"
              size="icon"
              onClick={handleDismiss}
              className="text-destructive/60 hover:text-destructive"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Collapsible raw backend error */}
      {hasDetail && (
        <div className="border-t border-destructive/20 pt-3 space-y-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-xs text-destructive/80 hover:text-destructive px-0"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            <ChevronDown
              className={`h-3.5 w-3.5 mr-1 transition-transform ${expanded ? "rotate-180" : ""}`}
            />
            {expanded ? hideDetailsLabel : showDetailsLabel}
          </Button>

          {expanded && (
            <div
              className="space-y-2 rounded bg-background/50 p-3"
              role="region"
              aria-label="Backend error details"
            >
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {rawResponseLabel}
                </p>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={handleCopy}
                  aria-label={copyLabel}
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5 text-emerald-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
              <pre className="text-[10px] text-foreground/90 font-mono whitespace-pre-wrap break-all max-h-60 overflow-auto">
                {formattedDetail}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Helper to extract error info from various error shapes
export function extractErrorInfo(err: unknown): {
  friendlyMessage: string;
  rawDetail?: unknown;
  status?: number;
  errorCode?: string;
} {
  // ApiRequestError from our api.ts
  if (err && typeof err === "object" && "detail" in err && "status" in err) {
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
  if (typeof err === "string") {
    return {
      friendlyMessage: err,
      rawDetail: err,
    };
  }

  // Unknown shape
  return {
    friendlyMessage: "An unknown error occurred",
    rawDetail: err,
  };
}
