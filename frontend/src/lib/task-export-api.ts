import { ApiRequestError } from './api';

/**
 * Client for the workspace's task-file export endpoint
 * (`GET /api/v1/workspaces/{id}/export/tasks`) and the home of the neutral
 * scope resolver the export page's four formats share.
 *
 * The file endpoint serves the same body in two dispositions — the download,
 * with the attachment header, and the preview (`preview=true`), the exact same
 * bytes without it. One URL builder feeds both, so what the preview shows
 * cannot differ from what the download saves: they are the same request.
 *
 * Errors travel as `ApiRequestError` carrying the canonical envelope's
 * `error_code` — the same shape the shared client throws — so `ErrorDisplay`
 * translates the code like every other surface.
 */

/** The four formats the export page offers, in display order. */
export const EXPORT_FORMATS = ['csv', 'json', 'markdown', 'trello'] as const;

export type ExportFormat = (typeof EXPORT_FORMATS)[number];

/** The formats served as a file by `GET …/export/tasks`; `trello` is the fourth disposition. */
export type FileExportFormat = Exclude<ExportFormat, 'trello'>;

export function isFileExportFormat(format: ExportFormat): format is FileExportFormat {
  return format !== 'trello';
}

/**
 * One resolved export target — the wire spellings both export endpoints accept.
 *
 * This is the resolver behind all four formats: the Trello trigger's body and
 * the file export's query are built from the same value, so the two paths
 * cannot disagree about what is selected. Most-specific-wins, the Kanban
 * cascade's rule: a story implies its project, so when both levels are held
 * only the story travels. `extraction_id` names the version and is emitted
 * only beside its story — a version belongs to a story, and the API answers
 * `422` for one asked at project or workspace level, so the resolver makes
 * that impossible by construction rather than by discipline.
 */
export interface ExportScopeTarget {
  project_id?: string;
  user_story_id?: string;
  extraction_id?: string;
}

export function resolveExportTarget(
  projectId: string | null,
  userStoryId: string | null,
  extractionId: string | null = null,
): ExportScopeTarget {
  if (userStoryId) {
    return extractionId
      ? { user_story_id: userStoryId, extraction_id: extractionId }
      : { user_story_id: userStoryId };
  }
  if (projectId) return { project_id: projectId };
  return {};
}

/** The export request URL: the format, the resolved target, and the disposition. */
export function buildTaskExportUrl(
  wsId: string,
  format: FileExportFormat,
  target: ExportScopeTarget,
  preview = false,
): string {
  const baseUrl = import.meta.env.PUBLIC_API_URL || '';
  const params = new URLSearchParams({ format });
  for (const [key, value] of Object.entries(target)) {
    if (value !== undefined) params.set(key, value);
  }
  if (preview) params.set('preview', 'true');
  return `${baseUrl}/api/v1/workspaces/${wsId}/export/tasks?${params.toString()}`;
}

/**
 * The preview read: the exact body the download would save, answered without
 * the attachment header. `preview=true` on the same endpoint — never a second
 * serialization.
 */
export async function getTaskExportPreview(
  wsId: string,
  format: FileExportFormat,
  target: ExportScopeTarget,
): Promise<string> {
  const response = await fetch(buildTaskExportUrl(wsId, format, target, true), {
    credentials: 'include',
  });
  if (!response.ok) throw await exportHttpError(response);
  return response.text();
}

/** The download request: the body as a blob, plus the server's filename when it names one. */
export async function fetchTaskExportBlob(
  wsId: string,
  format: FileExportFormat,
  target: ExportScopeTarget,
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(buildTaskExportUrl(wsId, format, target), {
    credentials: 'include',
  });
  if (!response.ok) throw await exportHttpError(response);
  const disposition = response.headers.get('Content-Disposition');
  const filename = disposition
    ? (disposition.split('filename=')[1]?.replace(/['"]/g, '') ?? null)
    : null;
  return { blob: await response.blob(), filename };
}

/**
 * Raise the export failure as an `ApiRequestError`, the same shape the shared
 * client throws, so the caller renders it through `ErrorDisplay` with the
 * envelope's code translated.
 */
async function exportHttpError(response: Response): Promise<ApiRequestError> {
  let rawBody: unknown;
  let detail: unknown;
  try {
    const text = await response.text();
    try {
      const body = JSON.parse(text) as Record<string, unknown>;
      rawBody = body;
      detail = body.detail ?? body.message ?? body;
    } catch {
      rawBody = text;
      detail = text.length > 0 ? text : `HTTP ${response.status}`;
    }
  } catch {
    detail = `HTTP ${response.status}`;
  }
  return new ApiRequestError(response.status, response.statusText, detail, rawBody);
}
