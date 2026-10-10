import { getTranslations, type Locale } from '@/i18n/utils';

/**
 * Resolve a backend `error_code` into its translated, user-facing headline.
 *
 * The backend speaks English (`docs/api.md`) and may reword its prose, so its
 * sentences are display material, not copy. What it does guarantee is a stable
 * machine-readable code (registry: `backend/src/storico/api/error_codes.py`),
 * and this module is the one place that turns a code into the user's words.
 * Codes in the same semantic family share one sentence per locale instead of
 * 21 near-identical strings; the families and their copy live in the
 * `errorCodes` object of `src/i18n/en.json` and `src/i18n/es.json`.
 *
 * Returns `undefined` for anything unmapped — a code the frontend has not
 * learned yet (WU3 keeps adding registry codes), or a caller-supplied marker
 * like `BOARD_UNAVAILABLE` that never comes from the backend — so the caller
 * keeps its own message instead of rendering nothing.
 */
export function errorCodeHeadline(
  errorCode: string | undefined,
  locale: Locale,
): string | undefined {
  if (!errorCode) return undefined;
  const headlines = getTranslations(locale).errorCodes as Record<string, string | undefined>;
  return headlines[errorCode];
}
