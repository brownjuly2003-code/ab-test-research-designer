// @vitest-environment jsdom

import { describe, expect, it } from "vitest";

import Icon from "./Icon";
import { renderIntoDocument } from "../test/dom";

describe("Icon", () => {
  it("renders Lucide icons with a consistent stroke width", async () => {
    const view = await renderIntoDocument(<Icon name="check" className="icon icon-inline" />);

    try {
      const svg = view.container.querySelector("svg");

      expect(svg).not.toBeNull();
      expect(svg?.getAttribute("class")).toContain("lucide-check");
      expect(svg?.getAttribute("stroke-width")).toBe("1.5");
      expect(svg?.getAttribute("class")).toContain("icon icon-inline");
      expect(svg?.getAttribute("aria-hidden")).toBe("true");
    } finally {
      await view.unmount();
    }
  });
});
