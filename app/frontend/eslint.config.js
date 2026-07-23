import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
// Side-by-side toolchain: TypeScript 5.9 + typescript-eslint (hard-throws on TS 7).
// App `typescript` stays at 7 for tsc/Vite; this require root forces parser/plugin
// resolution under eslint-toolchain/node_modules.
const toolchainRequire = createRequire(path.join(rootDir, "eslint-toolchain", "package.json"));
const js = toolchainRequire("@eslint/js");
const tsPlugin = toolchainRequire("@typescript-eslint/eslint-plugin");
const tsParser = toolchainRequire("@typescript-eslint/parser");
const jsxA11y = toolchainRequire("eslint-plugin-jsx-a11y");
const react = toolchainRequire("eslint-plugin-react");
const reactHooks = toolchainRequire("eslint-plugin-react-hooks");

/**
 * Flat ESLint baseline (plan step 8 / audit F-08).
 *
 * Zero-baseline policy: new violations fail `npm run lint`. Do not blanket
 * disable plugins to land a feature; fix the call site or add a narrow,
 * justified inline disable with a reason.
 */
export default [
  {
    ignores: [
      "dist/**",
      "coverage/**",
      "node_modules/**",
      "src/lib/generated/**",
      "eslint.config.js",
      "eslint-toolchain/**"
    ]
  },
  js.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        tsconfigRootDir: rootDir,
        warnOnUnsupportedTypeScriptVersion: false
      }
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      react,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y
    },
    settings: {
      react: { version: "detect" }
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...react.configs.flat.recommended.rules,
      ...react.configs.flat["jsx-runtime"].rules,
      ...jsxA11y.flatConfigs.recommended.rules,

      // Classic React Hooks only. Plugin v7 `recommended` also enables React
      // Compiler rules (set-state-in-effect, purity, …) that flag many valid
      // data-fetch effects; those stay off until a dedicated cleanup pass.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",

      // Project uses TypeScript for prop types.
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",

      // Prefer explicit intentional any at the boundary; keep noise low.
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_"
        }
      ],
      // TypeScript + ESLint both flag unused; prefer the TS-aware rule.
      "no-unused-vars": "off",
      // TS overload signatures are not redeclarations.
      "no-redeclare": "off",

      // Browser + Vitest globals; TS already typechecks identifiers.
      "no-undef": "off"
    }
  },
  {
    files: ["src/**/*.{test,spec}.{ts,tsx}", "src/test/**/*.{ts,tsx}"],
    rules: {
      // Test harnesses intentionally use non-semantic markup / roles.
      "jsx-a11y/no-static-element-interactions": "off",
      "jsx-a11y/click-events-have-key-events": "off"
    }
  }
];
