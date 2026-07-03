// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OmnibusResultsSection, { parseGroups } from "../OmnibusResultsSection";
import i18n from "../../../i18n";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";

describe("parseGroups", () => {
  it("parses one group per line into numeric arrays", () => {
    expect(parseGroups("1 2 3\n4,5,6")).toEqual([
      [1, 2, 3],
      [4, 5, 6]
    ]);
  });

  it("rejects fewer than two groups or a group with fewer than two values", () => {
    expect(parseGroups("1 2 3")).toBeNull();
    expect(parseGroups("1 2\n3")).toBeNull();
    expect(parseGroups("1 x\n3 4")).toBeNull();
  });
});

describe("OmnibusResultsSection", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the omnibus form with a test selector", async () => {
    const view = await renderIntoDocument(<OmnibusResultsSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Multiple groups (omnibus)");
      expect(view.container.querySelector("select")).not.toBeNull();
      expect(view.container.querySelector("textarea")).not.toBeNull();
      expect(findButton(view.container, "Run omnibus test")).toBeTruthy();
    } finally {
      await view.unmount();
    }
  });

  it("posts the parsed groups and renders the Welch result with a per-group summary", async () => {
    const response = {
      test_type: "welch_anova",
      test_statistic: 20.6234,
      df_numerator: 2,
      df_denominator: 13.2251,
      p_value: 0.000086,
      is_significant: true,
      effect_size: 0.6578,
      effect_size_label: "eta squared (η²)",
      num_groups: 3,
      n_total: 24,
      group_summaries: [
        { n: 8, mean: 5.4375, std: 0.5069, median: null, mean_rank: null },
        { n: 9, mean: 6.9889, std: 0.4595, median: null, mean_rank: null },
        { n: 7, mean: 6.3, std: 0.5508, median: null, mean_rank: null }
      ],
      verdict: "At least one group differs at alpha=0.050",
      interpretation: "Welch's ANOVA F 20.6234 on 2 and 13.2251 degrees of freedom..."
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<OmnibusResultsSection />);
    try {
      await flushEffects();
      const textarea = view.container.querySelector("textarea") as HTMLTextAreaElement;
      await changeValue(textarea, "5.1 4.8 6.2 5.5\n6.5 7.1 6.8 7.4\n5.9 6.3 6.7 5.5");

      await click(findButton(view.container, "Run omnibus test"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(String(url)).toContain("/api/v1/results/omnibus");
      const body = JSON.parse(String(requestInit.body));
      expect(body.test_type).toBe("welch_anova");
      expect(body.groups).toHaveLength(3);
      expect(body.groups[0]).toHaveLength(4);
      expect(body.alpha).toBe(0.05);

      expect(view.container.textContent).toContain("At least one group differs");
      expect(view.container.textContent).toContain("eta squared");
      // per-group summary table rendered (mean column value)
      expect(view.container.querySelector("table")).not.toBeNull();
      expect(view.container.textContent).toContain("5.4375");
    } finally {
      await view.unmount();
    }
  });

  it("shows a parse hint and does not call the API for a single group", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<OmnibusResultsSection />);
    try {
      await flushEffects();
      const textarea = view.container.querySelector("textarea") as HTMLTextAreaElement;
      await changeValue(textarea, "1 2 3 4");

      await click(findButton(view.container, "Run omnibus test"));
      await flushEffects();

      expect(fetchMock).not.toHaveBeenCalled();
      expect(view.container.textContent).toContain("at least two groups");
    } finally {
      await view.unmount();
    }
  });
});
