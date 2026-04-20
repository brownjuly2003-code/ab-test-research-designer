// @vitest-environment jsdom

import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { click, flushEffects, renderIntoDocument } from "../test/dom";
import ErrorBoundary from "./ErrorBoundary";

function Thrower({ shouldThrow, children }: { shouldThrow: boolean; children?: ReactNode }) {
  if (shouldThrow) {
    throw new Error("boom");
  }

  return <>{children ?? <div>safe</div>}</>;
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children when nothing throws", async () => {
    const view = await renderIntoDocument(
      <ErrorBoundary>
        <div>safe child</div>
      </ErrorBoundary>
    );
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("safe child");
      expect(view.container.textContent).not.toContain("Something went wrong");
    } finally {
      await view.unmount();
    }
  });

  it("shows fallback ui and calls onError when a child throws", async () => {
    const onError = vi.fn();

    const view = await renderIntoDocument(
      <ErrorBoundary onError={onError}>
        <Thrower shouldThrow={true} />
      </ErrorBoundary>
    );
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Something went wrong");
      expect(view.container.textContent).toContain("Retry");
      expect(onError).toHaveBeenCalledTimes(1);
      expect(onError.mock.calls[0]?.[0]).toBeInstanceOf(Error);
    } finally {
      await view.unmount();
    }
  });

  it("retries rendering after a transient failure", async () => {
    let shouldThrow = true;

    function TransientThrower() {
      if (shouldThrow) {
        throw new Error("transient");
      }

      return <div>recovered child</div>;
    }

    const view = await renderIntoDocument(
      <ErrorBoundary>
        <TransientThrower />
      </ErrorBoundary>
    );
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Something went wrong");

      const retryButton = Array.from(view.container.querySelectorAll("button")).find(
        (button) => button.textContent?.trim() === "Retry"
      );
      if (!(retryButton instanceof HTMLButtonElement)) {
        throw new Error("Retry button was not rendered");
      }

      shouldThrow = false;
      await click(retryButton);
      await flushEffects();

      expect(view.container.textContent).toContain("recovered child");
      expect(view.container.textContent).not.toContain("Something went wrong");
    } finally {
      await view.unmount();
    }
  });
});
