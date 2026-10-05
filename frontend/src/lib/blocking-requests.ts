/**
 * Pure decision module for the full-page blocking loader.
 *
 * No React, no browser APIs: both the loader wiring and the tests can import
 * this without rendering anything. Whether a request blocks is a function of
 * (method, path) alone.
 */

/**
 * Requests that mutate but must NOT trigger the full-page overlay.
 *
 * Each entry documents itself via `why`: the reason this write is invisible
 * to the loader is a product decision, not an accident, and the test pins
 * that every reason was actually written down.
 */
export const BLOCKING_EXCLUSIONS: readonly {
  readonly match: RegExp;
  readonly why: string;
}[] = [
  {
    match: /^\/api\/v1\/users\/me\/onboarding$/,
    why: 'Automatic first-login write fired by the onboarding modal: not a user-initiated operation anyone waits on.',
  },
  {
    match: /^\/api\/v1\/workspaces\/[^/]+\/settings\/llm\/models$/,
    why: 'Automatic model probe. It is a POST only because the selection can carry an API key that must not land in an access log query string, not because the user asked for it.',
  },
  {
    match: /^\/api\/v1\/workspaces\/[^/]+\/extract\/$/,
    why: 'Extraction start answers 202 immediately and the story page already owns the pending UI (version selector, toast, poll), so a page-wide overlay would be a second, contradicting signal.',
  },
] as const;

const BLOCKING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * True when the request should hold the full-page loader open.
 *
 * Reads are exempt by design: the 2 s extraction poll and every background
 * refresh are GETs, so method filtering is what keeps them out of the
 * overlay. Query strings and hashes are stripped before matching so an
 * exclusion cannot be dodged (or accidentally triggered) by its parameters.
 */
export function shouldBlockRequest(method: string, path: string): boolean {
  if (!BLOCKING_METHODS.has(method.toUpperCase())) return false;
  const stripped = path.split(/[?#]/)[0];
  return !BLOCKING_EXCLUSIONS.some((exclusion) => exclusion.match.test(stripped));
}
