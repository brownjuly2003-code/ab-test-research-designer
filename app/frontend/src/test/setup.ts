import ar from "../../public/locales/ar.json";
import de from "../../public/locales/de.json";
import en from "../../public/locales/en.json";
import es from "../../public/locales/es.json";
import fr from "../../public/locales/fr.json";
import ru from "../../public/locales/ru.json";
import zh from "../../public/locales/zh.json";

import { vi } from "vitest";

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
