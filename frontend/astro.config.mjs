import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import auth from 'auth-astro';
import vercel from '@astrojs/vercel';

export default defineConfig({
  output: 'server',
  adapter: vercel(),
  security: {
    checkOrigin: false,
    allowedDomains: [
      { hostname: 'storico.vercel.app' },
      { hostname: 'localhost' },
      { hostname: '127.0.0.1' },
    ],
  },
  integrations: [react(), auth()],
  site: process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : 'http://localhost:4321',
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'es'],
    routing: {
      prefixDefaultLocale: true,
      strategy: 'pathname',
    },
  },
  vite: {
    optimizeDeps: {
      // Pin every browser dependency that islands import eagerly, including deep
      // subpaths. Discovery alone is not enough: when the dev-time scan misses,
      // the prebundle silently degrades to this list and an island importing a
      // @base-ui-backed primitive dies on a stale ?v= hash (504 Outdated
      // Optimize Dep, then "Failed to fetch dynamically imported module").
      // Add a line here when a new primitive is adopted in src/ui; the glob
      // '@base-ui/react/**' is not usable because it also expands internals/*,
      // which import the uninstalled optional peer 'luxon'.
      include: [
        'react',
        'react-dom',
        'zustand',
        'zod',
        'lucide-react',
        'cmdk',
        'sonner',
        'class-variance-authority',
        'clsx',
        'tailwind-merge',
        '@hello-pangea/dnd',
        '@base-ui/react',
        '@base-ui/react/accordion',
        '@base-ui/react/alert-dialog',
        '@base-ui/react/avatar',
        '@base-ui/react/button',
        '@base-ui/react/collapsible',
        '@base-ui/react/dialog',
        '@base-ui/react/input',
        '@base-ui/react/menu',
        '@base-ui/react/merge-props',
        '@base-ui/react/popover',
        '@base-ui/react/preview-card',
        '@base-ui/react/progress',
        '@base-ui/react/radio',
        '@base-ui/react/radio-group',
        '@base-ui/react/scroll-area',
        '@base-ui/react/select',
        '@base-ui/react/separator',
        '@base-ui/react/slider',
        '@base-ui/react/switch',
        '@base-ui/react/toggle',
        '@base-ui/react/toggle-group',
        '@base-ui/react/tooltip',
        '@base-ui/react/use-render',
      ],
      exclude: ['auth-astro', 'auth:config'],
    },
  },
});
