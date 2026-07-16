const BASE_URL = '';  // Proxy through Astro (same-origin)

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
}

export class ApiRequestError extends Error {
  status: number;
  statusText: string;
  detail: unknown;

  constructor(status: number, statusText: string, detail: unknown) {
    const message = buildErrorMessage(status, statusText, detail);
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
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
      try {
        const errorBody = await response.json();
        detail = errorBody.detail ?? errorBody.message;
      } catch {
        // response body is not JSON
      }

      throw new ApiRequestError(response.status, response.statusText, detail);
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
}

export const api = new ApiClient(BASE_URL);
