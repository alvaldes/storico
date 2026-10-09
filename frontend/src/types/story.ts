/** User story extraction lifecycle status — matches backend UserStoryStatus enum. */
export type UserStoryStatus =
  'pending_extraction' | 'extracting' | 'extracted' | 'failed_extraction';

/** All valid UserStoryStatus values in lifecycle order. */
export const USER_STORY_STATUSES: UserStoryStatus[] = [
  'pending_extraction',
  'extracting',
  'extracted',
  'failed_extraction',
];

/** Human-readable labels for each UserStoryStatus (i18n keys). */
export const USER_STORY_STATUS_LABELS: Record<UserStoryStatus, string> = {
  pending_extraction: 'stories.status_pending_extraction',
  extracting: 'stories.status_extracting',
  extracted: 'stories.status_extracted',
  failed_extraction: 'stories.status_failed_extraction',
};

/** Valid UserStoryStatus transitions (forward only, terminal states). */
export const VALID_USER_STORY_TRANSITIONS: Record<UserStoryStatus, UserStoryStatus[]> = {
  pending_extraction: ['extracting'],
  extracting: ['extracted', 'failed_extraction'],
  extracted: [],
  failed_extraction: [],
};

/** Check if a UserStoryStatus transition is valid. */
export function isValidUserStoryTransition(
  current: UserStoryStatus,
  next: UserStoryStatus,
): boolean {
  return VALID_USER_STORY_TRANSITIONS[current]?.includes(next) ?? false;
}

export interface UserStory {
  id: string;
  projectId: string;
  actor: string;
  feature: string;
  benefit: string;
  rawText: string;
  status: UserStoryStatus;
  createdAt: string;
  /**
   * One-line version summary for the story card, projected by the story read
   * paths (`list_stories`, `get_story`, `update_story`) in one batched
   * statement — never one request per card.
   *
   * Nested shape (camelCase mirror of the backend `StoryVersionSummaryResponse`):
   * - `count` — how many extraction runs the story has, any status.
   * - `currentNumber` — the highest `completed` run's version number, or
   *   `null` when there is no completed run (the card must then show the
   *   newest run without ever calling it "current").
   * - `latestNumber` / `latestStatus` — the newest run of any status and its
   *   `ExtractionStatus` (`pending` | `completed` | `failed`).
   *
   * `null` (or absent) reliably means **the story has no runs at all** —
   * exactly what `create_story` answers for a story just created. The card
   * renders no version badge and no count in that case; nothing is invented.
   */
  versionSummary?: StoryVersionSummary | null;
}

/* ── Story version summary (versioning-visibility, WU3) ── */

/** Raw `version_summary` from `UserStoryResponse` (snake_case, pre-`toCamelCase`). */
export interface RawStoryVersionSummary {
  /** How many extraction runs the story has, any status. */
  count: number;
  /** Highest `completed` run's version number; `null` when no run completed. */
  current_number: number | null;
  /** The newest run's version number, any status. */
  latest_number: number;
  /** The newest run's status — the backend `ExtractionStatus` enum. */
  latest_status: 'pending' | 'completed' | 'failed';
}

/** camelCase mirror of `RawStoryVersionSummary`, as `UserStory.versionSummary` carries it. */
export interface StoryVersionSummary {
  /** How many extraction runs the story has, any status. */
  count: number;
  /** Highest `completed` run's version number; `null` when no run completed. */
  currentNumber: number | null;
  /** The newest run's version number, any status. */
  latestNumber: number;
  /** The newest run's status — the backend `ExtractionStatus` enum. */
  latestStatus: 'pending' | 'completed' | 'failed';
}

/* ── Extraction versions (0.9.0 slice b) ── */

/** Raw story version from `GET /stories/{id}/versions` (snake_case). */
export interface RawStoryVersion {
  id: string;
  version_number: number | null;
  status: string;
  model_used: string;
  provider: string;
  temperature: number;
  created_at: string;
  completed_at: string | null;
  error_info: string | null;
  is_current: boolean;
  has_output: boolean;
}

/**
 * One version of a story's extraction, as the version selector reads it.
 * Mirrors the backend `StoryVersionResponse`: every run of the story —
 * pending and failed ones included — ordered `version_number DESC` by the
 * route. `is_current` marks the first `completed` entry of the ordered list
 * (a story with no completed run has no current entry) and `has_output` is
 * `status == completed`; both are derived server-side, never stored.
 */
export interface StoryVersion {
  id: string;
  versionNumber: number | null;
  status: string;
  modelUsed: string;
  provider: string;
  temperature: number;
  createdAt: string;
  completedAt: string | null;
  errorInfo: string | null;
  isCurrent: boolean;
  hasOutput: boolean;
}

/* ── CSV import ── */

/** Why a CSV row was skipped as a duplicate during import. */
export type StoryImportDuplicateReason = 'duplicate' | 'duplicate_in_file';

/** A row skipped because it duplicates an existing story or another row in the upload. */
export interface StoryImportDuplicate {
  /** 1-based line number in the uploaded CSV. */
  line: number;
  reason: StoryImportDuplicateReason;
  /** Present when reason is 'duplicate': the story that already exists in the project. */
  existingStoryId?: string;
  /** Present when reason is 'duplicate_in_file': the earlier line it repeats. */
  firstLine?: number;
}

/** A single validation problem with one CSV row (blocking — the whole import is rejected). */
export interface StoryImportIssue {
  /** 1-based line number in the uploaded CSV. */
  line: number;
  reason: string;
  field?: string;
  length?: number;
  max?: number;
  observed?: number;
  expected?: number;
}

/** Successful import summary (201 response). */
export interface StoryImportReport {
  created: number;
  skipped: number;
  totalRows: number;
  duplicates: StoryImportDuplicate[];
  storyIds: string[];
}

/**
 * Typed import failure, extracted from an ApiRequestError.
 * - `rows`: 422 IMPORT_VALIDATION_FAILED — per-row validation issues; nothing was created.
 * - `file`: 422 IMPORT_FILE_REJECTED or 413 IMPORT_FILE_TOO_LARGE — the file itself was rejected.
 */
export type StoryImportFailure =
  | {
      kind: 'rows';
      totalRows: number;
      errors: StoryImportIssue[];
      duplicates: StoryImportDuplicate[];
    }
  | {
      kind: 'file';
      errorCode: 'IMPORT_FILE_REJECTED' | 'IMPORT_FILE_TOO_LARGE';
      reason?: string;
      size?: number;
      max?: number;
    };
