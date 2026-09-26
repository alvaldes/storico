import {
  ApiRequestError,
  api,
} from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type {
  StoryImportDuplicate,
  StoryImportIssue,
  UserStory,
  UserStoryStatus,
  StoryImportReport,
  StoryImportFailure,
} from '@/types/story';
import type { CreateStoryParams, UpdateStoryParams } from '@/schemas';
import type { PaginatedResponse } from './projects-api';

/** Create a new user story. */
export async function createStory(params: CreateStoryParams): Promise<UserStory> {
  const raw = await api.post<Record<string, unknown>>('/api/v1/stories/', toSnakeCase(params));
  return toCamelCase<UserStory>(raw);
}

/** List user stories with optional project filter, workspace filter, and pagination. */
export async function listStories(
  projectId?: string,
  page = 1,
  size = 20,
  workspaceId?: string,
): Promise<PaginatedResponse<UserStory>> {
  let path = `/api/v1/stories/?page=${page}&size=${size}`;
  if (projectId) {
    path += `&project_id=${projectId}`;
  }
  if (workspaceId) {
    path += `&workspace_id=${workspaceId}`;
  }
  const raw = await api.get<Record<string, unknown>>(path);
  return toCamelCase<PaginatedResponse<UserStory>>(raw);
}

/** Get a single user story by ID. */
export async function getStory(id: string): Promise<UserStory> {
  const raw = await api.get<Record<string, unknown>>(`/api/v1/stories/${id}`);
  return toCamelCase<UserStory>(raw);
}

/** Update an existing user story. */
export async function updateStory(id: string, params: UpdateStoryParams): Promise<UserStory> {
  const raw = await api.put<Record<string, unknown>>(`/api/v1/stories/${id}`, toSnakeCase(params));
  return toCamelCase<UserStory>(raw);
}

/** Delete a user story by its ID. */
export async function deleteStory(id: string): Promise<void> {
  await api.delete(`/api/v1/stories/${id}`);
}

/* ── CSV import ── */

export interface ImportStoriesParams {
  workspaceId: string;
  projectId: string;
  file: File;
}

/**
 * Import user stories from a CSV file into a project.
 *
 * The multipart form fields are named by the backend and are NOT JSON keys, so
 * `project_id` stays snake_case (it is a form field name, not an object key).
 * The success body is raw snake_case JSON from `postForm`, so it is camelCased here.
 */
export async function importStories({
  workspaceId,
  projectId,
  file,
}: ImportStoriesParams): Promise<StoryImportReport> {
  const form = new FormData();
  form.append('project_id', projectId);
  form.append('file', file);
  const raw = await api.postForm<Record<string, unknown>>(
    `/api/v1/workspaces/${workspaceId}/stories/import`,
    form,
  );
  return toCamelCase<StoryImportReport>(raw);
}

/** Error codes the import endpoint can fail with. */
const IMPORT_ERROR_CODES = new Set([
  'IMPORT_VALIDATION_FAILED',
  'IMPORT_FILE_REJECTED',
  'IMPORT_FILE_TOO_LARGE',
]);

/**
 * Turn a thrown error into a typed StoryImportFailure, or null when the error
 * is not an import failure (the caller then falls back to its generic error
 * display).
 *
 * Shape trap: the SUCCESS body is camelCased by `toCamelCase` before it
 * reaches the caller, but the ERROR body arrives raw and snake_case inside
 * `ApiRequestError.detail` (which is the inner payload, already unwrapped from
 * the top-level `{detail: ...}` envelope). The two shapes do not match, and we
 * must not assume they do.
 *
 * Absent optionals: we normalize the detail with `toCamelCase`, which only
 * iterates keys that are actually present, so an absent optional key stays
 * absent (no `undefined` values that would break a `toStrictEqual`).
 * `toCamelCase` is idempotent on already-camelCase keys, so this also handles
 * the (hypothetical) case of a backend that emits camelCase error bodies.
 */
export function readImportFailure(error: unknown): StoryImportFailure | null {
  if (!(error instanceof ApiRequestError)) return null;
  if (error.errorCode === undefined || !IMPORT_ERROR_CODES.has(error.errorCode)) return null;
  if (typeof error.detail !== 'object' || error.detail === null) return null;

  // Normalized copy of the raw snake_case detail (see docstring re: shapes).
  const payload = toCamelCase<Record<string, unknown>>(error.detail);

  if (error.errorCode === 'IMPORT_VALIDATION_FAILED') {
    // Defensive: a malformed body must degrade to empty arrays rather than
    // crash the dialog that is trying to display the failure.
    const errors = Array.isArray(payload.errors) ? (payload.errors as StoryImportIssue[]) : [];
    const duplicates = Array.isArray(payload.duplicates)
      ? (payload.duplicates as StoryImportDuplicate[])
      : [];
    return {
      kind: 'rows',
      totalRows: typeof payload.totalRows === 'number' ? payload.totalRows : 0,
      errors,
      duplicates,
    };
  }

  // Build conditionally so an absent optional stays absent (an explicit
  // `reason: undefined` key would break a `toStrictEqual` against a payload
  // where the key is simply missing).
  const failure: StoryImportFailure = {
    kind: 'file',
    errorCode: error.errorCode as 'IMPORT_FILE_REJECTED' | 'IMPORT_FILE_TOO_LARGE',
  };
  const file = failure as { reason?: string; size?: number; max?: number };
  if (typeof payload.reason === 'string') file.reason = payload.reason;
  if (typeof payload.size === 'number') file.size = payload.size;
  if (typeof payload.max === 'number') file.max = payload.max;
  return failure;
}
