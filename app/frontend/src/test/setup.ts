import ar from "../../public/locales/ar.json";
import de from "../../public/locales/de.json";
import en from "../../public/locales/en.json";
import es from "../../public/locales/es.json";
import fr from "../../public/locales/fr.json";
import ru from "../../public/locales/ru.json";
import zh from "../../public/locales/zh.json";

import { vi } from "vitest";

// Node 26 ships experimental Web Storage: `localStorage`/`sessionStorage` exist on
// globalThis but evaluate to undefined unless node gets --localstorage-file, and their
// mere presence stops vitest's jsdom environment from installing jsdom's working
// implementation (existing globals are preserved). Replace only the broken accessor
// with an in-memory Storage; on runtimes where storage already works this is a no-op.
class MemoryStorage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

for (const storageKey of ["localStorage", "sessionStorage"] as const) {
  const isBroken = (() => {
    if (!Object.getOwnPropertyDescriptor(globalThis, storageKey)) {
      return false;
    }
    try {
      return (globalThis as Record<string, unknown>)[storageKey] == null;
    } catch {
      return true;
    }
  })();

  if (isBroken) {
    Object.defineProperty(globalThis, storageKey, {
      configurable: true,
      value: new MemoryStorage()
    });
  }
}

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (!("ResizeObserver" in globalThis)) {
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserver }).ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver;
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
