import type { RefObject } from "react";

import { t } from "../i18n";

type ChartExportMenuProps = {
  chartRef: RefObject<HTMLDivElement | null>;
  filenameBase: string;
};

function resolveChartDimensions(svg: SVGSVGElement): { width: number; height: number } {
  const viewBox = svg.viewBox.baseVal;
  const width = Number(svg.getAttribute("width")) || viewBox?.width || svg.clientWidth || 640;
  const height = Number(svg.getAttribute("height")) || viewBox?.height || svg.clientHeight || 360;
  return {
    width,
    height
  };
}

function serializeChartSvg(svg: SVGSVGElement): string {
  if (!svg.getAttribute("xmlns")) {
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  }
  if (!svg.getAttribute("xmlns:xlink")) {
    svg.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  }
  return new XMLSerializer().serializeToString(svg);
}

function triggerDownload(href: string, filename: string) {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
}

export function slugifyChartFilename(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return normalized || "chart";
}

export function downloadChartSvg(svg: SVGSVGElement, filenameBase: string) {
  const blob = new Blob([serializeChartSvg(svg)], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  triggerDownload(url, `${filenameBase}.svg`);
  URL.revokeObjectURL(url);
}

export async function downloadChartPng(svg: SVGSVGElement, filenameBase: string) {
  const { width, height } = resolveChartDimensions(svg);
  const blob = new Blob([serializeChartSvg(svg)], { type: "image/svg+xml;charset=utf-8" });
  const svgUrl = URL.createObjectURL(blob);
  const image = new Image();

  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error(t("chartExport.errors.imageRenderFailed")));
    image.src = svgUrl;
  });

  const canvas = document.createElement("canvas");
  canvas.width = width * 2;
  canvas.height = height * 2;
  const context = canvas.getContext("2d");
  if (!context) {
    URL.revokeObjectURL(svgUrl);
    throw new Error(t("chartExport.errors.canvasUnavailable"));
  }
  context.scale(2, 2);
  context.drawImage(image, 0, 0, width, height);
  triggerDownload(canvas.toDataURL("image/png"), `${filenameBase}.png`);
  URL.revokeObjectURL(svgUrl);
}

export default function ChartExportMenu({ chartRef, filenameBase }: ChartExportMenuProps) {
  async function exportChart(format: "svg" | "png") {
    const svg = chartRef.current?.querySelector("svg");
    if (!(svg instanceof SVGSVGElement)) {
      return;
    }

    if (format === "svg") {
      downloadChartSvg(svg, filenameBase);
      return;
    }

    await downloadChartPng(svg, filenameBase);
  }

  return (
    <div
      className="actions"
      role="group"
      aria-label={t("chartExport.groupAriaLabel")}
      style={{ justifyContent: "flex-end", marginBottom: "12px" }}
    >
      <button
        type="button"
        className="btn ghost"
        aria-label={t("chartExport.downloadSvgAriaLabel")}
        onClick={() => void exportChart("svg")}
      >
        {t("chartExport.svg")}
      </button>
      <button
        type="button"
        className="btn ghost"
        aria-label={t("chartExport.downloadPngAriaLabel")}
        onClick={() => void exportChart("png")}
      >
        {t("chartExport.png")}
      </button>
    </div>
  );
}
