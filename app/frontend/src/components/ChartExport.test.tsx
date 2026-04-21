// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadChartPng, downloadChartSvg } from "./ChartExport";

function buildSvg(width = "320", height = "180") {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const rect = document.createElementNS(namespace, "rect");
  rect.setAttribute("width", width);
  rect.setAttribute("height", height);
  rect.setAttribute("fill", "#0d9488");
  svg.append(rect);
  return svg;
}

describe("ChartExport", () => {
  beforeEach(() => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:chart"),
      revokeObjectURL: vi.fn()
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("creates an SVG blob download from a chart element", () => {
    const svg = buildSvg();

    downloadChartSvg(svg, "power-curve");

    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  });

  it("renders a 2x PNG export through canvas", async () => {
    const svg = buildSvg("200", "100");
    const drawImage = vi.fn();
    const scale = vi.fn();
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage,
      scale
    } as unknown as CanvasRenderingContext2D);
    const toDataUrl = vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,abc");

    class MockImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        this.onload?.();
      }
    }

    vi.stubGlobal("Image", MockImage);

    await downloadChartPng(svg, "power-curve");

    expect(getContext).toHaveBeenCalled();
    expect(scale).toHaveBeenCalledWith(2, 2);
    expect(drawImage).toHaveBeenCalled();
    expect(toDataUrl).toHaveBeenCalledWith("image/png");
  });
});
