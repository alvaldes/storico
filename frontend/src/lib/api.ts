import type { Task, TaskStatus } from '@/types/task';
import type { UserStory, UserStoryStatus } from '@/types/story';
import type { ExtractionResponse, ExtractResponse, ExtractRequest, ExtractionTask, ExtractionUserStory } from '@/types/extraction';

const BASE_URL = '';  // Proxy through Astro (same-origin)

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
  error_code?: string;
  current_state?: string;
  attempted_state?: string;
  allowed_transitions?: string[];
}

/** Complete raw backend error response for debugging/display */
export interface RawBackendError {
  /** HTTP status code */
  status: number;
  /** HTTP status text */
  statusText: string;
  /** Raw response body as parsed JSON (or text if not JSON) */
  rawBody: unknown;
  /** Extracted detail field (backward compatible) */
  detail: unknown;
  /** Structured error fields if present */
  errorCode?: string;
  currentState?: string;
  attemptedState?: string;
  allowedTransitions?: string[];
}

export class ApiRequestError extends Error {
  status: number;
  statusText: string;
  /** Raw backend error response - use this for displaying full details */
  rawError: RawBackendError;
  /** Backward compatible: extracted detail field */
  detail: unknown;
  errorCode?: string;
  currentState?: string;
  attemptedState?: string;
  allowedTransitions?: string[];

  constructor(status: number, statusText: string, detail: unknown, rawBody: unknown) {
    const message = buildErrorMessage(status, statusText, detail);
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
    this.rawError = {
      status,
      statusText,
      rawBody,
      detail,
    };

    // Extract structured error fields for INVALID_STATE_TRANSITION
    if (typeof detail === 'object' && detail !== null) {
      const d = detail as Record<string, unknown>;
      this.errorCode = d.error_code as string | undefined;
      this.currentState = d.current_state as string | undefined;
      this.attemptedState = d.attempted_state as string | undefined;
      this.allowedTransitions = d.allowed_transitions as string[] | undefined;
      this.rawError.errorCode = this.errorCode;
      this.rawError.currentState = this.currentState;
      this.rawError.attemptedState = this.attemptedState;
      this.rawError.allowedTransitions = this.allowedTransitions;
    }
  }

  /** Check if this is an INVALID_STATE_TRANSITION error. */
  isInvalidStateTransition(): boolean {
    return this.errorCode === 'INVALID_STATE_TRANSITION';
  }

  /** Get allowed transitions from the error (if available). */
  getAllowedTransitions(): TaskStatus[] {
    return (this.allowedTransitions as TaskStatus[]) ?? [];
  }

  /** Get error info formatted for ErrorDisplay component */
  toErrorInfo(): {
    friendlyMessage: string;
    rawDetail: unknown;
    status: number;
    errorCode?: string;
  } {
    return {
      friendlyMessage: this.message,
      rawDetail: this.rawError.rawBody,
      status: this.status,
      errorCode: this.errorCode,
    };
  }
}

function buildErrorMessage(status: number, statusText: string, detail: unknown): string {
  if (typeof detail === 'string' && detail.length > 0) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first.msg === 'string') {
      return first.msg;
    }
    const json = JSON.stringify(detail);
    return json.length > 200 ? json.slice(0, 200) + '...' : json;
  }
  if (statusText && statusText.length > 0) {
    return statusText;
  }
  return `HTTP ${status}`;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {};

    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      let detail: unknown;
      let rawBody: unknown;
      try {
        const errorBody = await response.json();
        rawBody = errorBody;
        detail = errorBody.detail ?? errorBody.message ?? errorBody;
      } catch {
        // response body is not JSON - try to get as text
        try {
          const text = await response.text();
          rawBody = text;
          detail = text;
        } catch {
          rawBody = null;
        }
      }

      throw new ApiRequestError(response.status, response.statusText, detail, rawBody);
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>('GET', path);
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('POST', path, body);
  }

  async put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('PUT', path, body);
  }

  async delete<T>(path: string): Promise<T> {
    return this.request<T>('DELETE', path);
  }

  async patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('PATCH', path, body);
  }

  // ── Task-specific methods ──

  async listTasksByWorkspace(workspaceId: string): Promise<Task[]> {
    const resp = await this.get<{ items: TaskResponseRaw[] }>(
      `/api/v1/tasks/?workspace_id=${workspaceId}`,
    );
    return resp.items.map(mapTaskResponse);
  }

  async updateTaskStatus(taskId: string, status: TaskStatus): Promise<void> {
    await this.put(`/api/v1/tasks/${taskId}`, { status });
  }

  async updateTask(taskId: string, fields: Partial<Task>): Promise<void> {
    await this.put(`/api/v1/tasks/${taskId}`, fields);
  }

  // ── Story methods ──

  async listStories(params: { project_id?: string; workspace_id?: string; page?: number; size?: number }): Promise<{ items: StoryResponseRaw[]; total: number; page: number; size: number }> {
    const query = new URLSearchParams();
    if (params.project_id) query.set('project_id', params.project_id);
    if (params.workspace_id) query.set('workspace_id', params.workspace_id);
    if (params.page) query.set('page', String(params.page));
    if (params.size) query.set('size', String(params.size));
    return this.get(`/api/v1/stories/?${query.toString()}`);
  }

  async getStory(id: string): Promise<UserStory> {
    const raw = await this.get<StoryResponseRaw>(`/api/v1/stories/${id}`);
    return mapStoryResponse(raw);
  }

  async createStory(data: { project_id: string; actor: string; feature: string; benefit: string; raw_text: string }): Promise<UserStory> {
    const raw = await this.post<StoryResponseRaw>('/api/v1/stories/', data);
    return mapStoryResponse(raw);
  }

  async updateStory(id: string, data: Partial<{ actor: string; feature: string; benefit: string; raw_text: string }>): Promise<UserStory> {
    const raw = await this.put<StoryResponseRaw>(`/api/v1/stories/${id}`, data);
    return mapStoryResponse(raw);
  }

  async deleteStory(id: string): Promise<void> {
    await this.delete(`/api/v1/stories/${id}`);
  }

  // ── Extraction methods ──

  async startExtraction(data: ExtractRequest): Promise<ExtractResponse> {
    return this.post(`/api/v1/workspaces/${data.user_story_id}/extract/`, data);
  }

  async getExtractionStatus(extractionId: string): Promise<ExtractionResponse> {
    return this.get(`/api/v1/extractions/${extractionId}`);
  }
}

// ── Type mapping helpers ──

interface TaskResponseRaw {
  id: string;
  user_story_id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  labels: string[];
  dependencies: string[];
  created_at: string;
  updated_at: string;
}

function mapTaskResponse(raw: TaskResponseRaw): Task {
  return {
    id: raw.id,
    storyId: raw.user_story_id,
    title: raw.title,
    description: raw.description,
    labels: raw.labels,
    dependencies: raw.dependencies,
    status: raw.status as TaskStatus,
    priority: raw.priority,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

interface StoryResponseRaw {
  id: string;
  project_id: string;
  actor: string;
  feature: string;
  benefit: string;
  raw_text: string;
  created_at: string;
  status: string;
}

function mapStoryResponse(raw: StoryResponseRaw): UserStory {
  return {
    id: raw.id,
    projectId: raw.project_id,
    actor: raw.actor,
    feature: raw.feature,
    benefit: raw.benefit,
    rawText: raw.raw_text,
    createdAt: raw.created_at,
    status: raw.status as UserStoryStatus,
  };
}

export const api = new ApiClient(BASE_URL);