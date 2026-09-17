/**
 * Test-only stand-in for Astro's virtual `astro:transitions/client` module.
 *
 * That specifier only exists inside a real Astro build, so plain vitest (no
 * `astro()` plugin; see `vitest.config.ts`) cannot resolve it and every component
 * importing it would fail to load. `vitest.config.ts` points the specifier here.
 *
 * Tests that need to observe navigation replace this stub with a spy via
 * `vi.mock('astro:transitions/client', ...)`; this default keeps every other test
 * loadable when the module is imported but never called.
 */

/** No-op navigator. The real module drives the browser router; tests do not. */
export function navigate(_path: string): void {
  // Intentionally empty.
}
