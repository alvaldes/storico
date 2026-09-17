import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    alias: {
      // `astro:transitions/client` is an Astro *virtual* module: it only exists
      // inside a real Astro build, so a plain vitest process cannot resolve it.
      // Point it at a test-only no-op stub so components that import it stay
      // loadable in tests. Production code still imports the real module.
      'astro:transitions/client': path.resolve(
        __dirname,
        './src/test/astro-transitions-client-stub.ts',
      ),
    },
    css: { modules: { classNameStrategy: 'non-scoped' } },
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/cypress/**',
      '**/.{idea,git,cache,output,temp}/**',
      '**/{karma,rollup,webpack,vite,vitest,jest,ava,babel,nyc,cypress,tsup,build,eslint,prettier}.config.*',
      // Playwright specs -- they run through `@playwright/test`, not vitest.
      'e2e/**',
    ],
  },
});
