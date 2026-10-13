import { defineConfig, mergeConfig } from "vite";
import base from "./vite.config";

// Shell lives under /_styx/app/ because /assets/* belongs to a focused app (spec §6.1).
export default mergeConfig(base, defineConfig({
  base: "/_styx/app/",
  publicDir: false,
  build: { outDir: "dist/_styx/app", emptyOutDir: true, rollupOptions: { input: "shell.html" } },
}));
