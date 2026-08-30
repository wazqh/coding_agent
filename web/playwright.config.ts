import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "../.test-runs/playwright",
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    colorScheme: "light",
    locale: "zh-CN",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "acceptance-1024", use: { viewport: { width: 1024, height: 700 } } },
    { name: "demo-1920", use: { viewport: { width: 1920, height: 1080 } } },
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    stdout: "ignore",
    stderr: "pipe",
  },
});
