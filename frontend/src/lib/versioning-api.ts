import { api } from './api';
import type { StoryVersion, RawStoryVersion } from '@/types/story';
import type {
  TaskInvalidation,
  RawTaskInvalidation,
  RepetitionMatch,
  RepetitionResponse,
  RawRepetitionMatch,
} from '@/types/task';

// ── Mapping helpers ──

function mapStoryVersion(raw: RawStoryVersion): StoryVersion {
  return {
    id: raw.id,
    versionNumber: raw.version_number,
    status: raw.status,
    modelUsed: raw.model_used,
    provider: raw.provider,
    temperature: raw.temperature,
    createdAt: raw.created_at,
    completedAt: raw.completed_at,
    errorInfo: raw.error_info,
    isCurrent: raw.is_current,
    hasOutput: raw.has_output,
  };
}

function mapInvalidation(raw: RawTaskInvalidation): TaskInvalidation {
  return {
    id: raw.id,
    reason: raw.reason,
    markedBy: raw.marked_by,
    markedAt: raw.marked_at,
    revokedBy: raw.revoked_by,
    revokedAt: raw.revoked_at,
  };
}

function mapRepetitionMatch(raw: RawRepetitionMatch): RepetitionMatch {
  return {
    versionNumber: raw.version_number,
    reason: raw.reason,
    markedAt: raw.marked_at,
  };
}

// ── Version selector read ──

/**
 * List every version of a story, ordered `version_number DESC` by the route,
 * deliberately unbounded — the selector shows the whole history.
 */
export async function listVersions(storyId: string): Promise<StoryVersion[]> {
  const raw = await api.get<RawStoryVersion[]>(`/api/v1/stories/${storyId}/versions`);
  return raw.map(mapStoryVersion);
}

// ── Invalidation marks ──

/** Mark a task invalid with a mandatory reason (201 with the stored mark). */
export async function createInvalidation(taskId: string, reason: string): Promise<TaskInvalidation> {
  const raw = await api.post<RawTaskInvalidation>(`/api/v1/tasks/${taskId}/invalidations`, {
    reason,
  });
  return mapInvalidation(raw);
}

/** Full mark history of a task, active mark first (the route orders `marked_at DESC`). */
export async function listInvalidations(taskId: string): Promise<TaskInvalidation[]> {
  const raw = await api.get<RawTaskInvalidation[]>(`/api/v1/tasks/${taskId}/invalidations`);
  return raw.map(mapInvalidation);
}

/**
 * Revoke a task's active mark (204). The row survives with its attribution;
 * revoking without an active mark is a 404 the caller surfaces.
 */
export async function revokeInvalidation(taskId: string): Promise<void> {
  await api.delete(`/api/v1/tasks/${taskId}/invalidations/current`);
}

/** The D16 read: marks on other versions whose normalized title equals this task's. */
export async function fetchRepetition(taskId: string): Promise<RepetitionResponse> {
  const raw = await api.get<{ matches: RawRepetitionMatch[] }>(
    `/api/v1/tasks/${taskId}/invalidations/repetition`,
  );
  return { matches: raw.matches.map(mapRepetitionMatch) };
}
