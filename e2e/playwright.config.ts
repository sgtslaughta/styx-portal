import { defineConfig } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:18080";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL: BASE,
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce", // screenshots are never caught mid-fade
    // Existing specs assert app tiles on home: start every context on the Apps tab.
    storageState: { cookies: [], origins: [{ origin: BASE, localStorage: [{ name: "styx.home.tab", value: "apps" }] }] },
    trace: "retain-on-failure",
  },
  // services.spec bootstraps the admin on a fresh DB, so it must run first; mounts.spec
  // logs in (or bootstraps itself when run alone with -g).
  projects: [
    { name: "services", testMatch: "services.spec.ts" },
    { name: "mounts", testMatch: "mounts.spec.ts", dependencies: ["services"] },
    { name: "shell", testMatch: "shell.spec.ts", dependencies: ["mounts"] },
    { name: "shots", testMatch: "shots.spec.ts", dependencies: ["shell"] },
    { name: "shots-home", testMatch: "shots-home.spec.ts", dependencies: ["shots"] },
    { name: "workspaces", testMatch: "workspaces.spec.ts", dependencies: ["shots-home"] },
  ],
});
