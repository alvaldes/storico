import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import auth from 'auth-astro';
import vercel from '@astrojs/vercel';

export default defineConfig({
  output: 'server',
  adapter: vercel(),
  // Disable Astro's built-in CSRF origin check — Auth.js (@auth/core) already
  // provides double-submit cookie CSRF protection. Astro's check can fail in
  // serverless environments (Vercel) due to how Origin headers are forwarded
  // through the edge network, causing false 403 on signin POST.
  security: {
    checkOrigin: false,
  },
  integrations: [react(), auth()],
  site: process.env.VERCEL_URL
    ? `https://${process.env.VERCEL_URL}`
    : 'http://localhost:4321',
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
    optimizeDeps: {
      include: ['zustand'],
      exclude: ['auth-astro', 'auth:config'],
    },
  },
});
