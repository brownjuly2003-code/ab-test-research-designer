// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    createApiKeyRequest: vi.fn(),
    deleteApiKeyRequest: vi.fn(),
    listApiKeysRequest: vi.fn(),
    revokeApiKeyRequest: vi.fn()
  };
});

import ApiKeyManager from "./ApiKeyManager";
import {
  createApiKeyRequest,
  listApiKeysRequest,
  revokeApiKeyRequest
} from "../lib/api";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../test/dom";

describe("ApiKeyManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the existing key list", async () => {
    vi.mocked(listApiKeysRequest).mockResolvedValue({
      keys: [
        {
          id: "key-1",
          name: "Partner read key",
          scope: "read",
          created_at: "2026-04-21T07:00:00Z",
          last_used_at: null,
          revoked_at: null,
          rate_limit_requests: null,
          rate_limit_window_seconds: null
        }
      ],
      total: 1
    });

    const view = await renderIntoDocument(<ApiKeyManager />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Partner read key");
      expect(view.container.textContent).toContain("Scope read");
      expect(view.container.textContent).toContain("Global default");
    } finally {
      await view.unmount();
    }
  });

  it("creates a new key and reveals the plaintext value once", async () => {
    vi.mocked(listApiKeysRequest)
      .mockResolvedValueOnce({ keys: [], total: 0 })
      .mockResolvedValueOnce({
        keys: [
          {
            id: "key-2",
            name: "Partner write key",
            scope: "write",
            created_at: "2026-04-21T08:00:00Z",
            last_used_at: null,
            revoked_at: null,
            rate_limit_requests: 25,
            rate_limit_window_seconds: 60
          }
        ],
        total: 1
      });
    vi.mocked(createApiKeyRequest).mockResolvedValue({
      id: "key-2",
      name: "Partner write key",
      scope: "write",
      created_at: "2026-04-21T08:00:00Z",
      last_used_at: null,
      revoked_at: null,
      rate_limit_requests: 25,
      rate_limit_window_seconds: 60,
      plaintext_key: "abk_secret_value"
    });

    const view = await renderIntoDocument(<ApiKeyManager />);
    try {
      await flushEffects();

      await click(findButton(view.container, "Create new"));
      await flushEffects();

      const nameInput = view.container.querySelector("#api-key-name");
      const scopeSelect = view.container.querySelector("#api-key-scope");
      const requestsInput = view.container.querySelector("#api-key-rate-limit-requests");
      const windowInput = view.container.querySelector("#api-key-rate-limit-window");

      if (!(nameInput instanceof HTMLInputElement)) {
        throw new Error("Name input was not rendered");
      }
      if (!(scopeSelect instanceof HTMLSelectElement)) {
        throw new Error("Scope select was not rendered");
      }
      if (!(requestsInput instanceof HTMLInputElement)) {
        throw new Error("Rate limit requests input was not rendered");
      }
      if (!(windowInput instanceof HTMLInputElement)) {
        throw new Error("Rate limit window input was not rendered");
      }

      await changeValue(nameInput, "Partner write key");
      await changeValue(scopeSelect, "write");
      await changeValue(requestsInput, "25");
      await changeValue(windowInput, "60");
      await click(findButton(view.container, "Create key"));
      await flushEffects();
      await flushEffects();

      expect(createApiKeyRequest).toHaveBeenCalledWith({
        name: "Partner write key",
        scope: "write",
        rate_limit_requests: 25,
        rate_limit_window_seconds: 60
      });
      expect(view.container.textContent).toContain("This secret is shown only once");
      expect(view.container.textContent).toContain("abk_secret_value");
      expect(view.container.textContent).toContain("Partner write key");
    } finally {
      await view.unmount();
    }
  });

  it("revokes an active key and refreshes the list", async () => {
    vi.mocked(listApiKeysRequest)
      .mockResolvedValueOnce({
        keys: [
          {
            id: "key-3",
            name: "Partner admin key",
            scope: "admin",
            created_at: "2026-04-21T08:00:00Z",
            last_used_at: "2026-04-21T08:10:00Z",
            revoked_at: null,
            rate_limit_requests: null,
            rate_limit_window_seconds: null
          }
        ],
        total: 1
      })
      .mockResolvedValueOnce({
        keys: [
          {
            id: "key-3",
            name: "Partner admin key",
            scope: "admin",
            created_at: "2026-04-21T08:00:00Z",
            last_used_at: "2026-04-21T08:10:00Z",
            revoked_at: "2026-04-21T08:20:00Z",
            rate_limit_requests: null,
            rate_limit_window_seconds: null
          }
        ],
        total: 1
      });
    vi.mocked(revokeApiKeyRequest).mockResolvedValue({
      id: "key-3",
      name: "Partner admin key",
      scope: "admin",
      created_at: "2026-04-21T08:00:00Z",
      last_used_at: "2026-04-21T08:10:00Z",
      revoked_at: "2026-04-21T08:20:00Z",
      rate_limit_requests: null,
      rate_limit_window_seconds: null
    });

    const view = await renderIntoDocument(<ApiKeyManager />);
    try {
      await flushEffects();

      await click(findButton(view.container, "Revoke"));
      await flushEffects();
      await flushEffects();

      expect(revokeApiKeyRequest).toHaveBeenCalledWith("key-3");
      expect(view.container.textContent).toContain("Revoked");
      expect(view.container.textContent).toContain("Delete");
    } finally {
      await view.unmount();
    }
  });
});
