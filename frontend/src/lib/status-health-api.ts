/**
 * The mockable fetch seam between the status island and the same-origin health endpoint.
 *
 * Pure IO: it calls `/api/health/services` (the public Astro endpoint that forwards the
 * backend's diagnostics document — see `src/pages/api/health/services.ts`) and parses the
 * answer through `parseServicesHealth`. No DOM and no i18n live here, so the outcome
 * mapping is testable in the node environment and the island can be tested by mocking
 * this module.
 *
 * The outcome union exists because the island must say four different things and a raw
 * `Response` says none of them well: the document arrived and is valid; something answered
 * but it is not a services document; something answered unwell (an HTTP error); or nothing
 * usable answered at all (timeout / transport failure).
 */
import { parseServicesHealth, type ServicesHealth } from '@/lib/health';

export type HealthOutcome =
  | { kind: 'ok'; health: ServicesHealth }
  /** 200 but the body is not a services document (e.g. the liveness payload shape). */
  | { kind: 'payload-invalid' }
  /** Something answered with a non-200 other than the endpoint's own 502/504. */
  | { kind: 'http-error'; status: number }
  /** Nothing usable answered: the endpoint's 502/504, an abort, or a failed fetch. */
  | { kind: 'unavailable'; reason: 'timeout' | 'transport' };

/** Default timeout, the same value the SSR page used before the client-fetch design. */
const DEFAULT_TIMEOUT_MS = 10_000;

export async function fetchServiceHealth(timeoutMs?: number): Promise<HealthOutcome> {
  try {
    const response = await fetch('/api/health/services', {
      signal: AbortSignal.timeout(timeoutMs ?? DEFAULT_TIMEOUT_MS),
    });

    if (response.status !== 200) {
      // 502 (`proxy_error`) and 504 (`proxy_timeout`) are the endpoint's own vocabulary
      // for "nothing usable answered from the backend", so they map to `unavailable`,
      // not to `http-error`.
      if (response.status === 502 || response.status === 504) {
        return { kind: 'unavailable', reason: 'transport' };
      }
      return { kind: 'http-error', status: response.status };
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      return { kind: 'payload-invalid' };
    }

    const health = parseServicesHealth(payload);
    return health ? { kind: 'ok', health } : { kind: 'payload-invalid' };
  } catch (error) {
    // `AbortSignal.timeout` rejects with `TimeoutError`; some engines surface the generic
    // `AbortError` name for the same condition, so both map to `timeout`.
    const name = error instanceof DOMException ? error.name : '';
    if (name === 'TimeoutError' || name === 'AbortError') {
      return { kind: 'unavailable', reason: 'timeout' };
    }
    return { kind: 'unavailable', reason: 'transport' };
  }
}
