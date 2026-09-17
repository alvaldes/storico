/** Extraction job status — for polling compatibility. */
export type ExtractionStatus = 'pending' | 'completed' | 'failed';

export type UserStoryStatus =
  'pending_extraction' | 'extracting' | 'extracted' | 'failed_extraction';

export type TaskStatus = 'backlog' | 'todo' | 'in_progress' | 'review' | 'done';

/** Single task in extraction response. */
export interface ExtractionTask {
  id: string;
  summary: string;
  description: string;
  status: TaskStatus;
  order_index: number;
}

/** Full extraction response from GET /extractions/{id}. */
export interface ExtractionResponse {
  id: string;
  user_story_id: string;
  model_used: string;
  status: ExtractionStatus;
  user_story_status: UserStoryStatus;
  error_info: string | null;
  prompt_config: Record<string, unknown> | null;
  raw_response: string;
  confidence_score: number | null;
  created_at: string;
  completed_at: string | null;
  tasks: ExtractionTask[];
}
