/**
 * The two health documents the backend publishes, and why this module exists.
 *
 * `GET /api/v1/health` is liveness: `database` and `schema` at the TOP LEVEL, no
 * `services` key. `GET /api/v1/health/services` is the diagnostics document:
 * `services: { database, schema, ollama, qdrant, embeddings }`.
 *
 * `/status` was written against the services shape while fetching the liveness route,
 * so `health.services.ollama` was a property read on `undefined`. Because Astro SSRs by
 * streaming, that throw aborted the response after the layout: the page rendered its
 * navbar, nothing else, and no error. It shipped on 2026-09-20 and was found on
 * 2026-09-25 by loading the page in a browser.
 *
 * The lesson is that a consumer must not assume a document it did not verify, so the
 * payload is parsed here — in one tested place — instead of being read directly from
 * `.astro` markup, where nothing could reach it.
 */

/** One probe result, shaped like every `_check_*` in the backend's health route. */
export interface ServiceStatus {
  status: 'ok' | 'error';
  latency_ms: number | null;
  error?: string;
  model_count?: number;
}

export interface ServicesHealth {
  status: 'ok' | 'degraded';
  version: string;
  timestamp: string;
  services: Record<string, ServiceStatus>;
}

/**
 * The diagnostics route. Named as a constant so the `/status` page fetches the document
 * its markup actually reads, and so a test can assert which of the two routes it is.
 */
export const HEALTH_SERVICES_PATH = '/api/v1/health/services';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Read a health payload as a services document, or `null` when it is not one.
 *
 * `status` and `timestamp` are required: the banner and the "last updated" line read
 * them, and a document missing either would force those two to be invented. `version` is
 * optional because the backend degrades it to `"unknown"` when it cannot read the
 * installed distribution.
 *
 * `null` is the honest answer for the liveness payload — it is not a services document,
 * and no amount of its `database` key makes it one.
 */
export function parseServicesHealth(payload: unknown): ServicesHealth | null {
  if (!isRecord(payload)) return null;
  if (!isRecord(payload.services)) return null;
  if (payload.status !== 'ok' && payload.status !== 'degraded') return null;
  if (typeof payload.timestamp !== 'string') return null;

  return {
    status: payload.status,
    version: typeof payload.version === 'string' ? payload.version : 'unknown',
    timestamp: payload.timestamp,
    services: payload.services as Record<string, ServiceStatus>,
  };
}

/**
 * The probe for one service, or `null` when the document does not carry one.
 *
 * `null` is deliberately not collapsed into a synthetic `error`: an absent probe means
 * "not reported", while `error` means "probed and unreachable". The page renders the
 * first as "Unavailable" and the second as "Error", and conflating them would put a
 * diagnosis in the operator's hands that nobody measured.
 */
export function serviceStatus(health: ServicesHealth | null, name: string): ServiceStatus | null {
  const probe = health?.services?.[name];
  if (!isRecord(probe)) return null;

  const status = probe.status;
  if (status !== 'ok' && status !== 'error') return null;

  return probe as unknown as ServiceStatus;
}
