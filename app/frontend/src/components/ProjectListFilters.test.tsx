// @vitest-environment jsdom

import "../i18n";

import { describe, expect, it, vi } from "vitest";

import ProjectListFilters from "./ProjectListFilters";
import { changeValue, renderIntoDocument } from "../test/dom";

describe("ProjectListFilters", () => {
  // Every metric family the backend can save must be filterable here. A count project was
  // savable long before this option existed, and the missing union member 400'd the whole
  // project list (audit F-04) — so the option list is asserted exactly, not loosely.
  it("offers every saved metric family as an option and reports the selection", async () => {
    const onMetricTypeChange = vi.fn();
    const view = await renderIntoDocument(
      <ProjectListFilters
        query=""
        status="active"
        metricType="all"
        sortBy="updated_desc"
        onQueryChange={() => {}}
        onStatusChange={() => {}}
        onMetricTypeChange={onMetricTypeChange}
        onSortByChange={() => {}}
        onClearFilters={() => {}}
      />
    );

    try {
      const select = view.container.querySelector("#saved-projects-metric-type");
      expect(select).not.toBeNull();
      const options = Array.from((select as HTMLSelectElement).options).map((option) => option.value);
      expect(options).toEqual(["all", "binary", "continuous", "ratio", "count"]);
      expect((select as HTMLSelectElement).textContent).toContain("Ratio");
      expect((select as HTMLSelectElement).textContent).toContain("Count");

      await changeValue(select as HTMLSelectElement, "ratio");
      expect(onMetricTypeChange).toHaveBeenCalledWith("ratio");

      await changeValue(select as HTMLSelectElement, "count");
      expect(onMetricTypeChange).toHaveBeenCalledWith("count");
    } finally {
      await view.unmount();
    }
  });
});
