import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import auth from 'auth-astro';
import node from '@astrojs/node';

export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [react(), auth()],
  site: 'http://localhost:4321',
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'es'],
    routing: {
      prefixDefaultLocale: true,
      strategy: 'pathname',
    },
  },
  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts: ['.ngrok-free.app'],
    },
    // env vars read from frontend/.env (default Astro behavior)
    optimizeDeps: {
      include: ['zustand'],
      // auth-astro ships raw .ts files that import types from
      // next-auth (a devDependency not installed in production).
      // Excluding from pre-bundling lets Vite transform each .ts
      // on-the-fly, stripping type-only imports without resolution.
      exclude: ['auth-astro', 'auth:config'],
    },
  },
});
