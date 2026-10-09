import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { updateTask, updateTaskStatus } from '@/lib/tasks-api';
import { resetBlockingLoader, useLoadingStore } from '@/stores/loadingStore';

/**
 * Tests that ApiClient mutations actually drive the loading store, while
 * reads and excluded writes never touch it. Follows the pattern of
 * api-formdata.test.ts: real ApiClient, stubbed global fetch.
 */
describe('ApiClient blocking-request wiring', () => {
  beforeEach(() => {
    resetBlockingLoader();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    resetBlockingLoader();
  });

  function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  /** A fetch whose promise we hold open until the test releases it. */
  function deferredFetch(): {
    fetchMock: ReturnType<typeof vi.fn>;
    resolve: (response: Response) => void;
  } {
    let release: (response: Response) => void = () => {};
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const fetchMock = vi.fn().mockReturnValue(gate);
    vi.stubGlobal('fetch', fetchMock);
    return { fetchMock, resolve: release };
  }

  it('a POST holds pending at 1 while in flight and returns it to 0 after settling', async () => {
    const { resolve } = deferredFetch();

    const inFlight = api.post('/api/v1/stories/', {});
    expect(useLoadingStore.getState().pending).toBe(1);

    resolve(jsonResponse(201, { id: 's-1' }));
    await inFlight;
    expect(useLoadingStore.getState().pending).toBe(0);
  });

  it('a GET never touches the counter', async () => {
    const { resolve } = deferredFetch();

    const inFlight = api.get('/api/v1/stories/');
    expect(useLoadingStore.getState().pending).toBe(0);

    resolve(jsonResponse(200, { items: [] }));
    await inFlight;
    expect(useLoadingStore.getState().pending).toBe(0);
  });

  it('the automatic onboarding write is excluded and never touches the counter', async () => {
    // Not deferred: the increment, if it happened, is synchronous — `request()`
    // calls `beginBlockingRequest()` before its first `await`. A resolved mock
    // therefore already proves the counter is untouched at the moment the
    // request would have started, which is the assertion that matters.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(200, { ok: true }))),
    );

    // The real call site is a PATCH (`lib/user-api.ts`). The exclusion is
    // deliberately path-scoped, so both methods on that path must be exempt —
    // asserting POST too pins that the exclusion does not depend on the verb.
    const patched = api.patch('/api/v1/users/me/onboarding', {});
    expect(useLoadingStore.getState().pending).toBe(0);

    const posted = api.post('/api/v1/users/me/onboarding');
    expect(useLoadingStore.getState().pending).toBe(0);

    await Promise.all([patched, posted]);
    expect(useLoadingStore.getState().pending).toBe(0);
  });

  it('a rejected fetch still releases the counter, so a network failure cannot strand the overlay', async () => {
    // The failure mode this pins is the worst one for this feature: an overlay
    // that never comes down. `fetch` rejecting is a different path from an
    // error RESPONSE (no `Response` object is ever built), and it is what a
    // dropped connection produces.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    await expect(api.post('/api/v1/stories/', {})).rejects.toThrow(TypeError);

    expect(useLoadingStore.getState().pending).toBe(0);
    expect(useLoadingStore.getState().visible).toBe(false);
  });

  it('a DELETE counts as one blocking request in flight', async () => {
    const { resolve } = deferredFetch();

    const inFlight = api.delete('/api/v1/stories/s-1');
    expect(useLoadingStore.getState().pending).toBe(1);

    resolve(jsonResponse(204, undefined));
    await inFlight;
    expect(useLoadingStore.getState().pending).toBe(0);
  });

  it('an error response still releases the counter through the finally path', async () => {
    const { resolve } = deferredFetch();

    const inFlight = api.post('/api/v1/stories/', {});
    expect(useLoadingStore.getState().pending).toBe(1);

    resolve(jsonResponse(500, { detail: 'boom' }));
    await expect(inFlight).rejects.toThrow();
    // The assertion IS the finally guarantee: the error surfaced AND pending
    // went back to zero, so the overlay cannot be left stuck after a failure.
    expect(useLoadingStore.getState().pending).toBe(0);
  });

  it('a postForm (CSV import) blocks like any other write', async () => {
    const { resolve } = deferredFetch();

    const inFlight = api.postForm('/api/v1/stories/import', new FormData());
    expect(useLoadingStore.getState().pending).toBe(1);

    resolve(jsonResponse(200, { created: 1 }));
    await inFlight;
    expect(useLoadingStore.getState().pending).toBe(0);
  });

  it('the task-status PUT is excluded for BOTH callers — card move and editor save never touch the counter (D11)', async () => {
    // Not deferred, for the same reason as the onboarding case: the increment,
    // if it happened, is synchronous before the first await. Both client
    // functions share the same `PUT /api/v1/tasks/{id}` (tasks-api.ts), so the
    // exclusion is pinned through their real call path, not a synthetic one.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(200, { ok: true }))),
    );

    // The card move (`updateTaskStatus`): optimistic, the card carries its own
    // in-flight indicator.
    const moved = updateTaskStatus('task-1', 'done');
    expect(useLoadingStore.getState().pending).toBe(0);
    await moved;
    expect(useLoadingStore.getState().pending).toBe(0);

    // The editor's save (`updateTask`): it has its own `saving` spinner and
    // success toast, so the same exclusion holds for it for the same reason.
    const saved = updateTask('task-1', { status: 'todo' });
    expect(useLoadingStore.getState().pending).toBe(0);
    await saved;
    expect(useLoadingStore.getState().pending).toBe(0);
  });
});
