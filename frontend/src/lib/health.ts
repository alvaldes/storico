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
  /**
   * `unknown` is a state the backend publishes, not an absence: the schema probe degrades to it
   * when it cannot read the applied Alembic revision, and its docstring says that `unknown`
   * already is the failure. Only `ok`/`error`/`unknown` are accepted from the wire.
   */
  status: 'ok' | 'error' | 'unknown';
  latency_ms: number | null;
  error?: string;
  model_count?: number;
  /**
   * The probe's classification, published by the backend since commit `b90ded2`:
   * `required` means the deployment is not useful without the probe, `optional` means an
   * integration a workspace may never use. Absent on payloads from a backend that predates
   * the field — the frontend and the backend deploy independently, so the page must still
   * classify correctly without it (see `CORE_PROBES`).
   */
  scope?: 'required' | 'optional';
  /** The embeddings probe: the provider the global embedding setting selected. */
  provider?: string;
  /** The embeddings probe: the model the probe actually used. */
  model?: string;
  /** The embeddings probe: the embedding dimensions the probe measured. */
  dimensions?: number;
  /** The embeddings probe: the vector length configured on the store. */
  vector_length?: number;
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
  if (status !== 'ok' && status !== 'error' && status !== 'unknown') return null;

  return probe as unknown as ServiceStatus;
}

/**
 * The probes whose failure means the deployment is not useful. A local mirror of the
 * backend's `REQUIRED_PROBES` (`backend/src/storico/api/routes/health.py`), which is
 * authoritative: `status-probes-mirror.test.ts` reads the Python source on every run and
 * pins this constant to it, so the two cannot drift silently.
 *
 * The mirror exists for the deploy-skew window: the frontend deploys on Vercel and the
 * backend on the VM, independently, so the page can receive a payload whose probes carry
 * no `scope` yet and must still classify the banner correctly.
 */
export const CORE_PROBES: readonly string[] = ['database', 'schema'];

/**
 * Whether a probe belongs to the core. The wire wins: when the probe carries a published
 * `scope` — one of the two values the backend actually publishes — that is the backend's
 * own answer. When it does not, the local `CORE_PROBES` mirror decides by probe name; a
 * scope value outside the published set falls through to the mirror rather than being
 * trusted.
 */
export function isCoreProbe(name: string, probe: ServiceStatus | null): boolean {
  if (probe?.scope === 'required') return true;
  if (probe?.scope === 'optional') return false;
  return CORE_PROBES.includes(name);
}

export type HealthBanner = 'ok' | 'degraded' | 'down';

export interface HealthSummary {
  banner: HealthBanner;
  /** The non-core probes that are not `ok`, in the order given. */
  degradedOptional: string[];
}

/**
 * The banner rule for the `/status` page, in one tested place.
 *
 * The backend's top-level `status` is its own answer about the required probes, and the
 * page must not re-derive a different one by accident — nor inherit the pre-`b90ded2`
 * contract, where any probe degraded it. Here: `down` when the document did not arrive;
 * `degraded` when any core probe is not `ok` (a core probe missing from the document, or
 * malformed, counts as not ok — never as fine); `ok` otherwise, with the failing optional
 * probes listed so the page can show a caveat instead of a bare green light.
 */
export function summarizeHealth(
  health: ServicesHealth | null,
  names: readonly string[],
): HealthSummary {
  if (!health) return { banner: 'down', degradedOptional: [] };

  const degradedOptional: string[] = [];
  let degraded = false;

  for (const name of names) {
    const probe = serviceStatus(health, name);
    if (!probe || probe.status !== 'ok') {
      if (isCoreProbe(name, probe)) degraded = true;
      else degradedOptional.push(name);
    }
  }

  return { banner: degraded ? 'degraded' : 'ok', degradedOptional };
}
