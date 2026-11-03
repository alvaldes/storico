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
  judge_result: JudgeResult | null;
  created_at: string;
  completed_at: string | null;
  tasks: ExtractionTask[];
}

/** One judged criterion, exactly as the backend persisted it. */
export interface JudgeCriterion {
  score: number;
  justification: string | null;
}

/**
 * The LLM-as-a-Judge record (`extractions.judge_result`), as the extraction
 * read carries it (S5/D4). `null` means the run was never asked to judge — the
 * normal case (D8).
 *
 * Rows written before the 1–7 rubric landed carry the OLD shape: five criteria
 * on 0–10 with the wire name `format` in place of `clarity`, and no `tas`/`ifi`
 * keys. Those rows are never rescaled or completed by the frontend: the panel
 * renders what a record has and omits the thesis indices when the record does
 * not carry them.
 */
export interface JudgeResult {
  state: 'ok' | 'failed';
  criteria: Record<string, JudgeCriterion>;
  total_score: number | null;
  max_total: number | null;
  approved: boolean | null;
  /** Absent on pre-rubric rows. Never recomputed in the frontend (S8). */
  tas?: number;
  ifi?: number;
  model?: string | null;
  model_source?: 'workspace' | 'extraction';
  error: string | null;
  error_type: string | null;
}
