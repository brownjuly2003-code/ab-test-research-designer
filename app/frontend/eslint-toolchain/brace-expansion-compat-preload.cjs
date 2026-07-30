#!/usr/bin/env node
/**
 * Dual-API shim for brace-expansion@5 when required by minimatch@3.
 *
 * minimatch@3 does:  const expand = require('brace-expansion'); expand(pattern)
 * brace-expansion@5: module.exports = { expand, EXPANSION_MAX, ... }  (not callable)
 *
 * A plain npm override to 5.0.8 is audit-clean but breaks brace globs such as
 * *.{ts,tsx} inside eslint-plugin-react / jsx-a11y (see jsx-eslint/eslint-plugin-react#4021).
 *
 * This preload wraps the *actual* installed brace-expansion@5 exports so that:
 *   - typeof mod === 'function'  → old minimatch@3 callable API
 *   - mod.expand(...)            → modern minimatch@10 / named export path
 * Expansion always delegates to upstream v5 (CVE-2026-14257 / GHSA-mh99-v99m-4gvg limits).
 *
 * Load via: node -r ./brace-expansion-compat-preload.cjs ...
 */
"use strict";

const Module = require("module");
const path = require("path");

const COMPAT_FLAG = "__abBraceExpansionCompat";
const EXPECTED_NAME = "brace-expansion";

/** @type {typeof Module._load} */
const originalLoad = Module._load;

/**
 * @param {unknown} exports
 * @returns {unknown}
 */
function wrapBraceExpansionExports(exports) {
  if (exports == null) {
    return exports;
  }

  // Already wrapped by this preload (or re-entered via cache).
  if (typeof exports === "function" && exports[COMPAT_FLAG] === true) {
    return exports;
  }

  // Unexpected dual form from another shim — leave alone.
  if (typeof exports === "function" && typeof exports.expand === "function") {
    return exports;
  }

  // Legacy brace-expansion@1 callable-only shape (should not appear under our override).
  if (typeof exports === "function") {
    return exports;
  }

  const upstream = /** @type {Record<string, unknown>} */ (exports);
  if (typeof upstream.expand !== "function") {
    return exports;
  }

  /** @type {(...args: unknown[]) => unknown} */
  const upstreamExpand = /** @type {(...args: unknown[]) => unknown} */ (
    upstream.expand
  );

  /**
   * Callable entry used by minimatch@3 (`expand(pattern)`).
   * @param {string} str
   * @param {object} [options]
   */
  function dualExpand(str, options) {
    return upstreamExpand(str, options);
  }

  dualExpand.expand = upstreamExpand;
  dualExpand[COMPAT_FLAG] = true;
  dualExpand.__abBraceExpansionUpstream = upstream;

  for (const key of Object.keys(upstream)) {
    if (key === "expand") {
      continue;
    }
    if (!(key in dualExpand)) {
      dualExpand[key] = upstream[key];
    }
  }

  return dualExpand;
}

/**
 * @param {string} request
 * @param {NodeModule | null | undefined} parent
 * @returns {boolean}
 */
function isBraceExpansionRequest(request, parent) {
  if (request === EXPECTED_NAME) {
    return true;
  }
  // Absolute / relative resolves that land on the package root entry.
  if (!request.includes(EXPECTED_NAME)) {
    return false;
  }
  try {
    const resolved = Module._resolveFilename(request, parent, false);
    const normalized = resolved.replace(/\\/g, "/");
    return (
      normalized.includes("/brace-expansion/") &&
      (normalized.endsWith("/brace-expansion/dist/commonjs/index.js") ||
        normalized.endsWith("/brace-expansion/index.js") ||
        /\/brace-expansion\/dist\/commonjs\/index\.js$/.test(normalized))
    );
  } catch {
    return false;
  }
}

Module._load = function abBraceExpansionCompatLoad(request, parent, isMain) {
  const loaded = originalLoad.apply(this, arguments);

  if (!isBraceExpansionRequest(request, parent)) {
    return loaded;
  }

  const wrapped = wrapBraceExpansionExports(loaded);

  // Keep require.cache aligned so later consumers see the dual API.
  try {
    const resolved = Module._resolveFilename(request, parent, isMain);
    const cached = Module._cache[resolved];
    if (cached && cached.exports !== wrapped) {
      cached.exports = wrapped;
    }
  } catch {
    // Resolution edge cases: still return wrapped value for this call.
  }

  return wrapped;
};

// Mark process so preflight can assert the preload is active.
process.__abBraceExpansionCompatPreload = {
  active: true,
  file: path.resolve(__filename),
  expectedPackage: EXPECTED_NAME,
  expectedSafeVersion: "5.0.8",
};
