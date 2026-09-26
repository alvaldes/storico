import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError, api } from '@/lib/api';

/**
 * Tests for the real ApiClient's fetch behaviour.
 *
 * The other API tests mock `@/lib/api` wholesale, so nothing else pins what
 * `request`/`postForm` actually send over the wire. These tests stub the
 * global `fetch` and assert on the arguments it received.
 */

const IMPORT_ERROR_BODY = {
  detail: {
    detail: 'The file has rows that must be fixed.',
    error_code: 'IMPORT_VALIDATION_FAILED',
    created: 0,
    total_rows: 44,
    errors: [{ line: 7, reason: 'missing_field' }],
    duplicates: [],
  },
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ApiClient fetch behaviour', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('post() sends Content-Type application/json and a JSON.stringify body, and parses the response', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { ok: true }));

    const result = await api.post('/x', { a: 1 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/x');
    expect(options.method).toBe('POST');
    expect((options.headers as Record<string, string>)['Content-Type']).toBe(
      'application/json',
    );
    expect(options.body).toBe(JSON.stringify({ a: 1 }));
    expect(result).toEqual({ ok: true });
  });

  it('postForm() sets no Content-Type header and passes the FormData instance as-is', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { created: 3 }));

    const form = new FormData();
    form.append('file', new Blob(['a,b\n1,2'], { type: 'text/csv' }), 'stories.csv');

    const result = await api.postForm('/x', form);

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = options.headers ?? {};
    // Explicit absence: the browser must supply multipart/form-data; boundary=...
    expect('Content-Type' in headers).toBe(false);
    expect(headers).not.toHaveProperty('Content-Type');
    // Same FormData instance, not JSON.stringify-ed into a string
    expect(options.body).toBe(form);
    expect(typeof options.body).not.toBe('string');
    expect(result).toEqual({ created: 3 });
  });

  it('postForm() uses POST and the path it was given', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}));

    await api.postForm('/api/v1/stories/import', new FormData());

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(options.method).toBe('POST');
    expect(url).toBe('/api/v1/stories/import');
  });

  it('a JSON-path error keeps the frozen error contract', async () => {
    fetchMock.mockResolvedValue(jsonResponse(422, IMPORT_ERROR_BODY));

    const err = await api.post('/import', { project_id: 'p1' }).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiRequestError);
    const apiErr = err as ApiRequestError;
    expect(apiErr.status).toBe(422);
    expect(apiErr.errorCode).toBe('IMPORT_VALIDATION_FAILED');
    expect(apiErr.detail).toEqual(IMPORT_ERROR_BODY.detail);
    expect((apiErr.detail as { errors: { reason: string }[] }).errors[0].reason).toBe(
      'missing_field',
    );
    expect(apiErr.rawError.rawBody).toEqual(IMPORT_ERROR_BODY);
  });

  it('a postForm-path error keeps the same frozen error contract through the shared helper', async () => {
    fetchMock.mockResolvedValue(jsonResponse(422, IMPORT_ERROR_BODY));

    const err = await api.postForm('/import', new FormData()).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiRequestError);
    const apiErr = err as ApiRequestError;
    expect(apiErr.status).toBe(422);
    expect(apiErr.errorCode).toBe('IMPORT_VALIDATION_FAILED');
    expect(apiErr.detail).toEqual(IMPORT_ERROR_BODY.detail);
    expect((apiErr.detail as { errors: { reason: string }[] }).errors[0].reason).toBe(
      'missing_field',
    );
    expect(apiErr.rawError.rawBody).toEqual(IMPORT_ERROR_BODY);
  });

  it('a non-JSON error body produces an ApiRequestError with the text as detail', async () => {
    fetchMock.mockResolvedValue(new Response('Internal Server Error', { status: 500 }));

    const err = await api.get('/x').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiRequestError);
    const apiErr = err as ApiRequestError;
    expect(apiErr.status).toBe(500);
    expect(apiErr.detail).toBe('Internal Server Error');
    expect(apiErr.rawError.rawBody).toBe('Internal Server Error');
  });
});
