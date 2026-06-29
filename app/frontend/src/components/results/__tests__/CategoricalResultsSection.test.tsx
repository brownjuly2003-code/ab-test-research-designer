// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CategoricalResultsSection, { cramersVMagnitude, parseContingencyTable } from "../CategoricalResultsSection";
import i18n from "../../../i18n";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";

describe("parseContingencyTable", () => {
  it("parses rows of comma- or space-separated counts", () => {
    expect(parseContingencyTable("30, 70\n50 50")).toEqual([
      [30, 70],
      [50, 50]
    ]);
  });

  it("rejects ragged rows, single columns, and non-integer or negative cells", () => {
    expect(parseContingencyTable("1 2 3\n4 5")).toBeNull(); // ragged
    expect(parseContingencyTable("1\n2")).toBeNull(); // single column
    expect(parseContingencyTable("1 2")).toBeNull(); // single row
    expect(parseContingencyTable("1 2\n3 -1")).toBeNull(); // negative
    expect(parseContingencyTable("1 2\n3 2.5")).toBeNull(); // non-integer
    expect(parseContingencyTable("")).toBeNull(); // empty
  });
});

describe("cramersVMagnitude", () => {
  it("classifies a 2x2 table by Cramér's V directly (min dimension 1)", () => {
    expect(cramersVMagnitude(0.05, 2, 2)).toBe("negligible");
    expect(cramersVMagnitude(0.2, 2, 2)).toBe("small");
    expect(cramersVMagnitude(0.4, 2, 2)).toBe("medium");
    expect(cramersVMagnitude(0.6, 2, 2)).toBe("large");
  });

  it("tightens the cut-offs as the table grows (w = V·√minDim)", () => {
    // df* = 2: small/medium boundary is 0.3/√2 ≈ 0.212
    expect(cramersVMagnitude(0.2, 3, 3)).toBe("small");
    expect(cramersVMagnitude(0.25, 3, 3)).toBe("medium");
  });
});

describe("CategoricalResultsSection", () => {
  beforeEach(async () => {
    // Deterministically load the default-language bundle before rendering so t() resolves keys
    // regardless of test-file run order (matches the i18n.test.tsx readiness pattern).
    await i18n.changeLanguage("en");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the contingency-table form", async () => {
    const view = await renderIntoDocument(<CategoricalResultsSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Categorical outcome (chi-square)");
      expect(view.container.textContent).toContain("Contingency table");
      expect(findButton(view.container, "Run chi-square test")).toBeTruthy();
    } finally {
      await view.unmount();
    }
  });

  it("posts the parsed table and renders the chi-square result", async () => {
    const response = {
      chi_square: 20.0,
      degrees_of_freedom: 2,
      p_value: 0.000045,
      is_significant: true,
      cramers_v: 0.4082,
      n_total: 120,
      num_rows: 2,
      num_cols: 3,
      min_expected_count: 20.0,
      low_expected_warning: false,
      verdict: "Association detected",
      interpretation: "Chi-square 20.0000 on 2 degrees of freedom..."
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<CategoricalResultsSection />);
    try {
      await flushEffects();
      const textarea = view.container.querySelector("textarea");
      expect(textarea).not.toBeNull();
      await changeValue(textarea as HTMLTextAreaElement, "10 20 30\n30 20 10");

      await click(findButton(view.container, "Run chi-square test"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(String(url)).toContain("/api/v1/results/categorical");
      const body = JSON.parse(String(requestInit.body));
      expect(body.table).toEqual([
        [10, 20, 30],
        [30, 20, 10]
      ]);
      expect(body.alpha).toBe(0.05);

      expect(view.container.textContent).toContain("Association detected");
      expect(view.container.textContent).toContain("20.0000");
      expect(view.container.textContent).toContain("0.4082");
      expect(view.container.textContent).toContain("2×3");
      // Cramér's V 0.4082 on a 2×3 table (min dimension 1) → w = 0.4082 → "medium".
      expect(view.container.textContent).toContain("medium");
    } finally {
      await view.unmount();
    }
  });

  it("shows a validation hint and does not call the API for a malformed table", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<CategoricalResultsSection />);
    try {
      await flushEffects();
      const textarea = view.container.querySelector("textarea");
      await changeValue(textarea as HTMLTextAreaElement, "1 2 3\n4 5");

      await click(findButton(view.container, "Run chi-square test"));
      await flushEffects();

      expect(fetchMock).not.toHaveBeenCalled();
      expect(view.container.textContent).toContain("Each row must contain");
    } finally {
      await view.unmount();
    }
  });
});
