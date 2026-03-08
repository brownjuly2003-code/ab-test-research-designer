// This spec mirrors the canonical Python smoke flow in `scripts/run_local_smoke.py`.
// It stays out of the main app tsconfig because it uses Node + Playwright globals.

import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";


const currentDir = path.dirname(fileURLToPath(import.meta.url));
const sampleProjectPath = path.resolve(currentDir, "../../../../docs/demo/sample-project.json");
test("imports the demo project and completes the browser smoke flow", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "AB Test Research Designer" })).toBeVisible();
  await expect(page.getByText("API online")).toBeVisible();

  await page.getByLabel("Import draft file").setInputFiles(sampleProjectPath);
  await expect(
    page.getByText("Imported draft from sample-project.json. Save it to create a new local project record.")
  ).toBeVisible();

  await expect(page.locator("#project-project_name")).toHaveValue("Checkout redesign");
  await expect(page.locator("#project-project_description")).toHaveValue(
    /simplified checkout flow/i
  );

  await page.getByRole("button", { name: "Save project" }).click();
  await expect(page.getByText("Project saved locally with id", { exact: false })).toBeVisible();

  await page.locator("#project-project_name").fill("Smoke restored draft");
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByText("Restored unsaved browser draft.")).toBeVisible();
  await expect(page.locator("#project-project_name")).toHaveValue("Smoke restored draft");

  for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
    await page.getByRole("button", { name: "Next" }).click();
  }

  await expect(page.getByText("Review inputs")).toBeVisible();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByText("Analysis completed.", { exact: false })).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("Deterministic experiment design")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Markdown" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain("report");
});
