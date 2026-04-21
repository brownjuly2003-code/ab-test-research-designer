// @vitest-environment jsdom

import "vitest-axe/extend-expect";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    listWebhooksRequest: vi.fn()
  };
});

import WebhookManager from "../components/WebhookManager";
import i18n from "../i18n";
import { listWebhooksRequest } from "../lib/api";
import { click, flushEffects, renderIntoDocument } from "./dom";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

describe("WebhookManager accessibility", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    window.localStorage.clear();
    await i18n.changeLanguage("en");
    vi.mocked(listWebhooksRequest).mockResolvedValue({
      subscriptions: [],
      total: 0
    });
  });

  afterEach(async () => {
    await i18n.changeLanguage("en");
    vi.restoreAllMocks();
  });

  async function renderWebhookManager() {
    return renderIntoDocument(
      <I18nextProvider i18n={i18n}>
        <WebhookManager />
      </I18nextProvider>
    );
  }

  it("has no critical or serious accessibility violations in default state", async () => {
    const view = await renderWebhookManager();
    try {
      await flushEffects();

      const results = await axe(view.container);
      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  }, 15000);

  it("has no critical or serious accessibility violations when the create dialog is open", async () => {
    const view = await renderWebhookManager();
    try {
      await flushEffects();
      const createButton = Array.from(view.container.querySelectorAll("button")).find(
        (button) => button.textContent?.trim() === "Create webhook"
      );
      if (!(createButton instanceof HTMLButtonElement)) {
        throw new Error("Create webhook button was not rendered");
      }

      await click(createButton);
      await flushEffects();

      const results = await axe(view.container);
      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  }, 15000);
});
