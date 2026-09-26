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
