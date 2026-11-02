import { defineConfig } from "@playwright/test";
// Throwaway mobile audit: every screen at phone sizes, screenshots + overflow/tap-target report.
export default defineConfig({
  testDir: "./tests", testMatch: "mobile-audit.spec.ts", workers: 1, timeout: 1_800_000, reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:18080", deviceScaleFactor: 2, isMobile: true, hasTouch: true, reducedMotion: "reduce", actionTimeout: 5_000 },
});
