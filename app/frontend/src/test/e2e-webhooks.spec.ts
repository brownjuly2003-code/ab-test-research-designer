// Webhook manager CRUD (audit G-09 follow-up). Keys/webhooks are admin-only at
// the middleware level — with no AB_ADMIN_TOKEN configured the backend rejects
// every credential, and configuring one flips auth on for the whole instance,
// which would break the anonymous smoke flows. run_frontend_e2e.py therefore
// starts a second, admin-token-enabled backend and points this spec at it via
// AB_E2E_ADMIN_BASE_URL / AB_E2E_ADMIN_TOKEN.

import { expect, test } from "@playwright/test";

const adminBaseUrl = process.env.AB_E2E_ADMIN_BASE_URL;
const adminToken = process.env.AB_E2E_ADMIN_TOKEN ?? "";

test.use({ baseURL: adminBaseUrl });

test("creates and deletes a webhook subscription through the manager", async ({ page }) => {
  test.skip(!adminBaseUrl, "admin backend not provisioned (run via scripts/run_frontend_e2e.py)");

  await page.goto("/?admin=1", { waitUntil: "networkidle" });

  // The API keys tab (webhook manager host) appears once the admin session
  // token is stored and verified against /api/v1/keys.
  await page.getByRole("button", { name: "System", exact: true }).click();
  await page.locator("#api-admin-token").fill(adminToken);
  await page.getByRole("button", { name: "Save admin token" }).click();

  const manager = page.getByTestId("webhook-manager");
  await expect(manager).toBeVisible();

  await page.getByRole("button", { name: "Create webhook" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.locator("#webhook-name").fill("E2E scenario hook");
  await page.locator("#webhook-target-url").fill("https://example.com/e2e-hook");
  await page.locator("#webhook-secret").fill("e2e-webhook-secret");
  await page.getByRole("button", { name: "Save webhook" }).click();

  await expect(page.getByText("Webhook subscription created.").first()).toBeVisible();
  const row = page.getByTestId("webhook-subscription-row").filter({ hasText: "E2E scenario hook" });
  await expect(row).toBeVisible();
  await expect(row.getByText("https://example.com/e2e-hook")).toBeVisible();

  await row.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByText("Webhook subscription deleted.").first()).toBeVisible();
  await expect(
    manager.getByTestId("webhook-subscription-row").filter({ hasText: "E2E scenario hook" })
  ).toHaveCount(0);
});
