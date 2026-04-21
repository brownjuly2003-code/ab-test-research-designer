// @vitest-environment jsdom

import { act } from "react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    createWebhookRequest: vi.fn(),
    deleteWebhookRequest: vi.fn(),
    listWebhookDeliveriesRequest: vi.fn(),
    listWebhooksRequest: vi.fn(),
    testWebhookRequest: vi.fn()
  };
});

import WebhookManager from "./WebhookManager";
import i18n from "../i18n";
import {
  createWebhookRequest,
  deleteWebhookRequest,
  listWebhookDeliveriesRequest,
  listWebhooksRequest,
  testWebhookRequest
} from "../lib/api";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../test/dom";

describe("WebhookManager", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    window.localStorage.clear();
    await i18n.changeLanguage("en");
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

  it("renders existing subscriptions", async () => {
    vi.mocked(listWebhooksRequest).mockResolvedValue({
      subscriptions: [
        {
          id: "hook-1",
          name: "Partner alerts",
          target_url: "https://example.com/webhook",
          secret: null,
          format: "generic",
          event_filter: ["api_key_created"],
          scope: "global",
          api_key_id: null,
          created_at: "2026-04-21T08:00:00Z",
          updated_at: "2026-04-21T08:00:00Z",
          last_delivered_at: null,
          last_error_at: null,
          enabled: true
        }
      ],
      total: 1
    });

    const view = await renderWebhookManager();
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Partner alerts");
      expect(view.container.textContent).toContain("generic");
      expect(view.container.textContent).toContain("api_key_created");
    } finally {
      await view.unmount();
    }
  });

  it("creates a subscription from the modal and closes on Escape", async () => {
    vi.mocked(listWebhooksRequest)
      .mockResolvedValueOnce({ subscriptions: [], total: 0 })
      .mockResolvedValueOnce({
        subscriptions: [
          {
            id: "hook-2",
            name: "Slack alerts",
            target_url: "https://hooks.slack.com/services/test",
            secret: null,
            format: "slack",
            event_filter: ["project.archive"],
            scope: "global",
            api_key_id: null,
            created_at: "2026-04-21T09:00:00Z",
            updated_at: "2026-04-21T09:00:00Z",
            last_delivered_at: null,
            last_error_at: null,
            enabled: true
          }
        ],
        total: 1
      });
    vi.mocked(createWebhookRequest).mockResolvedValue({
      id: "hook-2",
      name: "Slack alerts",
      target_url: "https://hooks.slack.com/services/test",
      secret: "hook-secret",
      format: "slack",
      event_filter: ["project.archive"],
      scope: "global",
      api_key_id: null,
      created_at: "2026-04-21T09:00:00Z",
      updated_at: "2026-04-21T09:00:00Z",
      last_delivered_at: null,
      last_error_at: null,
      enabled: true
    });

    const view = await renderWebhookManager();
    try {
      await flushEffects();

      await click(findButton(view.container, "Create webhook"));
      await flushEffects();

      const dialog = view.container.querySelector('[role="dialog"]');
      expect(dialog).not.toBeNull();

      const nameInput = view.container.querySelector("#webhook-name");
      const targetUrlInput = view.container.querySelector("#webhook-target-url");
      const secretInput = view.container.querySelector("#webhook-secret");
      const formatSelect = view.container.querySelector("#webhook-format");
      const eventFilterInput = view.container.querySelector("#webhook-event-filter");

      if (!(nameInput instanceof HTMLInputElement)) {
        throw new Error("Name input was not rendered");
      }
      if (!(targetUrlInput instanceof HTMLInputElement)) {
        throw new Error("Target URL input was not rendered");
      }
      if (!(secretInput instanceof HTMLInputElement)) {
        throw new Error("Secret input was not rendered");
      }
      if (!(formatSelect instanceof HTMLSelectElement)) {
        throw new Error("Format select was not rendered");
      }
      if (!(eventFilterInput instanceof HTMLInputElement)) {
        throw new Error("Event filter input was not rendered");
      }

      await changeValue(nameInput, "Slack alerts");
      await changeValue(targetUrlInput, "https://hooks.slack.com/services/test");
      await changeValue(secretInput, "hook-secret");
      await changeValue(formatSelect, "slack");
      await changeValue(eventFilterInput, "project.archive");
      await click(findButton(view.container, "Save webhook"));
      await flushEffects();
      await flushEffects();

      expect(createWebhookRequest).toHaveBeenCalledWith({
        name: "Slack alerts",
        target_url: "https://hooks.slack.com/services/test",
        secret: "hook-secret",
        format: "slack",
        event_filter: ["project.archive"],
        scope: "global"
      });
      expect(view.container.textContent).toContain("Slack alerts");

      await click(findButton(view.container, "Create webhook"));
      await flushEffects();

      await act(async () => {
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      });
      await flushEffects();

      expect(view.container.querySelector('[role="dialog"]')).toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("tests, opens deliveries, and deletes a subscription", async () => {
    vi.mocked(listWebhooksRequest)
      .mockResolvedValueOnce({
        subscriptions: [
          {
            id: "hook-3",
            name: "Partner alerts",
            target_url: "https://example.com/webhook",
            secret: null,
            format: "generic",
            event_filter: ["api_key_created"],
            scope: "global",
            api_key_id: null,
            created_at: "2026-04-21T08:00:00Z",
            updated_at: "2026-04-21T08:00:00Z",
            last_delivered_at: null,
            last_error_at: null,
            enabled: true
          }
        ],
        total: 1
      })
      .mockResolvedValueOnce({ subscriptions: [], total: 0 });
    vi.mocked(testWebhookRequest).mockResolvedValue({
      delivery_id: "delivery-1",
      status: "delivered",
      response_code: 200
    });
    vi.mocked(listWebhookDeliveriesRequest).mockResolvedValue({
      deliveries: [
        {
          id: "delivery-1",
          subscription_id: "hook-3",
          event_id: 99,
          status: "delivered",
          attempt_count: 1,
          last_attempt_at: "2026-04-21T08:30:00Z",
          delivered_at: "2026-04-21T08:30:00Z",
          response_code: 200,
          response_body: "{\"ok\":true}",
          error_message: null
        }
      ],
      total: 1
    });
    vi.mocked(deleteWebhookRequest).mockResolvedValue({
      id: "hook-3",
      deleted: true
    });

    const view = await renderWebhookManager();
    try {
      await flushEffects();

      await click(findButton(view.container, "Test"));
      await flushEffects();
      expect(testWebhookRequest).toHaveBeenCalledWith("hook-3");
      expect(view.container.textContent).toContain("200");

      await click(findButton(view.container, "Deliveries"));
      await flushEffects();
      await flushEffects();
      expect(listWebhookDeliveriesRequest).toHaveBeenCalledWith("hook-3");
      expect(view.container.textContent).toContain("delivery-1");
      expect(view.container.textContent).toContain("delivered");

      await click(findButton(view.container, "Delete"));
      await flushEffects();
      await flushEffects();

      expect(deleteWebhookRequest).toHaveBeenCalledWith("hook-3");
      expect(view.container.textContent).toContain("No webhook subscriptions yet.");
    } finally {
      await view.unmount();
    }
  });
});
