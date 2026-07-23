#!/usr/bin/env node
/**
 * Run ESLint against the parent frontend package using this toolchain's
 * TypeScript 5.9 + eslint plugins (app stays on TypeScript 7).
 */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const toolchainDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(toolchainDir, "..");
const eslintBin = path.join(toolchainDir, "node_modules", "eslint", "bin", "eslint.js");
const configPath = path.join(frontendRoot, "eslint.config.js");

const srcDir = path.join(frontendRoot, "src");
const result = spawnSync(
  process.execPath,
  [eslintBin, "--config", configPath, srcDir],
  {
    cwd: frontendRoot,
    stdio: "inherit",
    env: process.env
  }
);

process.exit(result.status ?? 1);
