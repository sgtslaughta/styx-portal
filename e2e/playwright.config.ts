import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:18080",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  // services.spec bootstraps the admin on a fresh DB, so it must run first; mounts.spec
  // logs in (or bootstraps itself when run alone with -g).
  projects: [
    { name: "services", testMatch: "services.spec.ts" },
    { name: "mounts", testMatch: "mounts.spec.ts", dependencies: ["services"] },
    { name: "shell", testMatch: "shell.spec.ts", dependencies: ["mounts"] },
  ],
});
