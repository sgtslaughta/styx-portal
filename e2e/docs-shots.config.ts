import { defineConfig } from "@playwright/test";

// Standalone config for the docs screenshots (the main config chains the functional specs).
// Run via e2e/docs-shots/run.sh against the isolated stack on 127.0.0.1:18080.
export default defineConfig({
  testDir: "./tests",
  testMatch: "docs-shots.spec.ts",
  workers: 1,
  timeout: 300_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:18080",
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    actionTimeout: 15_000,
    reducedMotion: "reduce",
  },
});
