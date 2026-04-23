// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import "../../i18n";
import { changeValue, click, findButton, renderIntoDocument } from "../../test/dom";
import LlmProviderSettings from "./llm-provider";

describe("LLM provider settings", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("renders provider dropdown and password input", async () => {
    const view = await renderIntoDocument(<LlmProviderSettings />);
    try {
      expect(view.container.querySelector("#llm-provider-select")).toBeInstanceOf(HTMLSelectElement);
      expect(view.container.querySelector("#llm-provider-token")).toBeInstanceOf(HTMLInputElement);
      expect(view.container.textContent).toContain("Your key stays in browser session storage");
    } finally {
      await view.unmount();
    }
  });

  it("stores provider and token in sessionStorage on change", async () => {
    const view = await renderIntoDocument(<LlmProviderSettings />);
    try {
      const providerSelect = view.container.querySelector("#llm-provider-select");
      const tokenInput = view.container.querySelector("#llm-provider-token");
      if (!(providerSelect instanceof HTMLSelectElement) || !(tokenInput instanceof HTMLInputElement)) {
        throw new Error("LLM provider controls were not rendered");
      }

      await changeValue(providerSelect, "openai");
      await changeValue(tokenInput, "sk-session-token");

      expect(window.sessionStorage.getItem("ab_llm_provider")).toBe("openai");
      expect(window.sessionStorage.getItem("ab_llm_token")).toBe("sk-session-token");
    } finally {
      await view.unmount();
    }
  });

  it("clears sessionStorage when switching back to local mode", async () => {
    const view = await renderIntoDocument(<LlmProviderSettings />);
    try {
      const providerSelect = view.container.querySelector("#llm-provider-select");
      const tokenInput = view.container.querySelector("#llm-provider-token");
      if (!(providerSelect instanceof HTMLSelectElement) || !(tokenInput instanceof HTMLInputElement)) {
        throw new Error("LLM provider controls were not rendered");
      }

      await changeValue(providerSelect, "anthropic");
      await changeValue(tokenInput, "claude-session-token");
      await click(findButton(view.container, "Use local instead"));

      expect(window.sessionStorage.getItem("ab_llm_provider")).toBeNull();
      expect(window.sessionStorage.getItem("ab_llm_token")).toBeNull();
      expect(providerSelect.value).toBe("local");
      expect(tokenInput.value).toBe("");
    } finally {
      await view.unmount();
    }
  });

  it("shows a warning when a remote provider is selected without a token", async () => {
    const view = await renderIntoDocument(<LlmProviderSettings />);
    try {
      const providerSelect = view.container.querySelector("#llm-provider-select");
      if (!(providerSelect instanceof HTMLSelectElement)) {
        throw new Error("LLM provider select was not rendered");
      }

      await changeValue(providerSelect, "openai");

      expect(view.container.textContent).toContain("Token required - falling back to local suggestions");
    } finally {
      await view.unmount();
    }
  });
});
