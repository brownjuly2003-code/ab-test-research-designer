#!/usr/bin/env node
/**
 * Deterministic preflight for brace-expansion dual-API compatibility.
 *
 * Must run under brace-expansion-compat-preload.cjs (node -r ...).
 * Fails hard if:
 *   - preload is absent
 *   - installed brace-expansion is not the safe 5.0.8 override target
 *   - dual API (callable + .expand) is missing
 *   - plugin-resolved minimatch@3 cannot match brace globs
 *   - modern minimatch@10 brace API regresses
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { createRequire } = require("module");

const toolchainDir = __dirname;
const requireFromToolchain = createRequire(path.join(toolchainDir, "package.json"));

const EXPECTED_BE_VERSION = "5.0.8";
const BRACE_GLOB = "*.{ts,tsx}";
const SAMPLE_FILE = "a.ts";

/**
 * @param {string} message
 * @returns {never}
 */
function fail(message) {
  console.error(`[brace-expansion-compat-preflight] ${message}`);
  process.exit(1);
}

function assertPreloadActive() {
  const marker = process.__abBraceExpansionCompatPreload;
  if (!marker || marker.active !== true) {
    fail(
      "compat preload is not active. Run via: node -r ./brace-expansion-compat-preload.cjs ./brace-expansion-compat-preflight.cjs"
    );
  }
}

function assertBraceExpansionSafeAndDual() {
  let pkg;
  try {
    pkg = requireFromToolchain("brace-expansion/package.json");
  } catch (err) {
    fail(`cannot resolve brace-expansion package.json: ${err.message}`);
  }

  if (pkg.name !== "brace-expansion") {
    fail(`unexpected package name at brace-expansion resolution: ${pkg.name}`);
  }
  if (pkg.version !== EXPECTED_BE_VERSION) {
    fail(
      `brace-expansion version mismatch: got ${pkg.version}, expected pinned safe ${EXPECTED_BE_VERSION} (override/graph drift)`
    );
  }

  let be;
  try {
    be = requireFromToolchain("brace-expansion");
  } catch (err) {
    fail(`cannot require brace-expansion: ${err.message}`);
  }

  if (typeof be !== "function") {
    fail(
      `brace-expansion must be callable for minimatch@3 (got typeof ${typeof be}). Adapter missing or ineffective.`
    );
  }
  if (be.__abBraceExpansionCompat !== true) {
    fail(
      "brace-expansion callable export is not the project compat adapter (missing __abBraceExpansionCompat)"
    );
  }
  if (typeof be.expand !== "function") {
    fail("brace-expansion.expand must remain a function for minimatch@10 / modern consumers");
  }
  if (typeof be.EXPANSION_MAX !== "number" || typeof be.EXPANSION_MAX_LENGTH !== "number") {
    fail(
      "brace-expansion is missing EXPANSION_MAX / EXPANSION_MAX_LENGTH (not safe v5 API surface)"
    );
  }

  let viaCall;
  let viaExpand;
  try {
    viaCall = be(BRACE_GLOB);
    viaExpand = be.expand(BRACE_GLOB);
  } catch (err) {
    fail(`brace-expansion dual expand threw: ${err && err.stack ? err.stack : err}`);
  }

  if (!Array.isArray(viaCall) || !viaCall.includes("*.ts") || !viaCall.includes("*.tsx")) {
    fail(`callable expand(${JSON.stringify(BRACE_GLOB)}) returned unexpected: ${JSON.stringify(viaCall)}`);
  }
  if (!Array.isArray(viaExpand) || !viaExpand.includes("*.ts") || !viaExpand.includes("*.tsx")) {
    fail(`.expand(${JSON.stringify(BRACE_GLOB)}) returned unexpected: ${JSON.stringify(viaExpand)}`);
  }
}

/**
 * @param {string} label
 * @param {string} minimatchEntry
 */
function assertPluginMinimatch(label, minimatchEntry) {
  if (!fs.existsSync(minimatchEntry)) {
    fail(
      `${label}: minimatch not found at ${minimatchEntry} (plugin dependency graph changed; re-validate override strategy)`
    );
  }

  let pkg;
  try {
    pkg = require(path.join(path.dirname(minimatchEntry), "package.json"));
  } catch {
    // package.json may sit one level up depending on entry file layout
    try {
      pkg = require(path.join(path.dirname(minimatchEntry), "..", "package.json"));
    } catch (err) {
      fail(`${label}: cannot read minimatch package.json: ${err.message}`);
    }
  }

  const major = Number.parseInt(String(pkg.version).split(".")[0], 10);
  if (major !== 3) {
    fail(
      `${label}: expected minimatch major 3 under plugin (got ${pkg.version}); guarded dual-API assumptions no longer match`
    );
  }

  // Clear minimatch cache so it re-requires brace-expansion under the active preload.
  // (Safe: preflight is a short-lived process.)
  for (const key of Object.keys(require.cache)) {
    if (key.replace(/\\/g, "/").includes("/minimatch/")) {
      delete require.cache[key];
    }
  }

  let minimatch;
  try {
    minimatch = require(minimatchEntry);
  } catch (err) {
    fail(`${label}: require(minimatch) failed: ${err && err.stack ? err.stack : err}`);
  }

  if (typeof minimatch !== "function") {
    fail(`${label}: plugin minimatch export is not callable (got typeof ${typeof minimatch})`);
  }

  let matched;
  try {
    matched = minimatch(SAMPLE_FILE, BRACE_GLOB);
  } catch (err) {
    fail(
      `${label}: minimatch(${JSON.stringify(SAMPLE_FILE)}, ${JSON.stringify(BRACE_GLOB)}) threw: ${
        err && err.stack ? err.stack : err
      }`
    );
  }

  if (matched !== true) {
    fail(
      `${label}: expected minimatch(${JSON.stringify(SAMPLE_FILE)}, ${JSON.stringify(
        BRACE_GLOB
      )}) === true, got ${JSON.stringify(matched)}`
    );
  }
}

function assertModernMinimatch() {
  let mm;
  try {
    mm = requireFromToolchain("minimatch");
  } catch (err) {
    fail(`cannot require top-level minimatch: ${err.message}`);
  }

  if (typeof mm.minimatch !== "function") {
    fail("modern minimatch.minimatch is not a function");
  }
  if (typeof mm.braceExpand !== "function") {
    fail("modern minimatch.braceExpand is not a function");
  }

  let matched;
  let expanded;
  try {
    matched = mm.minimatch(SAMPLE_FILE, BRACE_GLOB);
    expanded = mm.braceExpand(BRACE_GLOB);
  } catch (err) {
    fail(`modern minimatch brace path threw: ${err && err.stack ? err.stack : err}`);
  }

  if (matched !== true) {
    fail(
      `modern minimatch.minimatch(${JSON.stringify(SAMPLE_FILE)}, ${JSON.stringify(
        BRACE_GLOB
      )}) expected true, got ${JSON.stringify(matched)}`
    );
  }
  if (!Array.isArray(expanded) || !expanded.includes("*.ts") || !expanded.includes("*.tsx")) {
    fail(`modern minimatch.braceExpand unexpected: ${JSON.stringify(expanded)}`);
  }
}

function main() {
  assertPreloadActive();
  assertBraceExpansionSafeAndDual();

  const reactMinimatch = path.join(
    toolchainDir,
    "node_modules",
    "eslint-plugin-react",
    "node_modules",
    "minimatch",
    "minimatch.js"
  );
  const jsxA11yMinimatch = path.join(
    toolchainDir,
    "node_modules",
    "eslint-plugin-jsx-a11y",
    "node_modules",
    "minimatch",
    "minimatch.js"
  );

  assertPluginMinimatch("eslint-plugin-react", reactMinimatch);
  assertPluginMinimatch("eslint-plugin-jsx-a11y", jsxA11yMinimatch);
  assertModernMinimatch();

  console.log(
    `[brace-expansion-compat-preflight] ok: brace-expansion@${EXPECTED_BE_VERSION} dual-API + plugin brace globs`
  );
}

main();
