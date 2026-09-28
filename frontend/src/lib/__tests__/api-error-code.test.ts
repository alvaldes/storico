import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, ApiRequestError } from '@/lib/api';

/**
 * The envelope WU1/WU2 ship puts `error_code` at the top level of the response
 * body, next to `detail`. Until WU4 moves them, six routes still nest their
 * code inside `detail` instead. The transport layer must read the canonical
 * shape first and keep the nested one as a fallback — before this change the
 * top-level code was silently dropped and `errorCode` stayed `undefined`.
 */
function errorResponse(status: number, statusText: string, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ApiRequestError — reading the canonical envelope', () => {
  it('reads the top-level error_code of the canonical envelope', () => {
    const prose = "Workspace with id 'abc' not found";
    const err = new ApiRequestError(404, 'Not Found', prose, {
      error_code: 'ENTITY_NOT_FOUND',
      detail: prose,
    });

    expect(err.errorCode).toBe('ENTITY_NOT_FOUND');
    expect(err.rawError.errorCode).toBe('ENTITY_NOT_FOUND');
  });

  it('reads the top-level code even when detail is a plain string and nothing else is structured', () => {
    // The case that silently returned `undefined` before: `detail` is a string,
    // so the old object-only extraction never ran at all.
    const err = new ApiRequestError(500, 'Internal Server Error', 'Something went wrong', {
      error_code: 'INTERNAL_ERROR',
      detail: 'Something went wrong',
    });

    expect(err.errorCode).toBe('INTERNAL_ERROR');
  });

  it('keeps the nested detail.error_code as the fallback while WU4 moves those routes', () => {
    const detail = {
      error_code: 'INVALID_STATE_TRANSITION',
      current_state: 'todo',
      attempted_state: 'done',
    };
    const err = new ApiRequestError(409, 'Conflict', detail, { detail });

    expect(err.errorCode).toBe('INVALID_STATE_TRANSITION');
    expect(err.currentState).toBe('todo');
    expect(err.attemptedState).toBe('done');
  });

  it('prefers the top-level code when both shapes arrive at once', () => {
    const nested = { error_code: 'IMPORT_FILE_REJECTED', reason: 'not a csv' };
    const err = new ApiRequestError(400, 'Bad Request', nested, {
      error_code: 'ENTITY_NOT_FOUND',
      detail: nested,
    });

    expect(err.errorCode).toBe('ENTITY_NOT_FOUND');
  });

  it('stays undefined when the body carries no code', () => {
    const err = new ApiRequestError(500, 'Internal Server Error', 'boom', 'boom');

    expect(err.errorCode).toBeUndefined();
    // Downstream consumers (taskStore, KanbanBoard, ImportStoriesDialog) branch
    // on these codes; a missing one must not become an empty string.
    expect(err.isInvalidStateTransition()).toBe(false);
  });
});

describe('the transport layer surfaces the top-level code end to end', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('populates errorCode from a real fetch response carrying the canonical envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      errorResponse(500, 'Internal Server Error', {
        error_code: 'INTERNAL_ERROR',
        detail: 'Something went wrong on the server',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const caught = await api.get('/api/v1/projects/').catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(ApiRequestError);
    expect((caught as ApiRequestError).errorCode).toBe('INTERNAL_ERROR');
    // The prose stays exactly where the disclosure panel reads it from.
    expect((caught as ApiRequestError).detail).toBe('Something went wrong on the server');
  });
});
