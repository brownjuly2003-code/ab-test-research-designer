// This spec mirrors the canonical Python smoke flow in `scripts/run_local_smoke.py`.
// It stays out of the main app tsconfig because it uses Node + Playwright globals.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { expect, test, type Page } from "@playwright/test";

const browserDraftStorageKey = "ab-test-research-designer:draft:v1";
const require = createRequire(import.meta.url);
// Load axe source once; inject via page.evaluate (CSP blocks addScriptTag on this app).
const axeSource = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

type AxeViolation = {
  id: string;
  impact?: string | null;
  help: string;
  nodes: Array<{ target: string[] }>;
};

type AxeResults = {
  violations: AxeViolation[];
};

async function runLandingAxe(page: Page): Promise<AxeResults> {
  // CDP evaluate is not subject to the page CSP script-src restriction.
  await page.evaluate(axeSource);
  return page.evaluate(async () => {
    const axeRunner = (
      window as Window & {
        axe?: {
          run: (
            context: Document,
            options: { runOnly: { type: string; values: string[] } }
          ) => Promise<AxeResults>;
        };
      }
    ).axe;
    if (!axeRunner) {
      throw new Error("axe-core failed to initialize in the page context");
    }
    return axeRunner.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
      }
    });
  });
}

function formatSeriousViolations(violations: AxeViolation[]): string {
  return violations
    .map((violation) => {
      const targets = violation.nodes
        .slice(0, 4)
        .map((node) => node.target.join(" "))
        .join("; ");
      return `${violation.id} [${violation.impact}] ${violation.help} → ${targets}`;
    })
    .join("\n");
}

/** Normalize rgb/rgba computed colors so transition polling is browser-stable. */
function normalizeCssColor(value: string): string {
  const match = value.match(
    /rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)/i
  );
  if (!match) {
    return value.trim();
  }
  const r = Math.round(Number(match[1]));
  const g = Math.round(Number(match[2]));
  const b = Math.round(Number(match[3]));
  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Theme toggles update CSS variables immediately, but topbar controls animate
 * background/color over --transition-fast. Axe samples mid-transition frames as
 * false color-contrast failures — wait for steady-state computed styles first.
 */
async function waitForSettledThemeStyles(page: Page, theme: "light" | "dark"): Promise<void> {
  const expected =
    theme === "dark"
      ? {
          // tokens.css dark: surface-elevated / text / text-secondary / surface-muted
          linkBg: "rgb(29, 38, 56)",
          linkFg: "rgb(238, 242, 248)",
          inactiveFg: "rgb(154, 165, 184)",
          segBg: "rgb(27, 35, 52)"
        }
      : {
          linkBg: "rgb(255, 255, 255)",
          linkFg: "rgb(15, 23, 41)",
          inactiveFg: "rgb(90, 100, 115)",
          segBg: "rgb(243, 245, 249)"
        };

  await expect
    .poll(
      async () => {
        const snapshot = await page.evaluate(() => {
          const link = document.querySelector(".topbar-link");
          const inactive = document.querySelector('.theme-seg-button[aria-pressed="false"]');
          const seg = document.querySelector(".theme-seg");
          if (!link || !inactive || !seg) {
            return null;
          }
          const linkStyle = getComputedStyle(link);
          const inactiveStyle = getComputedStyle(inactive);
          const segStyle = getComputedStyle(seg);
          return {
            linkBg: linkStyle.backgroundColor,
            linkFg: linkStyle.color,
            inactiveFg: inactiveStyle.color,
            segBg: segStyle.backgroundColor
          };
        });
        if (!snapshot) {
          return null;
        }
        return {
          linkBg: normalizeCssColor(snapshot.linkBg),
          linkFg: normalizeCssColor(snapshot.linkFg),
          inactiveFg: normalizeCssColor(snapshot.inactiveFg),
          segBg: normalizeCssColor(snapshot.segBg)
        };
      },
      { timeout: 5_000, intervals: [50, 100, 150, 200] }
    )
    .toEqual(expected);
}

test("keeps the topbar within narrow viewports", async ({ page }) => {
  for (const width of [320, 375] as const) {
    await page.setViewportSize({ width, height: 812 });
    await page.goto("/", { waitUntil: "networkidle" });

    const overflow = await page.evaluate(() => {
      const root = document.documentElement;
      return {
        clientWidth: root.clientWidth,
        scrollWidth: root.scrollWidth,
      };
    });
    expect(
      overflow.scrollWidth,
      `documentElement overflow at ${width}px: scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth}`
    ).toBeLessThanOrEqual(overflow.clientWidth);

    const controlsBox = await page.locator(".topbar-controls").boundingBox();
    expect(controlsBox, `.topbar-controls missing at ${width}px`).not.toBeNull();
    if (controlsBox) {
      expect(controlsBox.x, `.topbar-controls left edge at ${width}px`).toBeGreaterThanOrEqual(0);
      expect(
        controlsBox.x + controlsBox.width,
        `.topbar-controls right edge at ${width}px`
      ).toBeLessThanOrEqual(width + 1);
    }

    await expect(page.getByRole("link", { name: "Theory" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Language preference" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Theme preference" })).toBeVisible();
  }
});

test("keeps the landing page free of serious accessibility violations", async ({ page, request }) => {
  // E2E backends do not enable AB_SEED_DEMO_ON_STARTUP; ensure the landing demos
  // container is present so the named-region regression is deterministic.
  const existingDemos = await request.get("/api/v1/projects?limit=50");
  expect(existingDemos.ok()).toBeTruthy();
  const existingPayload = (await existingDemos.json()) as {
    projects?: Array<{ project_name?: string }>;
  };
  const hasDemo = (existingPayload.projects ?? []).some((project) =>
    String(project.project_name ?? "").startsWith("Demo - ")
  );
  if (!hasDemo) {
    const createResponse = await request.post("/api/v1/projects", {
      data: {
        project: {
          project_name: "Demo - A11y Landing Fixture",
          domain: "e-commerce",
          product_type: "web app",
          platform: "web",
          market: "US",
          project_description: "Accessibility regression fixture for the landing demos region."
        },
        hypothesis: {
          change_description: "Simplify checkout",
          target_audience: "new users on web",
          business_problem: "checkout abandonment is high",
          hypothesis_statement: "Simplifying checkout will increase purchase conversion.",
          what_to_validate: "impact on conversion",
          desired_result: "statistically meaningful uplift"
        },
        setup: {
          experiment_type: "ab",
          randomization_unit: "user",
          traffic_split: [50, 50],
          expected_daily_traffic: 12000,
          audience_share_in_test: 0.6,
          variants_count: 2,
          inclusion_criteria: "new users only",
          exclusion_criteria: "internal staff"
        },
        metrics: {
          primary_metric_name: "purchase_conversion",
          metric_type: "binary",
          baseline_value: 0.042,
          expected_uplift_pct: 8,
          mde_pct: 5,
          alpha: 0.05,
          power: 0.8,
          std_dev: null,
          secondary_metrics: ["add_to_cart_rate"],
          guardrail_metrics: []
        },
        constraints: {
          seasonality_present: true,
          active_campaigns_present: false,
          returning_users_present: true,
          interference_risk: "medium",
          technical_constraints: "none",
          legal_or_ethics_constraints: "none",
          known_risks: "none",
          deadline_pressure: "medium",
          long_test_possible: true,
          n_looks: 1,
          analysis_mode: "frequentist",
          desired_precision: null,
          credibility: 0.95
        },
        additional_context: {
          llm_context: "Fixture project for landing-page accessibility coverage."
        }
      }
    });
    expect(createResponse.ok(), `demo fixture create failed: ${createResponse.status()}`).toBeTruthy();
  }

  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Plan your A/B experiment" })).toBeVisible();
  // Demo cards must be present so the named landmark is in the a11y tree.
  await expect(page.getByRole("heading", { name: "Explore live demo projects" })).toBeVisible();

  for (const theme of ["light", "dark"] as const) {
    await page.getByRole("button", { name: `${theme === "light" ? "Light" : "Dark"} theme` }).click();
    await expect
      .poll(async () => page.locator("html").getAttribute("data-theme"))
      .toBe(theme);
    await waitForSettledThemeStyles(page, theme);

    // Demos container must expose a named landmark (section/region), not aria-label alone.
    await expect(
      page.getByRole("region", { name: "Explore live demo projects" })
    ).toBeVisible();

    const results = await runLandingAxe(page);
    const seriousOrCritical = results.violations.filter(
      (violation) => violation.impact === "serious" || violation.impact === "critical"
    );
    expect(
      seriousOrCritical,
      `Serious/critical WCAG A/AA axe violations in ${theme} theme:\n${formatSeriousViolations(seriousOrCritical)}`
    ).toEqual([]);
  }
});

test("imports the demo project and completes the browser smoke flow", async ({ page }) => {
  // Operator surfaces (System / API keys tabs) are gated behind ?admin=1 in the
  // public app; the smoke flow opts into them to exercise the backend tiles.
  await page.goto("/?admin=1", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Plan your A/B experiment" })).toBeVisible();
  await expect(page.getByText("AB Test Research Designer")).toBeVisible();

  await page.getByRole("button", { name: "System", exact: true }).click();
  await expect(page.getByText("API online")).toBeVisible();
  await page.getByRole("button", { name: "Projects", exact: true }).click();

  await page.getByRole("button", { name: "Load example" }).click();
  // The status surfaces in both the App-level banner and the ResultsPanel inline status, so
  // match the first (same pattern as the "Analysis completed." assertion below).
  await expect(
    page.getByText("Example loaded - click Run analysis to see results").first()
  ).toBeVisible();

  await expect(page.locator("#project-project_name")).toHaveValue("Checkout redesign");
  await expect(page.locator("#project-project_description")).toHaveValue(
    /simplified checkout flow/i
  );

  await page.locator("#project-project_name").fill("Smoke draft persistence check");
  await page.waitForFunction(
    ([storageKey, expectedValue]) => {
      const storedDraft = window.localStorage.getItem(storageKey);
      return typeof storedDraft === "string" && storedDraft.includes(expectedValue);
    },
    [browserDraftStorageKey, "Smoke draft persistence check"]
  );
  await page.locator("#project-project_name").fill("Checkout redesign");
  await page.waitForFunction(
    ([storageKey, expectedValue]) => {
      const storedDraft = window.localStorage.getItem(storageKey);
      return typeof storedDraft === "string" && storedDraft.includes(expectedValue);
    },
    [browserDraftStorageKey, "Checkout redesign"]
  );
  await expect(page.locator("#project-project_name")).toHaveValue("Checkout redesign");

  for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
    await page.getByRole("button", { name: "Next" }).click();
  }

  await expect(page.getByText("Review inputs")).toBeVisible();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByText("Analysis completed.", { exact: false }).first()).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("Deterministic experiment design")).toBeVisible();

  const exportButton = page.getByRole("button", { name: "Export", exact: true });
  await expect(exportButton).toBeVisible();

  await exportButton.click();
  await expect(page.getByRole("button", { name: "Export Markdown" })).toBeVisible();
  const markdownDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Markdown" }).click();
  const markdownDownload = await markdownDownloadPromise;
  expect(markdownDownload.suggestedFilename()).toContain("report");

  await exportButton.click();
  await expect(page.getByRole("button", { name: "Export HTML" })).toBeVisible();
  const htmlDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export HTML" }).click();
  const htmlDownload = await htmlDownloadPromise;
  expect(htmlDownload.suggestedFilename()).toContain("report");
});
