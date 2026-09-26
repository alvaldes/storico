// @vitest-environment node
// The route under test is pure server code (fetch, FormData, node:http stub),
// so this file opts out of jsdom on purpose (the setup file already guards for
// this pragma).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import type { AddressInfo } from 'node:net';
import { getSession } from 'auth-astro/server';
import { ALL } from '../v1/[...path].ts';

vi.mock('auth-astro/server', () => ({
  getSession: vi.fn(),
}));

// The config module reads import.meta.env at import time; mock the export the
// route actually consumes. `mockApiUrl` is filled in once the stub is listening.
vi.mock('@/lib/config', () => ({
  config: {
    get apiUrl() {
      return mockApiUrl;
    },
    authSecret: 'test-auth-secret',
    github: { clientId: '', clientSecret: '' },
    google: { clientId: '', clientSecret: '' },
  },
}));

interface RecordedRequest {
  method: string;
  url: string;
  contentType: string | undefined;
  body: Buffer;
}

let mockApiUrl = '';
let server: Server | undefined;
let requests: RecordedRequest[] = [];

/** Start a stub backend on 127.0.0.1 with an ephemeral port and point config.apiUrl at it. */
async function startStub(answer?: (req: IncomingMessage, res: ServerResponse) => void) {
  server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => {
      requests.push({
        method: req.method ?? '',
        url: req.url ?? '',
        contentType: req.headers['content-type'],
        body: Buffer.concat(chunks),
      });
      if (answer) {
        answer(req, res);
        return;
      }
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ ok: true }));
    });
  });
  await new Promise<void>((resolve) => server!.listen(0, '127.0.0.1', resolve));
  mockApiUrl = `http://127.0.0.1:${(server!.address() as AddressInfo).port}`;
}

function boundaryOf(contentType: string): string {
  const match = contentType.match(/boundary=([^;]+)/);
  expect(match, `content-type "${contentType}" must carry a boundary`).not.toBeNull();
  return match![1];
}

/** Authenticated session for the happy-path cases. */
function authAsUser() {
  vi.mocked(getSession).mockResolvedValue({ user: { id: 'user-1' } } as never);
}

/** Fire the catch-all handler with a Request and return its Response. */
function callRoute(request: Request): Promise<Response> {
  return Promise.resolve(ALL({ request } as never));
}

afterEach(async () => {
  vi.useRealTimers();
  vi.mocked(getSession).mockReset();
  requests = [];
  if (server) {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server!.close(() => resolve()));
    server = undefined;
  }
});

describe('proxy /api/v1 [...path] multipart forwarding', () => {
  it('forwards a multipart upload byte for byte with the client boundary', async () => {
    await startStub();
    authAsUser();

    const csv = 'name,note\n"Vald\u00e9s, Angel","line1\nline2"\n';
    const form = new FormData();
    form.append('file', new File([csv], 'stories.csv', { type: 'text/csv' }));

    const request = new Request('http://frontend.local/api/v1/stories/import', {
      method: 'POST',
      body: form,
    });
    const expectedBytes = await request.clone().arrayBuffer();
    const expectedContentType = request.headers.get('content-type')!;

    const response = await callRoute(request);

    expect(response.status).toBe(200);
    expect(requests).toHaveLength(1);
    const received = requests[0];
    // Pin the boundary: the proxy must reuse the client's exact content type,
    // because the boundary cannot be reconstructed after buffering the bytes.
    expect(received.contentType).toBe(expectedContentType);
    expect(received.contentType).not.toBe('application/json');
    expect(boundaryOf(received.contentType!)).toBe(boundaryOf(expectedContentType));
    // Byte-exact forwarding: compare the whole buffer, not its length plus a couple of
    // substrings. A same-length corruption outside those spans would have passed, which is
    // the difference between pinning a byte count and pinning the bytes.
    expect(Buffer.compare(received.body, Buffer.from(expectedBytes))).toBe(0);
    expect(await response.json()).toEqual({ ok: true });
  });

  it('survives a ~1 MB multipart upload without truncation', async () => {
    await startStub();
    authAsUser();

    const row = 'row,001,"text with, comma and \\"quote\\""\n';
    const csv = row.repeat(Math.ceil(1_000_000 / row.length));
    expect(csv.length).toBeGreaterThanOrEqual(1_000_000);

    const form = new FormData();
    form.append('file', new File([csv], 'big.csv', { type: 'text/csv' }));

    const request = new Request('http://frontend.local/api/v1/stories/import', {
      method: 'POST',
      body: form,
    });
    const expectedBytes = await request.clone().arrayBuffer();

    const response = await callRoute(request);

    expect(response.status).toBe(200);
    expect(requests).toHaveLength(1);
    // Pin the exact size: a truncated or re-encoded body cannot pass this.
    expect(requests[0].body.length).toBe(expectedBytes.byteLength);
    // Full-buffer equality as well: the length alone cannot catch a corruption that
    // preserves it.
    expect(Buffer.compare(requests[0].body, Buffer.from(expectedBytes))).toBe(0);
    expect(requests[0].body.toString('utf8')).toContain('"text with, comma and \\"quote\\""');
  });

  it('forwards a file whose bytes are not valid UTF-8', async () => {
    await startStub();
    authAsUser();

    // The payload that gives the byte-exactness assertion teeth. Every other case here is
    // valid UTF-8, so decoding to text and re-encoding round-trips it unchanged and a
    // `request.text()` regression would sail through. These bytes do not survive that trip:
    // the invalid sequences become U+FFFD, the length changes, and the file is corrupt in a
    // way the user would only discover as a rejected import.
    const binary = new Uint8Array([0xff, 0xfe, 0x00, 0x80, 0xc3, 0x28, 0xed, 0xa0, 0x80]);
    const form = new FormData();
    form.append('file', new File([binary], 'datos-\u00f1-\u65e5\u672c.csv', { type: 'text/csv' }));

    const request = new Request('http://frontend.local/api/v1/stories/import', {
      method: 'POST',
      body: form,
    });
    const expectedBytes = await request.clone().arrayBuffer();

    const response = await callRoute(request);

    expect(response.status).toBe(200);
    expect(Buffer.compare(requests[0].body, Buffer.from(expectedBytes))).toBe(0);
    // The non-ASCII filename travels inside the body too, so it is covered by the compare
    // above rather than asserted separately.
  });

  it('keeps the JSON branch unchanged', async () => {
    await startStub();
    authAsUser();

    const payload = JSON.stringify({ title: 'New story', priority: 2 });
    const request = new Request('http://frontend.local/api/v1/stories', {
      method: 'POST',
      body: payload,
      headers: { 'content-type': 'application/json' },
    });

    const response = await callRoute(request);

    expect(response.status).toBe(200);
    expect(requests).toHaveLength(1);
    expect(requests[0].body.toString('utf8')).toBe(payload);
    expect(requests[0].contentType).toBe('application/json');
    expect(await response.json()).toEqual({ ok: true });
  });

  it('sends a bodyless GET with no content-type set by the proxy', async () => {
    await startStub();
    authAsUser();

    const request = new Request('http://frontend.local/api/v1/stories?page=2');

    const response = await callRoute(request);

    expect(response.status).toBe(200);
    expect(requests).toHaveLength(1);
    expect(requests[0].method).toBe('GET');
    expect(requests[0].body.length).toBe(0);
    expect(requests[0].contentType).toBeUndefined();
    expect(requests[0].url).toBe('/api/v1/stories?page=2');
  });

  it('answers 401 and never reaches the backend without a session', async () => {
    await startStub();
    vi.mocked(getSession).mockResolvedValue(null as never);

    const request = new Request('http://frontend.local/api/v1/stories', {
      method: 'POST',
      body: '{"x":1}',
      headers: { 'content-type': 'application/json' },
    });

    const response = await callRoute(request);

    expect(response.status).toBe(401);
    expect(requests).toHaveLength(0);
    expect(await response.json()).toEqual({ detail: 'Unauthorized', type: 'auth_required' });
  });

  it('returns 504 when the backend never answers (timeout still applies)', async () => {
    await startStub(() => {
      /* never answer */
    });
    authAsUser();

    // BACKEND_TIMEOUT is a fixed 120s constant on the route, with no injection
    // point. Waiting two minutes in a test is not acceptable, and faking timers
    // corrupts undici's abort path (the fetch rejects as a socket error instead
    // of an AbortError), so only the 120s timer is accelerated to 100ms of real
    // time. The abort, the rejection and the 504 mapping all stay real.
    const realSetTimeout = globalThis.setTimeout;
    const shorten = vi
      .spyOn(globalThis, 'setTimeout')
      .mockImplementation(((
        handler: (...args: unknown[]) => void,
        timeout?: number,
        ...args: unknown[]
      ) =>
        realSetTimeout(handler, timeout === 120_000 ? 100 : timeout, ...args)) as unknown as typeof setTimeout);

    try {
      const request = new Request('http://frontend.local/api/v1/stories', {
        method: 'POST',
        body: '{"x":1}',
        headers: { 'content-type': 'application/json' },
      });

      const response = await callRoute(request);

      expect(response.status).toBe(504);
      expect(await response.json()).toEqual({ detail: 'Backend timeout', type: 'proxy_timeout' });
    } finally {
      shorten.mockRestore();
    }
  });
});
