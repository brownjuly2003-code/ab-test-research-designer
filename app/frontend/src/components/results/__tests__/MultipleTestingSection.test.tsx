// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

import MultipleTestingSection from "../MultipleTestingSection";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";

describe("MultipleTestingSection", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the correction form with the run button disabled until a metric is entered", async () => {
    const view = await renderIntoDocument(<MultipleTestingSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Correct for testing many metrics");
      expect(findButton(view.container, "Apply correction").disabled).toBe(true);
    } finally {
      await view.unmount();
    }
  });

  it("posts the battery and renders the decision table", async () => {
    const response = {
      method: "bh",
      level: 0.05,
      num_tests: 2,
      num_rejected: 1,
      threshold_rank: 1,
      critical_value: 0.001,
      results: [
        { label: "Checkout", p_value: 0.001, adjusted_p_value: 0.002, rejected: true },
        { label: "Bounce", p_value: 0.6, adjusted_p_value: 0.6, rejected: false }
      ]
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<MultipleTestingSection />);
    try {
      await flushEffects();
      const labelInputs = view.container.querySelectorAll<HTMLInputElement>('input[type="text"]');
      const numberInputs = view.container.querySelectorAll<HTMLInputElement>('input[type="number"]');
      await changeValue(labelInputs[0], "Checkout");
      await changeValue(numberInputs[0], "0.001");

      const runButton = findButton(view.container, "Apply correction");
      expect(runButton.disabled).toBe(false);

      await click(runButton);
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(String(requestInit.body));
      expect(body.metrics).toEqual([{ label: "Checkout", p_value: 0.001 }]);
      expect(body.method).toBe("bh");

      expect(view.container.textContent).toContain("1 of 2 metrics");
      expect(view.container.textContent).toContain("Checkout");
      expect(view.container.textContent).toContain("Significant");
    } finally {
      await view.unmount();
    }
  });
});
