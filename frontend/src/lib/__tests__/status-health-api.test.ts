// @vitest-environment node
//
// This module is pure IO against one fixed same-origin URL: no DOM, no i18n. The node
// environment keeps it out of the jsdom suite and lets the test stub `globalThis.fetch`
// directly.
import { describe, it, expect, vi, afterEach } from 'vitest';

import { fetchServiceHealth } from '@/lib/status-health-api';

/** A minimal but fully valid services document, as the backend publishes it. */
const VALID_DOCUMENT = {
  status: 'ok',
  version: '1.0.0',
  timestamp: '2026-09-25T12:00:00Z',
  services: {
    database: { status: 'ok', latency_ms: 2 },
    schema: { status: 'ok', latency_ms: 1 },
  },
};

/** The liveness payload of `GET /api/v1/health`: no `services` key, probes at top level. */
const LIVENESS_PAYLOAD = {
  status: 'ok',
  version: '1.0.0',
  timestamp: '2026-09-25T12:00:00Z',
  database: { status: 'ok', latency_ms: 2 },
  schema: { status: 'ok', latency_ms: 1 },
};

function mockFetchOnce(implementation: () => Promise<Response> | never) {
  vi.stubGlobal('fetch', vi.fn(implementation));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchServiceHealth', () => {
  it('maps a 200 with a valid services document to ok', async () => {
    mockFetchOnce(() =>
      Promise.resolve(new Response(JSON.stringify(VALID_DOCUMENT), { status: 200 })),
    );

    const outcome = await fetchServiceHealth();

    expect(outcome).toEqual({ kind: 'ok', health: expect.objectContaining({ status: 'ok' }) });
  });

  it('maps a 200 whose JSON is not a services document (liveness shape) to payload-invalid', async () => {
    mockFetchOnce(() =>
      Promise.resolve(new Response(JSON.stringify(LIVENESS_PAYLOAD), { status: 200 })),
    );

    const outcome = await fetchServiceHealth();

    expect(outcome).toEqual({ kind: 'payload-invalid' });
  });

  it('maps the endpoint 502 (proxy_error) to unavailable', async () => {
    mockFetchOnce(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'Backend unavailable', type: 'proxy_error' }), {
          status: 502,
        }),
      ),
    );

    const outcome = await fetchServiceHealth();

    expect(outcome).toEqual({ kind: 'unavailable', reason: 'transport' });
  });

  it('maps the endpoint 504 (proxy_timeout) to unavailable', async () => {
    mockFetchOnce(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'Backend timeout', type: 'proxy_timeout' }), {
          status: 504,
        }),
      ),
    );

    const outcome = await fetchServiceHealth();

    expect(outcome).toEqual({ kind: 'unavailable', reason: 'transport' });
  });

  it('maps an aborted fetch (AbortError) to unavailable with reason timeout', async () => {
    mockFetchOnce(() => Promise.reject(new DOMException('The operation was aborted.', 'AbortError')));

    const outcome = await fetchServiceHealth();

    expect(outcome).toEqual({ kind: 'unavailable', reason: 'timeout' });
  });

  it('maps a plain rejection to unavailable with reason transport', async () => {
    mockFetchOnce(() => Promise.reject(new TypeError('Failed to fetch')));

    const outcome = await fetchServiceHealth();

    expect(outcome).toEqual({ kind: 'unavailable', reason: 'transport' });
  });

  it('maps any other non-200 answer to http-error with its status', async () => {
    mockFetchOnce(() => Promise.resolve(new Response('nope', { status: 500 })));

    const outcome = await fetchServiceHealth();

    expect(outcome).toEqual({ kind: 'http-error', status: 500 });
  });
});
