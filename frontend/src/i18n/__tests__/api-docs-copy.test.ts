// @vitest-environment node
//
// This guard reads Python route modules off the real filesystem, so it needs a real path:
// jsdom hands out `http://localhost/...` URLs for `import.meta.url`, and `readFileSync`
// refuses those. The node environment keeps this file out of the jsdom suite instead of
// making the path depend on the working directory.
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';

import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

/**
 * The API Reference page is hand-written prose, and nothing connected it to the routers.
 *
 * It advertised three endpoints: `POST /api/v1/extract`, `POST /api/v1/batch` and
 * `GET /api/v1/status/{id}`. Only the third shape was ever real, and never at that path —
 * extraction moved under `/api/v1/workspaces/{workspace_id}/extract` and `POST /batch`
 * has never existed in this codebase (`docs/deployment.md` records batch processing as a
 * pending gap). A public reference that names endpoints the API does not serve is worse
 * than no reference: it is a documented promise that 404s.
 *
 * Both sides are derived, not restated. The declared paths come from the router
 * declarations and their decorators in `backend/src/storico/api/routes/*.py` — the same
 * source FastAPI reads — and the advertised paths come from the page itself. Nothing here
 * holds a second copy of the route table that could drift on its own.
 */
const ROUTES_DIR = new URL('../../../../backend/src/storico/api/routes/', import.meta.url);
const API_DOCS_PAGE = new URL('../../pages/[locale]/api.astro', import.meta.url);

const apiDocsSource = readFileSync(API_DOCS_PAGE, 'utf8');

/** `/api/v1/batch` was invented; the other two are paths the API answers `410 Gone` on. */
const RETIRED_API_PATHS = ['/api/v1/batch', '/api/v1/extract', '/api/v1/status/'];

/** Both forms of a path work — FastAPI redirects the slash — so the slash is not the drift. */
const normalize = (path: string) => path.replace(/\/+$/, '');

/**
 * Every path the routers declare, composed from each `APIRouter(prefix=...)` and the
 * route strings of its decorators, and mapped to the file that declares it.
 *
 * No nested parentheses appear inside any `APIRouter(...)` call in this backend, so the
 * argument block can be captured up to the first `)`. Both are asserted below: a silent
 * empty parse would otherwise make every "advertised path is declared" case vacuous.
 */
function declaredPaths(): Map<string, string> {
  const declared = new Map<string, string>();

  for (const file of readdirSync(ROUTES_DIR).filter((name) => name.endsWith('.py'))) {
    const source = readFileSync(new URL(file, ROUTES_DIR), 'utf8');

    const prefixes = new Map<string, string>();
    for (const match of source.matchAll(/^(\w+)\s*=\s*APIRouter\(([^)]*)\)/gm)) {
      const prefix = match[2].match(/prefix="([^"]*)"/)?.[1];
      if (prefix !== undefined) prefixes.set(match[1], prefix);
    }

    for (const match of source.matchAll(
      /@(\w+)\.(?:get|post|put|patch|delete|api_route)\(\s*"([^"]*)"/g,
    )) {
      const prefix = prefixes.get(match[1]);
      if (prefix === undefined) continue;
      declared.set(normalize(prefix + match[2]), file);
    }
  }

  return declared;
}

const DECLARED = declaredPaths();

/** The `path:` values of the page's endpoint list, and every `/api/v1/...` token it prints. */
const ADVERTISED = [...apiDocsSource.matchAll(/path:\s*'(\/api\/v1\/[^']*)'/g)].map((m) =>
  normalize(m[1]),
);

const PATH_TOKENS = [
  ...new Set(
    [...apiDocsSource.matchAll(/\/api\/v1\/[A-Za-z0-9{}/_-]*/g)].map((m) => normalize(m[0])),
  ),
];

const CATALOGS = { en: en as Record<string, unknown>, es: es as Record<string, unknown> };

/** The `pages.api` section of a catalog, as flat strings — the copy this page renders. */
function apiCopy(node: unknown, path = ''): { path: string; value: string }[] {
  if (typeof node === 'string') return [{ path, value: node }];
  if (typeof node !== 'object' || node === null) return [];

  return Object.entries(node).flatMap(([key, child]) =>
    apiCopy(child, path ? `${path}.${key}` : key),
  );
}

const API_COPY = Object.fromEntries(
  Object.entries(CATALOGS).map(([locale, catalog]) => [
    locale,
    apiCopy((catalog as { pages: { api: unknown } }).pages.api),
  ]),
);

describe('the router parse is not vacuous', () => {
  it('finds the routers and a real number of routes', () => {
    // 30 unique paths are published in `/openapi.json`; the two legacy catch-alls in
    // `extraction.py` and `projects.py` add one path each and are hidden from the schema.
    // The floor sits just under 32 so a parser that silently lost a whole module fails here.
    expect(DECLARED.size).toBeGreaterThan(30);
  });

  it('declares the legacy catch-alls too, which is how the decorator branch is covered', () => {
    expect(DECLARED.has('/api/v1/extract/{path:path}')).toBe(true);
    expect(DECLARED.has('/api/v1/projects/{path:path}')).toBe(true);
  });

  it('declares paths that are known to exist', () => {
    expect(DECLARED.has('/api/v1/health')).toBe(true);
    expect(DECLARED.has('/api/v1/stories')).toBe(true);
    expect(DECLARED.has('/api/v1/workspaces/{workspace_id}/extract')).toBe(true);
    expect(
      DECLARED.has('/api/v1/workspaces/{workspace_id}/extract/status/{extraction_id}'),
    ).toBe(true);
  });

  it('declares no batch endpoint, which is why the page must not advertise one', () => {
    expect([...DECLARED.keys()].filter((path) => path.includes('batch'))).toEqual([]);
  });

  it('extracts the advertised paths from the page', () => {
    expect(ADVERTISED.length).toBeGreaterThanOrEqual(2);
    expect(new Set(ADVERTISED).size).toBe(ADVERTISED.length);
  });

  it('leaves no `/api/v1/...` token on the page outside the endpoint list', () => {
    expect([...PATH_TOKENS].sort()).toEqual([...ADVERTISED].sort());
  });
});

describe('the API Reference page', () => {
  it('advertises only paths the routers declare', () => {
    for (const path of ADVERTISED) {
      expect(DECLARED.has(path), `${path} is advertised but declared in no router`).toBe(true);
    }
  });

  it('advertises the workspace-scoped extraction pair', () => {
    expect(ADVERTISED).toEqual([
      '/api/v1/workspaces/{workspace_id}/extract',
      '/api/v1/workspaces/{workspace_id}/extract/status/{extraction_id}',
    ]);
  });

  it('mentions none of the retired paths', () => {
    for (const retired of RETIRED_API_PATHS) {
      expect(apiDocsSource.includes(retired), `${retired} is retired copy`).toBe(false);
    }
  });
});

describe('the API Reference copy', () => {
  it('names no retired path in either catalog', () => {
    for (const [locale, entries] of Object.entries(API_COPY)) {
      for (const { path, value } of entries) {
        for (const retired of RETIRED_API_PATHS) {
          expect(value.includes(retired), `${locale}:${path} names ${retired}`).toBe(false);
        }
      }
    }
  });

  it('carries no copy describing the batch endpoint the API never had', () => {
    // The key existed only to describe the removed row. Re-adding a batch row means
    // re-adding this key, and this guard is what makes that deliberate.
    expect(Object.keys((en as { pages: { api: object } }).pages.api)).not.toContain(
      'endpoint_batch_desc',
    );
    expect(Object.keys((es as { pages: { api: object } }).pages.api)).not.toContain(
      'endpoint_batch_desc',
    );
  });
});
