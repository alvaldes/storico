import { describe, it, expect } from 'vitest';
import {
  CORE_PROBES,
  HEALTH_SERVICES_PATH,
  isCoreProbe,
  parseServicesHealth,
  serviceStatus,
  summarizeHealth,
  type ServiceStatus,
  type ServicesHealth,
} from '@/lib/health';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

/**
 * Captured verbatim from the running backend on 2026-09-25:
 *
 *   GET :8000/api/v1/health/services
 *   GET :8000/api/v1/health
 *
 * Both are kept as literal fixtures on purpose. The defect these tests pin down was
 * exactly a consumer reading one document with the other one's shape, so a fixture
 * fabricated from the consumer's own type would reproduce the bug it is meant to catch.
 */
const SERVICES_HEALTH_200 = {
  status: 'ok',
  version: '0.5.1',
  timestamp: '2026-09-25T01:35:48.878532+00:00',
  services: {
    database: { status: 'ok', latency_ms: 795.2 },
    schema: { status: 'ok', latency_ms: 1102.8 },
    ollama: { status: 'ok', latency_ms: 28.4, model_count: 4 },
    qdrant: { status: 'ok', latency_ms: 322.3 },
    embeddings: {
      status: 'ok',
      latency_ms: 562.6,
      provider: 'ollama',
      model: 'nomic-embed-text',
      dimensions: 768,
      vector_length: 768,
    },
  },
};

const LIVENESS_HEALTH_200 = {
  status: 'ok',
  version: '0.5.1',
  timestamp: '2026-09-25T01:42:56.288922+00:00',
  database: { status: 'ok', latency_ms: 793.7 },
  schema: { status: 'ok', latency_ms: 858.3 },
};

/**
 * The same document once the backend publishes each probe's classification (commit
 * `b90ded2`): `scope` rides inside every probe and the top-level `status` reflects the
 * required probes only. Shaped from `backend/src/storico/api/routes/health.py` and kept
 * next to the pre-scope fixture above because the frontend and the backend deploy
 * independently — the page must read both shapes during the skew window.
 */
const SERVICES_HEALTH_200_SCOPED = {
  status: 'ok',
  version: '0.5.1',
  timestamp: '2026-09-25T14:05:11.231900+00:00',
  services: {
    database: { status: 'ok', latency_ms: 795.2, scope: 'required' },
    schema: { status: 'ok', latency_ms: 1102.8, scope: 'required' },
    ollama: { status: 'ok', latency_ms: 28.4, model_count: 4, scope: 'optional' },
    qdrant: { status: 'ok', latency_ms: 322.3, scope: 'optional' },
    embeddings: {
      status: 'ok',
      latency_ms: 562.6,
      provider: 'google',
      model: 'text-embedding-004',
      dimensions: 768,
      vector_length: 768,
      scope: 'optional',
    },
  },
};

/** The document with one probe's status (or whole shape) replaced. */
const withProbes = (health: typeof SERVICES_HEALTH_200, probes: Record<string, unknown>) => ({
  ...health,
  services: { ...health.services, ...probes },
});

describe('HEALTH_SERVICES_PATH', () => {
  it('points at the route that carries per-service probes', () => {
    expect(HEALTH_SERVICES_PATH).toBe('/api/v1/health/services');
  });

  it('is not the liveness route, which has no services key', () => {
    expect(HEALTH_SERVICES_PATH).not.toBe('/api/v1/health');
  });
});

describe('parseServicesHealth', () => {
  it('reads the services payload', () => {
    const health = parseServicesHealth(SERVICES_HEALTH_200);

    expect(health).not.toBeNull();
    expect(health?.status).toBe('ok');
    expect(health?.timestamp).toBe('2026-09-25T01:35:48.878532+00:00');
    expect(health?.services.database.status).toBe('ok');
    expect(health?.services.ollama.model_count).toBe(4);
  });

  it('rejects the liveness payload instead of handing back undefined services', () => {
    // The regression: status.astro fetched /api/v1/health and read
    // health.services.ollama. `services` is absent there, so the page threw
    // "Cannot read properties of undefined (reading 'ollama')" while rendering.
    expect(parseServicesHealth(LIVENESS_HEALTH_200)).toBeNull();
  });

  it('rejects anything that is not a services document', () => {
    expect(parseServicesHealth(null)).toBeNull();
    expect(parseServicesHealth(undefined)).toBeNull();
    expect(parseServicesHealth('<!doctype html><title>error</title>')).toBeNull();
    expect(parseServicesHealth(503)).toBeNull();
    expect(parseServicesHealth([])).toBeNull();
    expect(parseServicesHealth({ services: null })).toBeNull();
    expect(parseServicesHealth({ services: [] })).toBeNull();
  });

  it('rejects a document whose status or timestamp the banner would have to invent', () => {
    expect(parseServicesHealth({ ...SERVICES_HEALTH_200, status: 'unknown' })).toBeNull();
    expect(parseServicesHealth({ ...SERVICES_HEALTH_200, timestamp: 42 })).toBeNull();
  });

  it('keeps a degraded document', () => {
    const degraded = {
      ...SERVICES_HEALTH_200,
      status: 'degraded',
      services: { ...SERVICES_HEALTH_200.services, qdrant: { status: 'error', latency_ms: 3000 } },
    };

    const health = parseServicesHealth(degraded);

    expect(health?.status).toBe('degraded');
    expect(health?.services.qdrant.status).toBe('error');
  });

  it('survives a version the backend could not read', () => {
    expect(parseServicesHealth({ ...SERVICES_HEALTH_200, version: null })?.version).toBe('unknown');
  });
});

describe('probe scope', () => {
  it('reads the scope the backend publishes off a probe', () => {
    const health = parseServicesHealth(SERVICES_HEALTH_200_SCOPED) as ServicesHealth;

    expect(serviceStatus(health, 'database')?.scope).toBe('required');
    expect(serviceStatus(health, 'ollama')?.scope).toBe('optional');
  });

  it('treats the absence of scope as valid, not as an error', () => {
    // The frontend deploys on Vercel and the backend on the VM, independently: during the
    // skew window the page reads the pre-`scope` payload and must not reject it.
    const health = parseServicesHealth(SERVICES_HEALTH_200) as ServicesHealth;

    expect(serviceStatus(health, 'database')?.scope).toBeUndefined();
  });
});

describe('isCoreProbe', () => {
  it('prefers the wire scope over the local mirror', () => {
    // A probe named like a core probe but published optional is optional — the backend's
    // own classification is the answer, and the name is only a fallback.
    expect(isCoreProbe('database', { status: 'ok', latency_ms: 1, scope: 'optional' })).toBe(false);
    expect(isCoreProbe('ollama', { status: 'ok', latency_ms: 1, scope: 'required' })).toBe(true);
  });

  it('falls back to CORE_PROBES when the payload carries no scope', () => {
    expect(isCoreProbe('database', { status: 'ok', latency_ms: 1 })).toBe(true);
    expect(isCoreProbe('ollama', { status: 'ok', latency_ms: 1 })).toBe(false);
  });

  it('falls back for a probe the document does not carry', () => {
    expect(isCoreProbe('database', null)).toBe(true);
    expect(isCoreProbe('ollama', null)).toBe(false);
  });

  it('ignores a scope value the backend never publishes', () => {
    // Only "required" and "optional" are published values; anything else (a typo, a future
    // third class) must fall through to the mirror instead of being trusted.
    const oddScope = { status: 'ok', latency_ms: 1, scope: 'needed' } as unknown as ServiceStatus;
    expect(isCoreProbe('ollama', oddScope)).toBe(false);
    expect(isCoreProbe('database', oddScope)).toBe(true);
  });
});

describe('summarizeHealth', () => {
  // The probe names the status page evaluates: the five the backend publishes.
  const PROBES = ['database', 'schema', 'ollama', 'qdrant', 'embeddings'];

  it('answers down when the document did not arrive', () => {
    expect(summarizeHealth(null, PROBES)).toEqual({ banner: 'down', degradedOptional: [] });
  });

  it('answers ok with the failing optionals listed when every core probe is ok', () => {
    // The production case: no Ollama on purpose, everything else healthy. The banner must
    // stay green — one optional integration is not the platform being down.
    const degraded = parseServicesHealth(
      withProbes(SERVICES_HEALTH_200_SCOPED, {
        ollama: { status: 'error', latency_ms: 3000, error: 'connection refused', scope: 'optional' },
        qdrant: { status: 'error', latency_ms: 3000, error: 'connection refused', scope: 'optional' },
        embeddings: {
          status: 'error',
          latency_ms: 3000,
          error: 'connection refused',
          scope: 'optional',
        },
      }),
    ) as ServicesHealth;

    expect(summarizeHealth(degraded, PROBES)).toEqual({
      banner: 'ok',
      degradedOptional: ['ollama', 'qdrant', 'embeddings'],
    });
  });

  it('answers degraded when a core probe fails', () => {
    const degraded = parseServicesHealth(
      withProbes(SERVICES_HEALTH_200_SCOPED, {
        database: { status: 'error', latency_ms: 3000, error: 'timeout', scope: 'required' },
      }),
    ) as ServicesHealth;

    expect(summarizeHealth(degraded, PROBES)).toEqual({
      banner: 'degraded',
      degradedOptional: [],
    });
  });

  it('answers degraded when a core probe is absent from the document', () => {
    // A core probe missing counts as not ok, never as fine: the page must not paint the
    // banner green over an absence. The optional probes absent alongside it are listed too —
    // an absent probe is not a measurement of "ok" either.
    const partial = parseServicesHealth({
      ...SERVICES_HEALTH_200_SCOPED,
      services: { database: { status: 'ok', latency_ms: 1, scope: 'required' } },
    }) as ServicesHealth;

    expect(summarizeHealth(partial, PROBES)).toEqual({
      banner: 'degraded',
      degradedOptional: ['ollama', 'qdrant', 'embeddings'],
    });
  });

  it('answers degraded when a malformed core probe is not a measurement', () => {
    const malformed = parseServicesHealth(
      withProbes(SERVICES_HEALTH_200_SCOPED, {
        schema: 'ok',
      }),
    ) as ServicesHealth;

    expect(summarizeHealth(malformed, PROBES)?.banner).toBe('degraded');
  });

  it('answers ok on the deploy-skew payload: no scope anywhere, ollama error', () => {
    // The old backend plus the new page: the payload carries no `scope`, so the banner rule
    // must fall back to the local mirror of the core set — and must not reproduce the defect
    // where one unreachable Ollama painted the whole platform degraded.
    const skew = parseServicesHealth(
      withProbes(SERVICES_HEALTH_200, {
        ollama: { status: 'error', latency_ms: 3000, error: 'connection refused' },
      }),
    ) as ServicesHealth;

    expect(summarizeHealth(skew, PROBES)).toEqual({
      banner: 'ok',
      degradedOptional: ['ollama'],
    });
  });

  it('lists the failing optionals in the order the page renders them', () => {
    const degraded = parseServicesHealth(
      withProbes(SERVICES_HEALTH_200_SCOPED, {
        embeddings: { status: 'error', latency_ms: 3000, error: 'timeout', scope: 'optional' },
        ollama: { status: 'error', latency_ms: 3000, error: 'refused', scope: 'optional' },
      }),
    ) as ServicesHealth;

    expect(summarizeHealth(degraded, PROBES)?.degradedOptional).toEqual(['ollama', 'embeddings']);
  });
});

describe('CORE_PROBES', () => {
  it('holds the probes whose failure means the deployment is not useful', () => {
    // Decision D3: the database is the required dependency, and a schema behind the code
    // is a dependency of being useful (the 2026-09-20 incident). Everything else is an
    // optional integration. The backend is authoritative; the mirror test pins this
    // constant to REQUIRED_PROBES by reading the Python source.
    expect(CORE_PROBES).toEqual(['database', 'schema']);
  });
});

describe('the optional-integrations note', () => {
  it('carries the {list} token in both catalogs', () => {
    // The page interpolates the unavailable optional integrations into this sentence; a
    // locale without the token would render the placeholder literally.
    expect(en.pages.status.optional_unavailable_note).toContain('{list}');
    expect(es.pages.status.optional_unavailable_note).toContain('{list}');
  });
});

describe('serviceStatus', () => {
  it('returns the probe of a service the backend reported', () => {
    const health = parseServicesHealth(SERVICES_HEALTH_200) as ServicesHealth;

    expect(serviceStatus(health, 'ollama')?.status).toBe('ok');
    expect(serviceStatus(health, 'qdrant')?.latency_ms).toBe(322.3);
  });

  it('returns null for a probe the backend did not send', () => {
    // A status page must degrade to "Unavailable" for one row instead of throwing
    // for the whole document: a missing probe is precisely when the page matters.
    const partial = parseServicesHealth({
      ...SERVICES_HEALTH_200,
      services: { database: { status: 'ok', latency_ms: 1 } },
    }) as ServicesHealth;

    expect(serviceStatus(partial, 'ollama')).toBeNull();
    expect(serviceStatus(partial, 'qdrant')).toBeNull();
  });

  it('returns null for a malformed probe and for a missing document', () => {
    const malformed = parseServicesHealth({
      ...SERVICES_HEALTH_200,
      services: { ollama: 'ok' },
    }) as ServicesHealth;

    expect(serviceStatus(malformed, 'ollama')).toBeNull();
    expect(serviceStatus(parseServicesHealth(LIVENESS_HEALTH_200), 'database')).toBeNull();
  });

  it('returns null for a probe whose status is not one of the published states', () => {
    const odd = parseServicesHealth({
      ...SERVICES_HEALTH_200,
      services: { ollama: { status: 'maybe', latency_ms: 1 } },
    }) as ServicesHealth;

    expect(serviceStatus(odd, 'ollama')).toBeNull();
  });

  it('reads the schema probe out of the diagnostics document', () => {
    const health = parseServicesHealth(SERVICES_HEALTH_200) as ServicesHealth;

    expect(serviceStatus(health, 'schema')?.status).toBe('ok');
  });

  it('keeps an unknown status, which is a measurement rather than a missing probe', () => {
    // The schema probe degrades to `unknown` when it cannot read the applied revision, and its
    // docstring says "`unknown` already is the failure" — the code/Alembic-head mismatch that
    // cost 56 extractions on 2026-09-20 is exactly what it reports that way. Returning null here
    // would render it as "Unavailable" and claim a probe nobody ran.
    const mismatched = parseServicesHealth({
      ...SERVICES_HEALTH_200,
      status: 'degraded',
      services: {
        ...SERVICES_HEALTH_200.services,
        schema: { status: 'unknown', latency_ms: 858.3 },
      },
    }) as ServicesHealth;

    expect(serviceStatus(mismatched, 'schema')?.status).toBe('unknown');
  });
});
