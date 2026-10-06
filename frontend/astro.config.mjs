import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import starlight from '@astrojs/starlight';
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
  integrations: [
    react(),
    auth(),
    // Starlight mounts at the site root; the docs path comes from nesting the
    // content under src/content/docs/en/docs/ and es/docs/. The top-level i18n
    // block above is the single owner of localisation (Option B): a Starlight
    // `locales` block next to it makes the build fail hard with
    // "Cannot provide both an Astro 'i18n' configuration and a Starlight
    // 'locales' configuration". 0.37.7 is the ceiling for Astro 5.
    // Explicit sidebar: the five docs pages in a deliberate reading order,
    // index first, instead of alphabetical autogeneration. Entries use
    // `link`, not `slug`: under `prefixDefaultLocale: true` every route slug
    // is locale-prefixed (en/docs/..., es/docs/...) and `slug` entries fail
    // to resolve on the locale-less prerendered 404 page ("The slug
    // \"docs/index\" specified in the Starlight sidebar config does not
    // exist"). `link` entries are locale-stripped paths; Starlight injects
    // the current page's locale prefix when rendering (/en/docs/quickstart,
    // /es/docs/quickstart).
    // No Starlight `locales` block: next to the top-level `i18n` config it
    // makes the build fail hard with "Cannot provide both an Astro 'i18n'
    // configuration and a Starlight 'locales' configuration".
    starlight({
      title: 'Storico Documentation',
      pagefind: true,
      // The app ships its own branded 404 (src/pages/404.astro, app layout plus
      // i18n). Without this, Starlight's static 404 shadows it for the whole
      // site, not just for /docs: the build warned that "/404" is defined twice
      // and the emitted .vercel/output/static/404.html was Starlight's.
      disable404Route: true,
      // Make the docs wear Storico's design system: remap Starlight's --sl-*
      // tokens onto the app's --color-* / --font-* tokens for both themes. The
      // file also mirrors the token values themselves, because globals.css is
      // not loaded on Starlight pages (they use Starlight's own layout).
      customCss: ['./src/styles/starlight.css'],
      // Component overrides for the theme bridge: Head injects the app→Starlight
      // inline theme script (src/lib/theme-bridge.ts) pre-paint; ThemeSelect
      // writes the app's `theme` key instead of Starlight's `starlight-theme`.
      // SiteTitle and Header give the docs a header that knows where it lives
      // (brand → app home, `Docs` label → docs home) and where the app is (the
      // shared public nav links); see odd/tasks/docs-app-navigation.md.
      components: {
        Head: './src/components/starlight/Head.astro',
        ThemeSelect: './src/components/starlight/ThemeSelect.astro',
        SiteTitle: './src/components/starlight/SiteTitle.astro',
        Header: './src/components/starlight/Header.astro',
      },
      sidebar: [
        {
          label: 'Documentation',
          translations: { es: 'Documentación' },
          link: '/docs/',
        },
        {
          label: 'Quickstart',
          translations: { es: 'Inicio rápido' },
          link: '/docs/quickstart',
        },
        {
          label: 'User story format',
          translations: { es: 'Formato de historia de usuario' },
          link: '/docs/story-format',
        },
        {
          label: 'LLM providers',
          translations: { es: 'Proveedores de LLM' },
          link: '/docs/llm-providers',
        },
        {
          label: 'Export',
          translations: { es: 'Exportación' },
          link: '/docs/export',
        },
        {
          label: 'Kanban board',
          translations: { es: 'Tablero Kanban' },
          link: '/docs/kanban',
        },
        {
          label: 'Extraction versions',
          translations: { es: 'Versiones de extracción' },
          link: '/docs/extraction-versions',
        },
        {
          label: 'Historical context',
          translations: { es: 'Contexto histórico' },
          link: '/docs/embeddings-rag',
        },
        {
          label: 'Roles and permissions',
          translations: { es: 'Roles y permisos' },
          link: '/docs/roles-permissions',
        },
        {
          // Generated from the FastAPI app by `storico.scripts.render_api_reference`
          // and guarded by backend/tests/test_api_reference.py, which fails when the
          // committed page drifts from the spec. See odd/tasks/api-reference.md.
          label: 'API reference',
          translations: { es: 'Referencia de la API' },
          link: '/docs/api-reference',
        },
      ],
    }),
  ],
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
