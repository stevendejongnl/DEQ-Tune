import ttsc from "@ttsc/unplugin/vite";
import { defineConfig } from "vitest/config";
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
 * page whose id differs is an older build that stayed open. */
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
