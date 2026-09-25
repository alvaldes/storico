// @vitest-environment node
//
// These guards read Python and Astro sources from disk, so they need a real filesystem
// path: jsdom hands out `http://localhost/...` URLs for `import.meta.url`, and
// `readFileSync` refuses those. The node environment keeps this file out of the jsdom
// suite instead of making the paths depend on the working directory.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

import en from '@/i18n/en.json';
import es from '@/i18n/es.json';
import { CORE_PROBES } from '@/lib/health';

/**
 * The status page must render one row per probe the backend publishes in
 * `GET /api/v1/health/services`, no fewer and no more.
 *
 * The backend is authoritative — `api/routes/health.py` decides which probes exist —
 * and the frontend cannot import it. A drift is not cosmetic here: the status page
 * derives its banner from a local mirror of the backend's required set (`CORE_PROBES` in
 * `@/lib/health`), because the two deploy independently (Vercel vs the VM) and the page
 * must classify correctly even on a payload whose probes carry no `scope` yet. A probe
 * without a row, or a mirror that drifts from `REQUIRED_PROBES`, would again let one
 * optional integration paint the banner a color the operator cannot trace to a row.
 *
 * The probe list is extracted from the backend on every run instead of being copied:
 * a hardcoded list cannot catch the next probe the backend grows.
 *
 * Each case asserts its extraction first: if something is renamed, the failure lands
 * there, on the missing match, instead of turning the comparison into a mystery
 * `undefined`.
 */
describe('the status page mirrors the backend probes', () => {
  const healthSource = readFileSync(
    new URL('../../../../backend/src/storico/api/routes/health.py', import.meta.url),
    'utf8',
  );
  const statusPageSource = readFileSync(
    new URL('../../../../frontend/src/pages/[locale]/status.astro', import.meta.url),
    'utf8',
  );

  /** Probes the backend publishes inside the `services` object of `health_services`. */
  const backendProbes = (() => {
    const services = healthSource.match(/"services": \{([^}]*)\}/)?.[1];
    expect(services, 'the backend declares a "services" object in health_services').toBeDefined();

    const probes = [...services!.matchAll(/"([^"]+)":/g)].map(([, probe]) => probe);
    expect(probes, 'the backend declares at least one probe in "services"').not.toHaveLength(0);
    return probes;
  })();

  /** Probes the page reads through `serviceStatus(health, '...')` calls. */
  const pageProbes = [...statusPageSource.matchAll(/serviceStatus\(health, '([^']+)'\)/g)].map(
    ([, probe]) => probe,
  );
  expect(pageProbes, 'the status page declares at least one serviceStatus call').not.toHaveLength(
    0,
  );

  /**
   * The probes the backend classifies as required, extracted from `REQUIRED_PROBES` the
   * same way the probe list above is extracted: a rename must fail here, on the missing
   * match, instead of on a mystery comparison against `undefined`.
   */
  const backendRequiredProbes = (() => {
    const tuple = healthSource.match(/^REQUIRED_PROBES = \(([^)]*)\)/m)?.[1];
    expect(tuple, 'the backend declares REQUIRED_PROBES in health.py').toBeDefined();

    const probes = [...tuple!.matchAll(/"([^"]+)"/g)].map(([, probe]) => probe);
    expect(probes, 'REQUIRED_PROBES declares at least one probe').not.toHaveLength(0);
    return probes;
  })();

  /**
   * The probe names the page feeds into the banner rule (`summarizeHealth`). Extracted the
   * same way as the reads above: a rename must fail here, on the missing match.
   */
  const pageDiagnosticProbes = (() => {
    const literal = statusPageSource.match(/const DIAGNOSTIC_PROBES = \[([^\]]*)\]/)?.[1];
    expect(literal, 'the status page declares DIAGNOSTIC_PROBES').toBeDefined();

    const probes = [...literal!.matchAll(/'([^']+)'/g)].map(([, probe]) => probe);
    expect(probes, 'DIAGNOSTIC_PROBES declares at least one probe').not.toHaveLength(0);
    return probes;
  })();

  it('renders a row for every probe the backend publishes', () => {
    for (const probe of backendProbes) {
      expect(
        pageProbes,
        `the status page must read the "${probe}" probe the backend publishes`,
      ).toContain(probe);
    }
  });

  it('renders no row for a probe the backend does not publish', () => {
    for (const probe of pageProbes) {
      expect(
        backendProbes,
        `the status page reads "${probe}", which the backend does not publish`,
      ).toContain(probe);
    }
  });

  it('pins CORE_PROBES to the backend REQUIRED_PROBES', () => {
    // The frontend falls back to this constant exactly when the payload carries no `scope`,
    // so the fallback is only honest while the mirror matches the backend's classification.
    expect([...CORE_PROBES]).toEqual(backendRequiredProbes);
  });

  it('feeds exactly the backend probes into the banner rule', () => {
    // The mirror image of the defect this feature removes: a probe missing from
    // DIAGNOSTIC_PROBES keeps every row invariant passing while `summarizeHealth` never
    // evaluates it — a new required probe would leave the banner green over a failing core,
    // and a new optional probe would never reach the amber note. Green with a hidden failure.
    expect(pageDiagnosticProbes).toEqual(backendProbes);
  });

  it('has copy for every row in both locales', () => {
    const rows = statusPageSource.match(
      /const serviceRows: [\s\S]*?= \[([\s\S]*?)\n\];/,
    )?.[1];
    expect(rows, 'the status page declares the serviceRows array').toBeDefined();

    const keys = [...rows!.matchAll(/t\.pages\.status\.([A-Za-z0-9_]+)/g)].map(([, key]) => key);
    expect(keys, 'the serviceRows array references status copy').not.toHaveLength(0);

    for (const key of keys) {
      expect(
        en.pages.status[key as keyof typeof en.pages.status],
        `en.pages.status.${key} exists and is non-empty`,
      ).toBeTruthy();
      expect(
        es.pages.status[key as keyof typeof es.pages.status],
        `es.pages.status.${key} exists and is non-empty`,
      ).toBeTruthy();
    }
  });
});
