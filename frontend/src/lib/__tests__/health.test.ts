import { describe, it, expect } from 'vitest';
import {
  HEALTH_SERVICES_PATH,
  parseServicesHealth,
  serviceStatus,
  type ServicesHealth,
} from '@/lib/health';

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

  it('returns null for a probe whose status is not ok or error', () => {
    const odd = parseServicesHealth({
      ...SERVICES_HEALTH_200,
      services: { ollama: { status: 'maybe', latency_ms: 1 } },
    }) as ServicesHealth;

    expect(serviceStatus(odd, 'ollama')).toBeNull();
  });
});
