// @vitest-environment node
//
// The middleware cannot be imported here: it pulls `astro:middleware` (virtual) and, on the one
// branch that needs it, `auth-astro/server`. So the wiring is pinned at the source level, the same
// technique `retired-paths.test.ts` uses for the middleware's redirect/skip ordering.
//
// The property this guard exists to pin is the one that keeps `pnpm build` environment-free: the
// docs prerender (20 Starlight pages) imports and runs this middleware at build time, and a
// top-level static import of `auth-astro/server` drags `auth.config.ts` → `src/lib/config.ts` into
// the build graph — a module that throws at import time by design (`required('API_URL')`). With
// the static import, a tree with no `.env` cannot build at all (CI at `ac3b832`, run
// `37540247596`). With the dynamic import sitting inside the protected-path branch, the auth
// module only enters the graph when a request actually needs a session.
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';

const MIDDLEWARE = readFileSync(new URL('../../middleware.ts', import.meta.url), 'utf8');

describe('middleware keeps auth-astro/server out of the build-time graph', () => {
  /**
   * This is the case that keeps the build environment-free. A static `import ... from
   * 'auth-astro/server'` at the top of the middleware pulls `src/lib/config.ts` (which throws
   * `Missing required environment variable: API_URL` at import time) into the prerender of every
   * Starlight docs page. Reintroducing it breaks `pnpm build` on any machine without `.env` —
   * exactly what CI is.
   */
  it('has no top-level static import of auth-astro/server', () => {
    expect(MIDDLEWARE).not.toMatch(/^\s*import\s+[^;]*from\s+['"]auth-astro\/server['"]/m);
  });

  /**
   * Every ordering case is vacuous if either needle is missing, so both surfaces are read before
   * the order is compared — the same non-vacuity guard `retired-paths.test.ts` uses.
   */
  it('reads both surfaces it compares, or the ordering case is vacuous', () => {
    expect(MIDDLEWARE).toMatch(/isProtectedPagePath\(/);
    expect(MIDDLEWARE).toMatch(/import\(['"]auth-astro\/server['"]\)/);
    expect(MIDDLEWARE).toMatch(/locals\.session\s*=/);
  });

  it('loads the session inside the protected-path branch, before the locals.session assignment', () => {
    const branch = MIDDLEWARE.indexOf('isProtectedPagePath(pathname)');
    const dynamicImport = MIDDLEWARE.indexOf("import('auth-astro/server')");
    const assignment = MIDDLEWARE.indexOf('context.locals.session =');
    expect(dynamicImport, 'the auth module must be loaded dynamically').toBeGreaterThan(-1);
    expect(assignment, 'locals.session must still be assigned').toBeGreaterThan(-1);
    expect(
      dynamicImport,
      'the dynamic import must sit inside the protected-path branch, not before it',
    ).toBeGreaterThan(branch);
    expect(
      assignment,
      'the session must be assigned after the dynamic import resolves',
    ).toBeGreaterThan(dynamicImport);
  });
});

describe('locals.session is assigned only inside the protected-path branch', () => {
  it('writes locals.session exactly once, after the branch opens', () => {
    const writes = MIDDLEWARE.match(/locals\.session\s*=/g) ?? [];
    expect(writes).toHaveLength(1);
    const branch = MIDDLEWARE.indexOf('isProtectedPagePath(pathname)');
    expect(MIDDLEWARE.indexOf('context.locals.session =')).toBeGreaterThan(branch);
  });
});

/**
 * The conditional assignment is safe only because nothing else reads `locals.session`: pages that
 * want a session call `getSession(Astro.request)` themselves. If a future page starts reading
 * `Astro.locals.session`, it would see `undefined` on public paths — a silent break this scan is
 * here to catch. The middleware itself and this test directory are excluded; both are read in the
 * ordering cases above.
 */
const SRC_DIR = new URL('../..', import.meta.url).pathname; // frontend/src/
// `.d.ts` files are type declarations, not code: they can mention `locals.session` but cannot read
// it at runtime. `env.d.ts` declares the field itself, so it is excluded by kind, not by name.
const EXCLUDED = (p: string) =>
  p.includes('__tests__') || p.endsWith('middleware.ts') || p.endsWith('.d.ts');
const SRC_FILES = readdirSync(SRC_DIR, { recursive: true, encoding: 'utf8' })
  .filter((p) => /\.(ts|tsx|astro|mjs|js)$/.test(p) && !EXCLUDED(p));

describe('locals.session is read nowhere outside the middleware guard', () => {
  it('finds at least one candidate file, or the scan is vacuous', () => {
    expect(SRC_FILES.length).toBeGreaterThan(0);
  });

  it('has no locals.session read in src/ outside the middleware', () => {
    const readers = SRC_FILES.filter((file) =>
      readFileSync(`${SRC_DIR}${file}`, 'utf8').includes('locals.session'),
    );
    expect(readers, 'files reading locals.session outside the middleware').toEqual([]);
  });
});
