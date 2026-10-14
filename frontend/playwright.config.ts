import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests, in a real browser.
 *
 * These cover what jsdom cannot: real rendering, real CSS nesting, and the
 * whole path from a click to the backend and back. `vitest` keeps the unit
 * tests next to their components. These tests use `.spec.ts` under `e2e/`,
 * so the two runners never pick up each other's files.
 *
 * The backend runs with `DEQ_TRANSPORT=fake`, so the unit that the backend
 * connects to is the fake DEQ. No hardware, and the replies are the ones
 * measured from a real DEQ-S1000A2.
 */
const FRONTEND_PORT = 5273;
// `vite.config.ts` proxies /api to this port, so the e2e backend uses it too.
const BACKEND_PORT = 8420;

export default defineConfig({
  testDir: "./e2e",
  // A failing assertion here is a real bug, not a flake to retry away.
  retries: 0,
  // The frontend's `typia` transform compiles the module graph on the first
  // request, which takes about twenty seconds on a cold cache. That compile
  // is the one slow step. Every test after it is fast.
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  reporter: process.env.CI ? "list" : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    // The app needs no WebUSB any more, so Chromium is a choice of one
    // engine to test in, not a requirement.
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command:
        `PYTHONPATH=. DEQ_TRANSPORT=fake DEQ_DB_PATH=e2e.db ` +
        `uv run uvicorn app.main:app --port ${BACKEND_PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${BACKEND_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort --host 127.0.0.1`,
      // Vite answers 404 on an unknown path but the port is what matters,
      // so wait for the port rather than for a URL to return 200.
      port: FRONTEND_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
