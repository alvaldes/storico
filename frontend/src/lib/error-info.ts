/**
 * One shape for a failure worth showing, and the single normaliser that produces it.
 *
 * Stores used to flatten whatever a `catch` caught to `err.message`. That threw away everything
 * the API layer had already captured — the HTTP status, the machine-readable error code, and the
 * raw response body — and `ErrorDisplay` renders all three. The loss was visible in the product:
 * the error card could not say what the server had actually answered.
 *
 * It lives in `lib/` rather than in the component that renders it. Stores normalise errors too,
 * and a store importing a React component to do it would drag the component tree into the
 * store's module graph for a pure function.
 */

import { ApiRequestError } from '@/lib/api';

export interface ErrorInfo {
  /** Message safe to show the user. */
  friendlyMessage: string;
  /** The raw response body, for the disclosure panel. */
  rawDetail?: unknown;
  /** HTTP status, when the failure came from a response. */
  status?: number;
  /** Machine-readable code, when the backend sent one. */
  errorCode?: string;
}

/** The fallback when a `catch` produced something with nothing readable in it at all. */
const GENERIC_MESSAGE = 'An unknown error occurred';

/**
 * Normalise anything a `catch` can hand over into `ErrorInfo`.
 *
 * `ApiRequestError` is matched **by class, first**. An earlier copy of this function tested for
 * `'detail' in err && 'status' in err` instead, which any object carrying those two keys would
 * satisfy — and it also missed `toErrorInfo()`, where the raw body and the structured fields of
 * an `INVALID_STATE_TRANSITION` response are captured.
 *
 * `fallbackMessage` exists so a caller whose failure has its own user-facing name can keep it
 * without re-implementing the rest of the normalisation.
 */
export function extractErrorInfo(err: unknown, fallbackMessage: string = GENERIC_MESSAGE): ErrorInfo {
  if (err instanceof ApiRequestError) return err.toErrorInfo();
  if (err instanceof Error) return { friendlyMessage: err.message, rawDetail: err.message };
  if (typeof err === 'string') return { friendlyMessage: err, rawDetail: err };
  return { friendlyMessage: fallbackMessage, rawDetail: err };
}
