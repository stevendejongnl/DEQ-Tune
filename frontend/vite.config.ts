import ttsc from "@ttsc/unplugin/vite";
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";
import { execSync } from "node:child_process";
import type { Plugin } from "vite";

/** The commit and the minute of this build. A Docker build has no `.git`,
 * so it has no commit either. */
function makeBuildId(): string {
  let commit = "nogit";
  try {
    commit = execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    // Keep "nogit".
  }
  return `${commit}-${new Date().toISOString().slice(0, 16)}`;
}

const BUILD_ID = makeBuildId();

/** Writes the build id beside the page. The backend reads the file and
 * reports it, and the app compares it with the id it was built with. A
 * page whose id differs is a cached copy of an older build. */
function buildIdFile(): Plugin {
  return {
    name: "deq-build-id",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "build-id.txt", source: `${BUILD_ID}\n` });
    },
  };
}

export default defineConfig({
  define: {
    __DEQ_BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  plugins: [
    ttsc(),
    buildIdFile(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "DEQ Tune",
        short_name: "DEQ Tune",
        description: "Pioneer DEQ equalizer profiles, in the browser.",
        theme_color: "#12110f",
        background_color: "#12110f",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "pwa-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
          { src: "maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // The backend API is live data (users edit profiles). Never serve it from cache.
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: /^\/api\//,
            handler: "NetworkOnly",
          },
        ],
      },
    }),
  ],
  // The ttsc transform writes imports of typia's deep internals, so Vite's
  // first scan cannot see them: it discovers them mid-run, re-optimizes,
  // and reloads the page. Naming them here means one cold start instead of
  // a start plus a re-optimize. `npm run warm` fills the cache without a
  // browser. After that, a start reuses it.
  optimizeDeps: {
    include: [
      "typia",
      "typia/lib/internal/_accessExpressionAsString",
      "typia/lib/internal/_assertGuard",
    ],
  },
  server: {
    proxy: {
      "/api": "http://localhost:8420",
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    fsModuleCache: true,
    // `e2e/` belongs to Playwright. Without this, vitest loads those specs
    // too and Playwright's own `test.beforeEach` throws.
    include: ["src/**/*.test.ts"],
  },
});
