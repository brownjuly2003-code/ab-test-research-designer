// @vitest-environment jsdom

import { act } from "react";
import { describe, expect, it, vi } from "vitest";

import ToastSystem from "../components/ToastSystem";
import { renderIntoDocument, click, flushEffects } from "../test/dom";
import { useToast } from "./useToast";

function ToastHarness() {
  const { toasts, addToast, removeToast } = useToast();

  return (
    <>
      <button
        type="button"
        onClick={() => {
          addToast("success", "Project saved", 5000);
          addToast("error", "Analysis failed");
        }}
      >
        Add toasts
      </button>
      <ToastSystem toasts={toasts} onDismiss={removeToast} />
    </>
  );
}

describe("useToast", () => {
  it("stacks multiple toasts, auto-dismisses non-errors, and keeps errors persistent", async () => {
    vi.useFakeTimers();
    const view = await renderIntoDocument(<ToastHarness />);
    try {
      await flushEffects();

      const addToastButton = Array.from(view.container.querySelectorAll("button")).find(
        (button) => button.textContent?.trim() === "Add toasts"
      );
      if (!(addToastButton instanceof HTMLButtonElement)) {
        throw new Error("Add toasts button was not rendered");
      }

      await click(addToastButton);
      await flushEffects();

      let alerts = Array.from(document.body.querySelectorAll('[role="alert"]'));
      expect(alerts.some((alert) => alert.textContent?.includes("Project saved") ?? false)).toBe(true);
      expect(alerts.some((alert) => alert.textContent?.includes("Analysis failed") ?? false)).toBe(true);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      await flushEffects();

      alerts = Array.from(document.body.querySelectorAll('[role="alert"]'));
      expect(alerts.some((alert) => alert.textContent?.includes("Project saved") ?? false)).toBe(false);
      expect(alerts.some((alert) => alert.textContent?.includes("Analysis failed") ?? false)).toBe(true);

      const closeButton = Array.from(document.body.querySelectorAll("button")).find(
        (button) => button.getAttribute("aria-label") === "Dismiss toast"
      );
      if (!(closeButton instanceof HTMLButtonElement)) {
        throw new Error("Toast close button was not rendered");
      }

      await click(closeButton);
      await flushEffects();

      alerts = Array.from(document.body.querySelectorAll('[role="alert"]'));
      expect(alerts.some((alert) => alert.textContent?.includes("Analysis failed") ?? false)).toBe(false);
    } finally {
      vi.useRealTimers();
      await view.unmount();
    }
  });
});
