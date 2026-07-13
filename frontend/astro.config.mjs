import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import auth from 'auth-astro';
import vercel from '@astrojs/vercel';

export default defineConfig({
  output: 'server',
  adapter: vercel(),
  // Security config for Vercel serverless deployment.
  //
  // checkOrigin: Astro's built-in CSRF check compares Origin vs url.origin
  // on POST requests. Auth.js already provides double-submit cookie CSRF
  // protection, making this redundant. Also avoids false 403 in Vercel.
  //
  // allowedDomains: Critical for Vercel. Astro's NodeApp.createRequest uses
  // this to validate the Host header when constructing the request URL.
  // Without it, the hostname falls back to "localhost", which breaks OAuth
  // redirect URIs (Google gets "https://localhost/..." instead of the real
  // URL). Must include the production domain AND localhost for dev.
  security: {
    checkOrigin: false,
    allowedDomains: [
      { hostname: 'storico.vercel.app' },
      { hostname: 'localhost' },
      { hostname: '127.0.0.1' },
    ],
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
