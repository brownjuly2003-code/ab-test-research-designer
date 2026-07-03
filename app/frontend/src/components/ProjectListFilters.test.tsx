// @vitest-environment jsdom

import "../i18n";

import { describe, expect, it, vi } from "vitest";

import ProjectListFilters from "./ProjectListFilters";
import { changeValue, renderIntoDocument } from "../test/dom";

describe("ProjectListFilters", () => {
  it("offers a Ratio metric-type option and reports its selection", async () => {
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
      expect(options).toEqual(["all", "binary", "continuous", "ratio"]);
      expect((select as HTMLSelectElement).textContent).toContain("Ratio");

      await changeValue(select as HTMLSelectElement, "ratio");

      expect(onMetricTypeChange).toHaveBeenCalledWith("ratio");
    } finally {
      await view.unmount();
    }
  });
});
