// Vite plugin to fix use-sync-external-store shim ESM exports
export default function shimFixPlugin() {
  return {
    name: 'shim-fix',
    resolveId(source, importer) {
      if (source === 'use-sync-external-store/shim') {
        return { id: 'use-sync-external-store', external: false };
      }
      if (source === 'use-sync-external-store/shim/with-selector') {
        return { id: 'use-sync-external-store/with-selector', external: false };
      }
      if (source === 'use-sync-external-store/shim/index.js') {
        return { id: 'use-sync-external-store', external: false };
      }
      return null;
    },
    load(id) {
      if (id === 'use-sync-external-store/shim' || id === 'use-sync-external-store/shim/with-selector' || id === 'use-sync-external-store/shim/index.js') {
        // Redirect to proper ESM entry points
        return null; // Let resolveId handle it
      }
      return null;
    },
    configureServer(server) {
      // Intercept direct /node_modules/ requests for the shim
      server.middlewares.use((req, res, next) => {
        if (req.url?.includes('/use-sync-external-store/shim')) {
          // Redirect to proper entry point
          const newUrl = req.url.replace('/use-sync-external-store/shim', '/use-sync-external-store');
          req.url = newUrl;
        }
        next();
      });
    },
  };
}
