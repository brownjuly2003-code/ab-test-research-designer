// This spec mirrors the canonical Python smoke flow in `scripts/run_local_smoke.py`.
// It stays out of the main app tsconfig because it uses Node + Playwright globals.

import { expect, test } from "@playwright/test";
const browserDraftStorageKey = "ab-test-research-designer:draft:v1";

test("imports the demo project and completes the browser smoke flow", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "AB Test Research Designer" })).toBeVisible();
  await expect(page.getByText("Plan your A/B experiment")).toBeVisible();

  await page.getByRole("button", { name: "System", exact: true }).click();
  await expect(page.getByText("API online")).toBeVisible();
  await page.getByRole("button", { name: "Projects", exact: true }).click();

  await page.getByRole("button", { name: "Load example" }).click();
  await expect(page.getByText("Example loaded - click Run analysis to see results")).toBeVisible();

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

  const markdownDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Markdown" }).click();
  const markdownDownload = await markdownDownloadPromise;
  expect(markdownDownload.suggestedFilename()).toContain("report");

  const htmlDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export HTML" }).click();
  const htmlDownload = await htmlDownloadPromise;
  expect(htmlDownload.suggestedFilename()).toContain("report");
});
