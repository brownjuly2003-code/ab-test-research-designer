import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = process.env.AB_E2E_BASE_URL ?? "http://127.0.0.1:8010";
const currentDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./src/test",
  testMatch: ["e2e-smoke.spec.ts"],
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: {
    timeout: 15_000
  },
  reporter: process.env.CI ? "dot" : "line",
  outputDir: "./test-results/playwright",
  use: {
    baseURL: baseUrl,
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    viewport: {
      width: 1440,
      height: 1200
    }
  },
  webServer: process.env.AB_E2E_BASE_URL
    ? undefined
    : {
        command: "python ../../scripts/run_backend_for_e2e.py",
        cwd: currentDir,
        url: `${baseUrl}/health`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000
      }
});
