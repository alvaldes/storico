import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { ExportScopeTarget } from './task-export-api';

/**
 * Client for the five Trello export endpoints the backend serves:
 *
 * - `GET/PUT /api/v1/workspaces/{id}/settings/trello` — the credential pair, admin-only.
 * - `GET /api/v1/workspaces/{id}/settings/trello/status` — member-readable, field names only.
 * - `POST /api/v1/workspaces/{id}/export/trello` — 202 + the job, open to any member (D7).
 * - `GET /api/v1/workspaces/{id}/export/trello/{export_id}` — the polled job state.
 * - `GET /api/v1/workspaces/{id}/export/trello/preview` — the board plan as JSON, no job created.
 *
 * The export scope is not resolved here: every body and query is built from
 * `resolveExportTarget` (`lib/task-export-api.ts`), the one resolver all four
 * export formats share, so the Trello path can never disagree with the file
 * path about what is selected.
 *
 * Errors travel through the shared `api` client, which raises `ApiRequestError`
 * carrying the canonical envelope's `error_code` — the caller renders it through
 * `ErrorDisplay`/`errorCodeHeadline` like every other surface.
 */

/** The two credential field codes the status endpoint reports, in wire order. */
export const TRELLO_STATUS_FIELDS = ['api_key', 'token'] as const;

export type TrelloStatusField = (typeof TRELLO_STATUS_FIELDS)[number];

/**
 * Whether the workspace has the credential pair, and which fields it lacks.
 *
 * `missing` carries the API's field codes (`api_key`, `token`), never a value:
 * the route is member-readable precisely because it names what has to be defined
 * without handing over the credential.
 */
export interface TrelloConfigStatus {
  configured: boolean;
  missing: TrelloStatusField[];
}

/** The decrypted credential pair, as the admin GET/PUT answer carries it. */
export interface TrelloCredentials {
  apiKey: string | null;
  token: string | null;
}

/**
 * The pair being written. A field left `undefined` means "keep the stored one" —
 * the backend merges; a field it does not return can never be echoed back into
 * the form from here.
 */
export interface TrelloCredentialsInput {
  apiKey?: string | null;
  token?: string | null;
}

export type TrelloExportJobStatus = 'pending' | 'running' | 'completed' | 'failed';

/** The states a poll can stop at: everything else means "keep polling" (D5). */
const TERMINAL_STATUSES: readonly TrelloExportJobStatus[] = ['completed', 'failed'];

export function isTerminalTrelloExportStatus(status: string): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status);
}

/** One persisted export job — everything a polling client needs. */
export interface TrelloExportJob {
  id: string;
  workspaceId: string;
  scope: string;
  projectId: string | null;
  userStoryId: string | null;
  /** The version the job exported, named by its extraction id; null for current versions. */
  extractionId: string | null;
  status: TrelloExportJobStatus;
  /** Set only on failure, with a value from the backend's error-code registry. */
  errorCode: string | null;
  boardId: string | null;
  /** The board link the moment the board exists — including on a failed job. */
  boardUrl: string | null;
  cardsCreated: number | null;
  createdAt: string;
  completedAt: string | null;
}

interface TrelloExportJobRaw {
  id: string;
  workspace_id: string;
  scope: string;
  project_id: string | null;
  user_story_id: string | null;
  extraction_id: string | null;
  status: string;
  error_code: string | null;
  board_id: string | null;
  board_url: string | null;
  cards_created: number | null;
  created_at: string;
  completed_at: string | null;
}

function mapJob(raw: TrelloExportJobRaw): TrelloExportJob {
  const job = toCamelCase<TrelloExportJob>(raw);
  return { ...job, status: job.status as TrelloExportJobStatus };
}

/** Get the workspace Trello credentials, decrypted. Admin only. */
export async function getTrelloConfig(wsId: string): Promise<TrelloCredentials> {
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/workspaces/${wsId}/settings/trello`,
  );
  return toCamelCase<TrelloCredentials>(raw);
}

/** Upsert the workspace Trello credentials. Admin only. */
export async function upsertTrelloConfig(
  wsId: string,
  credentials: TrelloCredentialsInput,
): Promise<TrelloCredentials> {
  const raw = await api.put<Record<string, unknown>>(
    `/api/v1/workspaces/${wsId}/settings/trello`,
    toSnakeCase(credentials),
  );
  return toCamelCase<TrelloCredentials>(raw);
}

/**
 * Ask whether this workspace can export to Trello.
 *
 * Readable by any member, unlike the credentials themselves. The member who
 * cannot read the pair is exactly the one who meets the refused export, so this
 * is how the workspace is checked before the export is attempted instead of
 * after it answers `409`.
 *
 * Only the field codes this client knows are kept, as the LLM status client does.
 */
export async function getTrelloConfigStatus(wsId: string): Promise<TrelloConfigStatus> {
  const raw = await api.get<{ configured: boolean; missing: string[] }>(
    `/api/v1/workspaces/${wsId}/settings/trello/status`,
  );
  return {
    configured: raw.configured,
    missing: raw.missing.filter((field): field is TrelloStatusField =>
      (TRELLO_STATUS_FIELDS as readonly string[]).includes(field),
    ),
  };
}

/**
 * Trigger a Trello export. Any member (D7); answers `202` with the job.
 *
 * `scope` must come from `resolveExportTarget` — the resolver all four export
 * formats share, so a body carries exactly one target and a version only
 * beside its story; the API refuses anything else with `422`.
 */
export async function triggerTrelloExport(
  wsId: string,
  scope: ExportScopeTarget = {},
): Promise<TrelloExportJob> {
  const raw = await api.post<TrelloExportJobRaw>(
    `/api/v1/workspaces/${wsId}/export/trello`,
    scope,
  );
  return mapJob(raw);
}

/** Read one export job's current state. Any member; the poll's endpoint (D5). */
export async function getTrelloExport(wsId: string, exportId: string): Promise<TrelloExportJob> {
  const raw = await api.get<TrelloExportJobRaw>(
    `/api/v1/workspaces/${wsId}/export/trello/${exportId}`,
  );
  return mapJob(raw);
}

/** One card of the preview's plan — everything resolved already. */
export interface TrelloBoardPlanCard {
  title: string;
  description: string;
  labels: string[];
  /** Already-resolved dependency titles, the same values the adapter sends. */
  dependencyTitles: string[];
}

/** One board list of the preview's plan, with its cards in order. */
export interface TrelloBoardPlanColumn {
  name: string;
  cards: TrelloBoardPlanCard[];
}

/** The board plan the trigger would send — the preview's shape (E4). */
export interface TrelloBoardPlan {
  name: string;
  columns: TrelloBoardPlanColumn[];
}

/**
 * The board plan as JSON, without creating a job (E4's preview).
 *
 * The same `TrelloBoardPlan` the runner builds, serialized by the backend —
 * an export that only describes itself must not cost a board, and what the
 * preview shows is what the trigger would create.
 */
export async function previewTrelloExport(
  wsId: string,
  scope: ExportScopeTarget = {},
): Promise<TrelloBoardPlan> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(scope)) {
    if (value !== undefined) params.set(key, value);
  }
  const query = params.toString();
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/workspaces/${wsId}/export/trello/preview${query ? `?${query}` : ''}`,
  );
  return toCamelCase<TrelloBoardPlan>(raw);
}
