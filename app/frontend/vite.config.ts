import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Node 26 ships experimental Web Storage: localStorage/sessionStorage exist on
// globalThis but are undefined without --localstorage-file, which stops vitest's
// jsdom environment from installing jsdom's working Storage (existing globals are
// preserved) and binds Storage.prototype spies to the wrong class. Vitest 4 ignores
// poolOptions.*.execArgv, so pass the flag via NODE_OPTIONS — worker processes
// inherit it and start with clean globals, restoring exact Node 22 semantics.
// The flag exists on node >=22.4 (the project floor is 22 LTS).
if (process.env.VITEST) {
  const webstorageFlag = "--no-experimental-webstorage";
  if (!process.env.NODE_OPTIONS?.includes(webstorageFlag)) {
    process.env.NODE_OPTIONS = [process.env.NODE_OPTIONS, webstorageFlag].filter(Boolean).join(" ");
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173
  },
  build: {
    rollupOptions: {
      output: {
        // vite 8 (rolldown) dropped the object form of manualChunks; the
        // function keeps the same vendor split as before.
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return "vendor-react";
          if (/[\\/]node_modules[\\/](i18next|react-i18next|i18next-browser-languagedetector)[\\/]/.test(id)) return "vendor-i18n";
          if (/[\\/]node_modules[\\/]zustand[\\/]/.test(id)) return "vendor-state";
          if (/[\\/]node_modules[\\/]lucide-react[\\/]/.test(id)) return "vendor-icons";
          if (/[\\/]node_modules[\\/]@floating-ui[\\/]/.test(id)) return "vendor-floating";
          return undefined;
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
    maxWorkers: 8,
    // Coverage runs only in the dedicated CI job (`npm run test:coverage`):
    // instrumentation multiplies suite runtime, so it stays off the verify path.
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/test/**",
        "src/lib/generated/**",
        "src/main.tsx"
      ],
      reporter: ["text-summary", "json-summary"],
      // Floors = measured coverage minus ~3 p.p. (2026-07-17 baseline:
      // statements 78.35, branches 70.32, functions 81.5, lines 78.38).
      thresholds: {
        lines: 75,
        statements: 75,
        functions: 78,
        branches: 67
      }
    }
  }
});
