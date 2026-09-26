import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as storiesApi from '@/lib/stories-api';
import { api, ApiRequestError } from '@/lib/api';

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    postForm: vi.fn(),
  },
  ApiRequestError: class ApiRequestErrorMock extends Error {
    status: number;
    statusText: string;
    detail: unknown;
    errorCode?: string;
    constructor(status: number, statusText: string, detail: unknown) {
      super(detail ? String(detail) : `HTTP ${status}`);
      this.name = 'ApiRequestError';
      this.status = status;
      this.statusText = statusText;
      this.detail = detail;
      // Mirror the real class: error_code is extracted from an object detail.
      if (typeof detail === 'object' && detail !== null) {
        this.errorCode = (detail as Record<string, unknown>).error_code as string | undefined;
      }
    }
  },
}));

describe('stories-api — importStories', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const file = new File(['actor,feature,benefit\nAs a user,I want in,so that out\n'], 'stories.csv', {
    type: 'text/csv',
  });

  it('posts FormData to the exact import URL with project_id and the same File instance', async () => {
    vi.mocked(api.postForm).mockResolvedValue({
      created: 1,
      skipped: 0,
      total_rows: 1,
      duplicates: [],
      story_ids: ['s1'],
    });

    await storiesApi.importStories({ workspaceId: 'ws-1', projectId: 'proj-9', file });

    expect(api.postForm).toHaveBeenCalledTimes(1);
    const [url, form] = vi.mocked(api.postForm).mock.calls[0];
    expect(url).toBe('/api/v1/workspaces/ws-1/stories/import');
    expect(form).toBeInstanceOf(FormData);
    expect(form.get('project_id')).toBe('proj-9');
    expect(form.get('file')).toBe(file);
  });

  it('camelCases the 201 snake_case body, including duplicate nested keys', async () => {
    vi.mocked(api.postForm).mockResolvedValue({
      created: 2,
      skipped: 2,
      total_rows: 4,
      duplicates: [
        { line: 3, reason: 'duplicate', existing_story_id: 'story-abc' },
        { line: 4, reason: 'duplicate_in_file', first_line: 2 },
      ],
      story_ids: ['story-1', 'story-2'],
    });

    const result = await storiesApi.importStories({ workspaceId: 'ws-1', projectId: 'p', file });

    expect(result).toStrictEqual({
      created: 2,
      skipped: 2,
      totalRows: 4,
      duplicates: [
        { line: 3, reason: 'duplicate', existingStoryId: 'story-abc' },
        { line: 4, reason: 'duplicate_in_file', firstLine: 2 },
      ],
      storyIds: ['story-1', 'story-2'],
    });
  });
});

describe('stories-api — readImportFailure', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('maps the frozen 422 IMPORT_VALIDATION_FAILED payload to a rows failure', () => {
    // Exact frozen inner payload (the outer `{detail: ...}` envelope is already
    // unwrapped by ApiRequestError, so `detail` here IS the inner object).
    const innerPayload = {
      detail: 'Import validation failed; no stories were created',
      error_code: 'IMPORT_VALIDATION_FAILED',
      created: 0,
      total_rows: 3,
      errors: [
        { line: 2, reason: 'too_long', field: 'actor', length: 320, max: 300 },
        { line: 3, reason: 'field_count_mismatch', observed: 2, expected: 4 },
      ],
      duplicates: [
        { line: 4, reason: 'duplicate', existing_story_id: 'story-abc' },
        { line: 5, reason: 'duplicate_in_file', first_line: 2 },
      ],
    };
    const error = new ApiRequestError(422, 'Unprocessable Entity', innerPayload);

    const failure = storiesApi.readImportFailure(error);

    expect(failure).toStrictEqual({
      kind: 'rows',
      totalRows: 3,
      errors: [
        { line: 2, reason: 'too_long', field: 'actor', length: 320, max: 300 },
        { line: 3, reason: 'field_count_mismatch', observed: 2, expected: 4 },
      ],
      duplicates: [
        { line: 4, reason: 'duplicate', existingStoryId: 'story-abc' },
        { line: 5, reason: 'duplicate_in_file', firstLine: 2 },
      ],
    });
  });

  it('maps the 422 IMPORT_FILE_REJECTED payload to a file failure with reason only', () => {
    const error = new ApiRequestError(422, 'Unprocessable Entity', {
      detail: 'CSV file rejected',
      error_code: 'IMPORT_FILE_REJECTED',
      reason: 'header_unrecognized',
    });

    const failure = storiesApi.readImportFailure(error);

    expect(failure).toStrictEqual({
      kind: 'file',
      errorCode: 'IMPORT_FILE_REJECTED',
      reason: 'header_unrecognized',
    });
  });

  it('maps the 413 IMPORT_FILE_TOO_LARGE payload with size and max', () => {
    const error = new ApiRequestError(413, 'Payload Too Large', {
      detail: 'CSV file too large',
      error_code: 'IMPORT_FILE_TOO_LARGE',
      size: 2097152,
      max: 1048576,
    });

    const failure = storiesApi.readImportFailure(error);

    expect(failure).toStrictEqual({
      kind: 'file',
      errorCode: 'IMPORT_FILE_TOO_LARGE',
      size: 2097152,
      max: 1048576,
    });
  });

  it('returns null for a plain Error', () => {
    expect(storiesApi.readImportFailure(new Error('Network error'))).toBeNull();
  });

  it('returns null for an ApiRequestError with an unrelated errorCode', () => {
    const error = new ApiRequestError(409, 'Conflict', {
      detail: 'Invalid state transition',
      error_code: 'INVALID_STATE_TRANSITION',
    });

    expect(storiesApi.readImportFailure(error)).toBeNull();
  });

  it('returns null for a non-object detail on an import errorCode', () => {
    const error = new ApiRequestError(422, 'Unprocessable Entity', 'plain string detail');

    expect(storiesApi.readImportFailure(error)).toBeNull();
  });

  it('does not throw when the validation payload is missing the errors key', () => {
    const error = new ApiRequestError(422, 'Unprocessable Entity', {
      detail: 'Import validation failed',
      error_code: 'IMPORT_VALIDATION_FAILED',
      created: 0,
      total_rows: 2,
      duplicates: [],
    });

    const failure = storiesApi.readImportFailure(error);

    expect(failure).toStrictEqual({
      kind: 'rows',
      totalRows: 2,
      errors: [],
      duplicates: [],
    });
  });
});
