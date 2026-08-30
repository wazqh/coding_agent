import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/coding_agent/web/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}", "electron/**/*.test.ts"],
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    globals: true,
  },
});
