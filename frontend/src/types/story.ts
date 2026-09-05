/** User story extraction lifecycle status — matches backend UserStoryStatus enum. */
export type UserStoryStatus = 'pending_extraction' | 'extracting' | 'extracted' | 'failed_extraction';

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
  next: UserStoryStatus
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