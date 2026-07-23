import ar from "../../public/locales/ar.json";
import de from "../../public/locales/de.json";
import en from "../../public/locales/en.json";
import es from "../../public/locales/es.json";
import fr from "../../public/locales/fr.json";
import ru from "../../public/locales/ru.json";
import zh from "../../public/locales/zh.json";

import { vi } from "vitest";

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (!("ResizeObserver" in globalThis)) {
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserver }).ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver;
}

// Stable Canvas stub for jsdom: silences repeated "Not implemented: getContext"
// noise from chart/a11y suites. Tests may still spyOn these prototype methods.
if (typeof HTMLCanvasElement !== "undefined") {
  const twoDContextStub = {
    canvas: null as HTMLCanvasElement | null,
    fillRect: () => undefined,
    clearRect: () => undefined,
    getImageData: () => ({ data: new Uint8ClampedArray(0), width: 0, height: 0 }),
    putImageData: () => undefined,
    createImageData: () => ({ data: new Uint8ClampedArray(0), width: 0, height: 0 }),
    setTransform: () => undefined,
    resetTransform: () => undefined,
    drawImage: () => undefined,
    save: () => undefined,
    restore: () => undefined,
    beginPath: () => undefined,
    moveTo: () => undefined,
    lineTo: () => undefined,
    closePath: () => undefined,
    stroke: () => undefined,
    translate: () => undefined,
    scale: () => undefined,
    rotate: () => undefined,
    arc: () => undefined,
    fill: () => undefined,
    fillText: () => undefined,
    strokeText: () => undefined,
    measureText: () => ({ width: 0 }),
    transform: () => undefined,
    rect: () => undefined,
    clip: () => undefined
  };

  HTMLCanvasElement.prototype.getContext = function getContext(
    this: HTMLCanvasElement,
    contextId: string,
    _options?: unknown
  ): RenderingContext | null {
    if (contextId === "2d") {
      twoDContextStub.canvas = this;
      return twoDContextStub as unknown as CanvasRenderingContext2D;
    }
    return null;
  } as typeof HTMLCanvasElement.prototype.getContext;

  HTMLCanvasElement.prototype.toDataURL = function toDataURL(): string {
    return "data:image/png;base64,";
  };
}

const localePayloads: Record<string, unknown> = {
  ar,
  de,
  en,
  es,
  fr,
  ru,
  zh
};
const originalFetch = globalThis.fetch;

vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
  const requestUrl =
    input instanceof Request
      ? input.url
      : input instanceof URL
        ? input.toString()
        : input;
  const pathname = requestUrl.startsWith("http")
    ? new URL(requestUrl).pathname
    : requestUrl;
  const localeName = pathname.match(/^\/locales\/([a-z]+)\.json$/)?.[1];

  if (localeName) {
    const payload = localePayloads[localeName];

    if (!payload) {
      return new Response("Not found", { status: 404 });
    }

    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: {
        "Content-Type": "application/json"
      }
    });
  }

  if (!originalFetch) {
    throw new Error(`Unhandled fetch in tests: ${requestUrl}`);
  }

  return originalFetch(input, init);
});
