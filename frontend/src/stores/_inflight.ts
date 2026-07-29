/**
 * Track an inflight promise so concurrent callers share a single underlying request.
 *
 * Returns a wrapper that:
 * - If a promise for the same key is already inflight, returns that same promise.
 * - If no promise is inflight, calls `factory()` and stores the result.
 * - Removes the promise from the map once it resolves or rejects, so subsequent
 *   calls after completion trigger a fresh fetch (refresh works).
 *
 * Usage:
 *   const inflight = createInflightTracker<string>();
 *   await inflight.run('projects', () => api.listProjects());
 *
 * NOTE: this is dedupe of *inflight* calls, NOT a result cache. Once the promise
 * settles, the slot is freed and the next call re-issues the request. Use this to
 * prevent N simultaneous callers from triggering N identical network requests
 * before the first one resolves.
 */
export function createInflightTracker<Key>() {
  const map = new Map<Key, Promise<unknown>>();
  return {
    run<T>(key: Key, factory: () => Promise<T>): Promise<T> {
      const existing = map.get(key) as Promise<T> | undefined;
      if (existing) return existing;
      const p = factory().finally(() => map.delete(key));
      map.set(key, p);
      return p;
    },
    /** Force a fresh fetch even if one is inflight. Use for explicit refresh. */
    forceRun<T>(key: Key, factory: () => Promise<T>): Promise<T> {
      map.delete(key);
      const p = factory().finally(() => map.delete(key));
      map.set(key, p);
      return p;
    },
    /** For tests — clear everything. */
    clear() {
      map.clear();
    },
  };
}
