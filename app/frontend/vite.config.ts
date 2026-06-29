import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom"],
          "vendor-i18n": ["i18next", "react-i18next", "i18next-browser-languagedetector"],
          "vendor-state": ["zustand"],
          "vendor-icons": ["lucide-react"],
          "vendor-floating": ["@floating-ui/react-dom"]
        }
      }
    },
    chunkSizeWarningLimit: 500
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
    // axe-driven a11y tests are CPU-bound: ~2-3s in isolation but 5-30s+ when one
    // jsdom worker per core competes for CPU. The vitest defaults (5s timeout,
    // worker per core) made full local runs flaky; a higher ceiling plus a worker
    // cap keeps the gate deterministic without slowing low-core CI runners.
    testTimeout: 30000,
    maxWorkers: 8
  }
});
