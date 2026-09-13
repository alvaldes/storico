import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import auth from "auth-astro";
import vercel from "@astrojs/vercel";

export default defineConfig({
  output: "server",
  adapter: vercel(),
  security: {
    checkOrigin: false,
    allowedDomains: [
      { hostname: "storico.vercel.app" },
      { hostname: "localhost" },
      { hostname: "127.0.0.1" },
    ],
  },
  integrations: [react(), auth()],
  site: process.env.VERCEL_URL
    ? `https://${process.env.VERCEL_URL}`
    : "http://localhost:4321",
  i18n: {
    defaultLocale: "en",
    locales: ["en", "es"],
    routing: {
      prefixDefaultLocale: true,
      strategy: "pathname",
    },
  },
  vite: {
    optimizeDeps: {
      include: ["react", "react-dom", "zustand", "zod", "lucide-react"],
      exclude: [
        "auth-astro",
        "auth:config",
        "@base-ui/react",
        "@base-ui/utils",
      ],
    },
    resolve: {
      alias: [
        {
          find: /^use-sync-external-store$/,
          replacement: "react",
        },
        {
          find: /^use-sync-external-store\/shim$/,
          replacement: "react",
        },
        {
          find: /^use-sync-external-store\/shim\/with-selector$/,
          replacement: "use-sync-external-store/with-selector",
        },
      ],
    },
  },
});
