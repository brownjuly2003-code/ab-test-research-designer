import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { expect, test, type Page } from "@playwright/test";

const require = createRequire(import.meta.url);
const axeSource = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

type AxeViolation = {
  id: string;
  impact?: string | null;
  help: string;
  nodes: Array<{ target: string[] }>;
};

type RunSummary = {
  run_id: string;
  bundle_id: string;
  kind: string;
  verdicts: Record<string, string>;
};

async function seriousAxeViolations(page: Page): Promise<AxeViolation[]> {
  await page.evaluate(axeSource);
  const violations = await page.evaluate(async () => {
    const axeRunner = (
      window as Window & {
        axe?: {
          run: (
            context: Document,
            options: { runOnly: { type: string; values: string[] } }
          ) => Promise<{ violations: AxeViolation[] }>;
        };
      }
    ).axe;
    if (!axeRunner) throw new Error("axe-core failed to initialize");
    return (
      await axeRunner.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
        }
      })
    ).violations;
  });
  return violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical"
  );
}

async function waitForSettledThemeControlStyles(
  page: Page,
  theme: "light" | "dark"
): Promise<void> {
  const expected = theme === "dark"
    ? "rgb(154, 165, 184)|rgb(27, 35, 52)"
    : "rgb(90, 100, 115)|rgb(243, 245, 249)";
  await expect
    .poll(
      () => page.locator('.theme-seg-button[aria-pressed="false"]').first().evaluate((button) => {
        const group = button.closest(".theme-seg");
        if (!group) return null;
        return `${getComputedStyle(button).color}|${getComputedStyle(group).backgroundColor}`;
      }),
      { timeout: 5_000, intervals: [50, 100, 150, 200] }
    )
    .toBe(expected);
}

test("persists a real decision without mutating the selected ASOS run", async (
  { browser, page, request },
  testInfo
) => {
  const consoleErrors: string[] = [];
  const failedApiResponses: string[] = [];
  let axeAuditActive = false;
  page.on("console", (message) => {
    const text = message.text();
    const axeStylesheetProbeBlocked =
      axeAuditActive &&
      text.includes("fonts.googleapis.com/css2") &&
      text.includes("violates the following Content Security Policy directive") &&
      text.includes("connect-src 'self'");
    if (message.type() === "error" && !axeStylesheetProbeBlocked) {
      consoleErrors.push(text);
    }
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 400) {
      failedApiResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });

  await page.route("https://fonts.googleapis.com/**", (route) =>
    route.fulfill({ contentType: "text/css", body: "" })
  );
  await page.route("https://fonts.gstatic.com/**", (route) => route.fulfill({ status: 204 }));

  const portfolioResponse = await request.get("/api/v2/runs");
  expect(portfolioResponse.ok(), `portfolio failed: ${portfolioResponse.status()}`).toBeTruthy();
  const portfolio = (await portfolioResponse.json()) as { runs: RunSummary[] };
  expect(portfolio.runs).toHaveLength(3);
  expect(portfolio.runs.every((run) => run.verdicts.lineage === "pass")).toBeTruthy();
  const analysisRuns = portfolio.runs.filter((run) => run.kind === "analysis");
  expect(analysisRuns, "seeded analysis run is missing").toHaveLength(1);
  const selected = analysisRuns[0];

  await page.goto("/runs", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Evidence runs" })).toBeVisible();
  await expect(page.getByText("3 persisted runs", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: selected.run_id, exact: true }).click();

  await expect(page).toHaveURL(new RegExp(`/runs/${selected.run_id}$`));
  const parentResponse = await request.get(`/api/v2/runs/${selected.run_id}`);
  expect(parentResponse.ok()).toBeTruthy();
  const parent = await parentResponse.json();
  expect(parent.estimates).toHaveLength(1);
  await expect(
    page.getByRole("heading", { name: parent.protocol.protocol.title })
  ).toBeVisible();
  await expect(page.getByText(selected.run_id, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("lineage pass", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Effect estimates" })).toBeVisible();
  await expect(page.getByText("1 estimates", { exact: true })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .tmk" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`${selected.run_id}.tmk`);
  expect(await download.path()).not.toBeNull();

  const rationale = "The content-bound ASOS evidence supports this recorded benchmark decision.";
  await page.getByLabel("Verdict").selectOption("ship");
  await page.getByLabel("Rationale").fill(rationale);
  await page.getByRole("button", { name: "Record human decision" }).click();

  await expect(page).not.toHaveURL(new RegExp(`/runs/${selected.run_id}$`));
  await expect(page.getByRole("heading", { name: "Decision record" })).toBeVisible();
  await expect(page.getByText(rationale, { exact: true })).toBeVisible();
  await expect(page.getByText("local-operator", { exact: true })).toBeVisible();

  const unchangedParent = await (await request.get(`/api/v2/runs/${selected.run_id}`)).json();
  expect(unchangedParent).toEqual(parent);

  const secondContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  try {
    const secondPage = await secondContext.newPage();
    await secondPage.goto(`/runs/${selected.run_id}`, { waitUntil: "networkidle" });
    await expect(secondPage.getByRole("heading", { name: "Decision record" })).toHaveCount(0);
    await expect(secondPage.getByRole("button", { name: "Record human decision" })).toBeVisible();
  } finally {
    await secondContext.close();
  }

  for (const width of [375, 768, 1440] as const) {
    await page.setViewportSize({ width, height: 1000 });
    const overflow = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));
    expect(
      overflow.scrollWidth,
      `Workbench overflows at ${width}px: ${overflow.scrollWidth} > ${overflow.clientWidth}`
    ).toBeLessThanOrEqual(overflow.clientWidth);
    await page.screenshot({
      path: testInfo.outputPath(`workbench-${width}.png`),
      fullPage: true
    });
  }

  for (const theme of ["light", "dark"] as const) {
    await page.getByRole("button", { name: `${theme === "light" ? "Light" : "Dark"} theme` }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await waitForSettledThemeControlStyles(page, theme);
    axeAuditActive = true;
    let violations: AxeViolation[];
    try {
      violations = await seriousAxeViolations(page);
    } finally {
      axeAuditActive = false;
    }
    expect(violations, `serious/critical axe violations in ${theme} theme`).toEqual([]);
  }

  expect(failedApiResponses, `failed API responses:\n${failedApiResponses.join("\n")}`).toEqual([]);
  expect(consoleErrors, `browser console errors:\n${consoleErrors.join("\n")}`).toEqual([]);
});
