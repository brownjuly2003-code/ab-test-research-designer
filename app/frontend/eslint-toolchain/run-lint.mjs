#!/usr/bin/env node
/**
 * Run ESLint against the parent frontend package using this toolchain's
 * TypeScript 5.9 + eslint plugins (app stays on TypeScript 7).
 *
 * Always loads brace-expansion dual-API preload and runs the compat preflight
 * before ESLint so minimatch@3 brace globs stay correct under the audit-clean
 * brace-expansion@5.0.8 override.
 */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const toolchainDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(toolchainDir, "..");
const eslintBin = path.join(toolchainDir, "node_modules", "eslint", "bin", "eslint.js");
const configPath = path.join(frontendRoot, "eslint.config.js");
const preloadPath = path.join(toolchainDir, "brace-expansion-compat-preload.cjs");
const preflightPath = path.join(toolchainDir, "brace-expansion-compat-preflight.cjs");

/**
 * @param {string[]} args
 * @param {{ cwd?: string, inherit?: boolean }} [opts]
 */
function runNode(args, opts = {}) {
  const result = spawnSync(process.execPath, args, {
    cwd: opts.cwd ?? toolchainDir,
    stdio: opts.inherit === false ? "pipe" : "inherit",
    env: process.env,
    encoding: "utf8",
  });
  return result;
}

const preflight = runNode(["-r", preloadPath, preflightPath], { cwd: toolchainDir });
if (preflight.status !== 0) {
  process.exit(preflight.status ?? 1);
}

const srcDir = path.join(frontendRoot, "src");
const result = runNode(
  ["-r", preloadPath, eslintBin, "--config", configPath, srcDir],
  { cwd: frontendRoot }
);

process.exit(result.status ?? 1);
