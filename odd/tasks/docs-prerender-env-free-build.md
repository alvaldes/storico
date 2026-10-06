# docs-prerender-env-free-build

## Goal

Make `pnpm build` succeed with **no environment** again, without weakening the auth guard, so
that CI's `Build (astro build)` step and any fresh clone keep working.

## The regression, measured

`main` at `ac3b832` has a red CI run (`37540247596`, frontend job) at the build step:

```
prerendering static routes
▶ @astrojs/starlight/routes/static/index.astro
  ├─ /en/docs/api-reference/index.html   Missing required environment variable: API_URL
     at required (…/dist/server/chunks/config_WfUrtxcm.mjs:21:11)
     at ModuleJob.run (node:internal/modules/module_job:343:25)
     at async BuildPipeline.middleware (…/astro/dist/core/build/pipeline.js:98:19)
```

The chain, each link read in the source:

1. `astro build` prerenders the docs — 20 pages, `/en/docs/**` and `/es/docs/**` (10 × 2 locales;
   `find .vercel/output/static -name '*.html'`). Pagefind indexes exactly those pages, so the
   prerender cannot simply be turned off.
2. Prerendering imports and runs the project middleware: `astro/dist/core/build/pipeline.js:94-98`
   dynamically imports `internals.middlewareEntryPoint` and wraps it as the render middleware.
3. `frontend/src/middleware.ts:2` imported `getSession` from `auth-astro/server` at module top
   level, and `:15` called it unconditionally.
4. `auth-astro/server` resolves the project's `auth.config.ts`, which does
   `import { config } from './src/lib/config'` (`auth.config.ts:4`).
5. `frontend/src/lib/config.ts:15` **throws at import time** by design ("no silent fallbacks"):
   `required('API_URL')` and `required('AUTH_SECRET')` are evaluated while the object is built.

CI has no `.env`; a developer machine has `frontend/.env` (a symlink to the repo root `.env`). That
is the entire difference between green locally and red in CI.

Reproduced locally, on this machine, by moving `frontend/.env` aside for one build — the same
failure, byte for byte, with `config_D3tZHWdy.mjs:21:11` in place of CI's `config_WfUrtxcm.mjs`:
the **chunk hash is the only difference**, which is what makes this the same defect and not a
lookalike.

Two corrections to the first reading of the CI log, both worth keeping:

- **The page named in the error is incidental.** CI reported `/en/docs/api-reference/index.html`,
  the local run reported `/en/docs/embeddings-rag/index.html`. Whichever page is prerendered first
  is the one named; **every** docs page fails the same way.
- **`ci.yml`'s comment is not stale — it was true, and it is true again after this fix.** The green
  run before this push (`37388702843`, on `54abdc7`) prerendered **zero** pages (`✓ Completed in
  63ms`) because that tree had no Starlight at all: the docs mounting and its ten content pages
  were in the 58 commits this push published. The comment says the config module "is evaluated per
  request, not at build time"; the docs prerender is the first thing that made that false.

## Decision

**Fetch the session where it is consumed, with a dynamic import** — not by listing the prerendered
docs paths in the middleware.

`src/middleware.ts` assigned `context.locals.session` on every request and read it in exactly one
place: the protected-page guard. Nothing else reads it — `auth-astro` 4.2.0 injects no middleware
and never touches `locals.session` (its integration only `injectRoute`s `/api/auth/[...auth]`,
`node_modules/auth-astro/src/integration.ts:27`), and every page that wants a session calls
`getSession(Astro.request)` itself (`src/pages/[locale]/index.astro:15`,
`src/pages/[locale]/projects/index.astro:9`, `src/pages/[locale]/projects/[id].astro:9`,
`src/pages/api/v1/[...path].ts:42`).

So the guard becomes:

```
if (getLocaleFromPath(pathname) && isProtectedPagePath(pathname)) {
  const { getSession } = await import('auth-astro/server');
  context.locals.session = await getSession(context.request);
  …identical redirect logic…
}
```

Why this and not a docs-subtree early return:

- It removes the dependency structurally: the auth module enters the graph only on the branch that
  needs it, so **any** future prerendered public page stays environment-free. An enumeration of
  `/en/docs/**` would have to be revisited by whoever prerenders the next public page, and its only
  justification would be a build-time artifact.
- It stops calling `getSession` — cookie parsing and a `@auth/core` round trip — on every public
  request that never looked at the result.
- The protected-path guard keeps byte-identical behaviour: same branch, same condition, same
  redirect. What changes is only that `locals.session` is no longer populated on paths that never
  read it.

**Honesty cost, accepted:** `src/env.d.ts` must drop the claim that `locals.session` is always
present (`session: Session | null` → `session?: Session | null`), because it now is not. The type
that lied by omission is the one thing this fix deliberately weakens, and the optional marker is
what makes the next reader handle it instead of trusting it.

## Tasks

- [x] 1. `src/middleware.ts`: move the static `auth-astro/server` import into the protected-path guard as a dynamic import; assign `locals.session` only there; leave the retired-path redirect, `SKIP_PREFIX`, locale redirects and the guard's redirect logic untouched.
- [x] 2. `src/env.d.ts`: `session?: Session | null`, with a comment naming the reason.
- [x] 3. `src/lib/__tests__/middleware-session-import.test.ts`: pin the load-bearing property at the source level (the middleware cannot be imported — it pulls `astro:middleware`), the same technique `retired-paths.test.ts` uses:
       a. `middleware.ts` has **no** top-level static import of `auth-astro/server`;
       b. the dynamic import sits inside the `isProtectedPagePath` branch, pinned by index order, with the same "reads both surfaces or the case is vacuous" guard that file uses;
       c. `locals.session` is only assigned inside that branch, and read nowhere but the guard;
       d. `locals.session` is read nowhere else in `src/` — the invariant that makes the conditional assignment safe. Without this case, a future page that reads `Astro.locals.session` breaks silently.
- [x] 4. Prove the new guard by triangulation: re-breaking each pinned property makes the suite fail, restoring it makes it pass, and `middleware.ts` / `env.d.ts` are byte-identical after the probe (`cmp`).
- [x] 5. Environment-free build: `pnpm build` with `frontend/.env` moved aside exits 0 and emits the same 20 docs pages (`/tmp/baseline-html.txt`, taken at `ac3b832` before the change).
- [x] 6. Output equivalence: the normal build (with `.env`) emits a static tree identical to the pre-fix snapshot (`/tmp/baseline-docs/static`); any diff is classified, not waved through.
- [x] 7. `pnpm exec tsc --noEmit` exit 0 and `pnpm vitest run` green (72 files / 823 tests at `ac3b832`, plus the new cases).

## Non-goals

- No change to `ci.yml`. Its comment becomes true again rather than being rewritten to bless a
  build that needs secrets.
- No change to the docs prerender itself, to Starlight, or to Pagefind — the 20 prerendered pages
  are the point, not the problem.
- No change to `auth.config.ts`, `src/lib/config.ts` or its fail-loudly contract. The module is
  right to throw; the mistake was importing it where nothing needed it.
- No auth behaviour change: the guard's condition, order and redirect are untouched.

## Verification

- RED, recorded before the change: environment-free build fails with
  `Missing required environment variable: API_URL` at the docs prerender (`/tmp/build-noenv.log`).
- GREEN: environment-free build exits 0.
- Equivalence: pre/post static tree diff, and `tsc` + vitest + build as the ordinary gates.
- The deploy workflow is unaffected (it builds only the backend image); this defect is a CI gate
  failure, not a production outage. Whether Vercel's own build of `ac3b832` succeeded was **not**
  verified from here: Vercel carries `API_URL` in its project environment, so it is expected to
  have built, and that expectation is unproven.

## Result

The fix is `38227b6` (`fix(web): keep the auth config out of the docs prerender build`) on
`fix/docs-prerender-env-free-build`: the `auth-astro/server` import is dynamic and inside the
protected-path guard, `locals.session` is assigned only there, `env.d.ts` declares the field
optional, and `src/lib/__tests__/middleware-session-import.test.ts` pins the four properties.

Evidence from the implementing worker and from a separate read-only verification of that commit:

| Check | Result |
| --- | --- |
| Environment-free build | exit 0; Pagefind found 20 HTML files; the emitted page list matches the pre-fix baseline byte for byte |
| RED baseline | `/tmp/build-noenv.log:147` `Missing required environment variable: API_URL`, exit 1 — the same defect as CI, differing only in chunk hash and in which page was named |
| Site equivalence | one differing file only: `pagefind/pagefind-entry.json` (see below) |
| `tsc --noEmit` | exit 0 |
| `pnpm vitest run` | 73 files / 829 tests green (72/823 before, +6 from the new file) |
| Triangulation | re-adding the static import fails exactly `has no top-level static import of auth-astro/server`, with the file echoed (the right reason, not a parse error); the file is byte-identical after restore (`cmp`, 2977 B, and `git diff --quiet`) |
| `locals.session` readers | none outside the middleware guard; every session consumer calls `getSession(Astro.request)` itself (`MainLayout.astro:15`, `PublicLayout.astro:30`, `[locale]/index.astro:15`, `projects/index.astro:9`, `projects/[id].astro:9`, `api/v1/[...path].ts:42`) |
| Guard equivalence | same condition, same target, same 302; old `!locals.session && isProtectedPagePath` and new `isProtectedPagePath → load → !session` reach the same branch |

### `pagefind/pagefind-entry.json`: classified, and what is still unproven

The two `languages` map keys swap order (`en,es` → `es,en`). Everything that carries content is
identical: all 20 HTML inputs byte-identical, `pagefind/index/` and `pagefind/fragment/` trees
identical, `pagefind.js`/`.pf_meta`/wasm `cmp`-identical, per-language hashes `en_f63160b656` and
`es_9ab27a3cbe` equal, `page_count: 10` each. The ordering was traced to enumeration order rather
than to this change: Starlight only calls `index.addDirectory({ path: dir })`, and the Pagefind
node API produces `en,es` when `en` is added first and `es,en` when `es` is first — so the key order
is exactly the order languages are encountered. The middleware does not run during indexing.

**Unproven:** a full-pipeline build was not reproduced with `en,es` after the change (both post-fix
builds were `es,en`), and top-level `readdir` returns `en` before `es`, so the walk order inside
Pagefind — plausibly inode- or timing-sensitive — was not pinned. The classification rests on the
mechanism plus identical inputs, not on a reproduction of the flip.

## Limitations carried forward

- **The guard is lexical, not behavioural.** It pins the shape of the source, not the effect: case
  (a) would not see `import 'auth-astro/server'` without `from`, an `export … from`, a `require`, or
  an import laundered through a local module — and it would false-fail on a harmless `import type`.
  Cases (b) and (c) compare index positions, so they cannot prove *block containment*: hoisting both
  the dynamic import and the assignment below the closed branch satisfies both. Case (d) is a
  substring scan for `locals.session`, so it misses bracket access, `locals?.session`,
  `const { session } = Astro.locals` and `const l = Astro.locals; l.session`.
- **What actually enforces the property is CI.** The build step has no `.env`, so a reintroduced
  build-time environment dependency fails there regardless of the source guard; the guard is a
  faster tripwire in front of that gate, not a replacement for it. This is why the containment gap
  above is recorded rather than closed with a third layer of lexical assertions.
- **A page shipped inside `__tests__` sits outside case (d)'s scan.** Defensible, and a hole.
- **Vercel's build of `ac3b832` was never checked from here** (unrelated to this fix's own gate).
- **Piped invocation suppresses the trap.** The environment-free build recipe moves `frontend/.env`
  aside under an `EXIT` trap. Piping the whole group (`{ … } 2>&1 | tail`) makes it a subshell and
  the trap does not fire, leaving `.env` moved aside; the unpiped form is what works. Restore by hand
  with `mv -f frontend/.env.ci-offline.tmp frontend/.env` if it happens, then confirm with
  `readlink frontend/.env` in a separate shell — the trap fires at shell exit, so checking inside the
  same shell races it and reports a false failure.
