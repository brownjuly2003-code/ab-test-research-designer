/**
 * Shared HTTP primitives for the frontend API client.
 * Domain modules import from here; consumers use `lib/api` facade.
 */

import { apiUrl, type ApiErrorResponse } from "../experiment";

const apiSessionTokenStorageKey = "ab-test-research-designer:api-token:v1";
const adminSessionTokenStorageKey = "ab-test-research-designer:admin-token:v1";
const llmProviderSessionStorageKey = "ab_llm_provider";
const llmTokenSessionStorageKey = "ab_llm_token";

export type LlmProvider = "local" | "openai" | "anthropic";
export type LlmSessionConfig = {
  provider: LlmProvider;
  token: string;
};

export type RequestOptions = {
  signal?: AbortSignal;
};

export type ApiAuthMode = "session" | "admin";

export type ApiJsonRequestOptions = {
  method?: string;
  /** Object/array is JSON.stringified; string body is sent as-is. */
  body?: unknown;
  headers?: Record<string, string>;
  auth?: ApiAuthMode;
  signal?: AbortSignal;
  errorFallback: string;
};

export type ApiBlobRequestOptions = {
  auth?: ApiAuthMode;
  headers?: Record<string, string>;
  errorFallback: string;
  fallbackFilename: string;
};

function readApiSessionToken(): string {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return "";
  }

  try {
    return String(storage.getItem(apiSessionTokenStorageKey) ?? "").trim();
  } catch {
    return "";
  }
}

function readAdminSessionToken(): string {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return "";
  }

  try {
    return String(storage.getItem(adminSessionTokenStorageKey) ?? "").trim();
  } catch {
    return "";
  }
}

function readLlmSessionProvider(): LlmProvider {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return "local";
  }

  try {
    const provider = String(storage.getItem(llmProviderSessionStorageKey) ?? "").trim().toLowerCase();
    return provider === "openai" || provider === "anthropic" ? provider : "local";
  } catch {
    return "local";
  }
}

function readLlmSessionToken(): string {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return "";
  }

  try {
    return String(storage.getItem(llmTokenSessionStorageKey) ?? "").trim();
  } catch {
    return "";
  }
}

export function getLlmSessionConfig(): LlmSessionConfig {
  return {
    provider: readLlmSessionProvider(),
    token: readLlmSessionToken()
  };
}

export function setLlmSessionProvider(provider: LlmProvider): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  if (provider === "local") {
    clearLlmSessionConfig();
    return;
  }

  storage.setItem(llmProviderSessionStorageKey, provider);
}

export function setLlmSessionToken(token: string): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  const normalized = token.trim();
  if (!normalized) {
    storage.removeItem(llmTokenSessionStorageKey);
    return;
  }

  storage.setItem(llmTokenSessionStorageKey, normalized);
}

export function clearLlmSessionConfig(): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  storage.removeItem(llmProviderSessionStorageKey);
  storage.removeItem(llmTokenSessionStorageKey);
}

export function hasApiSessionToken(): boolean {
  return readApiSessionToken().length > 0;
}

export function hasAdminSessionToken(): boolean {
  return readAdminSessionToken().length > 0;
}

export function setApiSessionToken(token: string): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  const normalized = token.trim();
  if (!normalized) {
    clearApiSessionToken();
    return;
  }

  storage.setItem(apiSessionTokenStorageKey, normalized);
}

export function clearApiSessionToken(): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  storage.removeItem(apiSessionTokenStorageKey);
}

export function setAdminSessionToken(token: string): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  const normalized = token.trim();
  if (!normalized) {
    clearAdminSessionToken();
    return;
  }

  storage.setItem(adminSessionTokenStorageKey, normalized);
}

export function clearAdminSessionToken(): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  storage.removeItem(adminSessionTokenStorageKey);
}

function currentLanguageHeader(): Record<string, string> {
  if (typeof document === "undefined") {
    return {};
  }
  const language = document.documentElement.lang?.trim();
  return language ? { "Accept-Language": language } : {};
}

function buildHeaders(
  additionalHeaders: Record<string, string> = {},
  token: string = readApiSessionToken()
): Record<string, string> {
  const headers = { ...currentLanguageHeader(), ...additionalHeaders };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function buildAdminHeaders(additionalHeaders: Record<string, string> = {}): Record<string, string> {
  return buildHeaders(additionalHeaders, readAdminSessionToken());
}

export function buildLlmHeaders(path: string): Record<string, string> {
  if (
    path !== "/api/v1/analyze" &&
    path !== "/api/v1/hypotheses/generate" &&
    !path.startsWith("/api/v1/llm/")
  ) {
    return {};
  }

  const config = getLlmSessionConfig();
  if ((config.provider === "openai" || config.provider === "anthropic") && config.token) {
    return {
      "X-AB-LLM-Provider": config.provider,
      "X-AB-LLM-Token": config.token
    };
  }

  return {};
}

async function readJson<T>(response: Response): Promise<T> {
  const data: T = await response.json();
  return data;
}

function getErrorMessage(payload: ApiErrorResponse, response: Response, fallback: string): string {
  const retryAfter = response.headers.get("Retry-After")?.trim();
  if (payload.error_code === "rate_limited" || payload.error_code === "auth_rate_limited") {
    const detail = typeof payload.detail === "string" && payload.detail.length > 0 ? payload.detail : "Too many requests";
    return retryAfter ? `${detail}. Retry after ${retryAfter}s.` : detail;
  }
  if (payload.error_code === "request_body_too_large") {
    if (typeof payload.detail === "string" && payload.detail.length > 0) {
      return `${payload.detail}. Reduce the payload size or raise the backend limit.`;
    }
    return "Request payload is too large for the current backend limit.";
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (typeof payload.error_code === "string" && payload.error_code.length > 0) {
    return `${fallback} (${payload.error_code})`;
  }
  return fallback;
}

/**
 * Shared typed JSON request primitive for the frontend API client.
 * All JSON endpoints go through here so auth headers, error parsing,
 * and response typing stay in one place (audit F-11).
 */
export async function apiJsonRequest<T>(path: string, options: ApiJsonRequestOptions): Promise<T> {
  const {
    method = "GET",
    body,
    headers: extraHeaders = {},
    auth = "session",
    signal,
    errorFallback
  } = options;

  const withContentType =
    body !== undefined && !("Content-Type" in extraHeaders)
      ? { "Content-Type": "application/json", ...extraHeaders }
      : extraHeaders;

  const headers =
    auth === "admin" ? buildAdminHeaders(withContentType) : buildHeaders(withContentType);

  const init: RequestInit = { method, headers, signal };
  if (body !== undefined) {
    init.body = typeof body === "string" ? body : JSON.stringify(body);
  }

  const response = await fetch(apiUrl(path), init);
  const data = await readJson<T & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, errorFallback));
  }

  return data;
}

/** Download endpoints that return a binary body + optional Content-Disposition filename. */
export async function apiBlobRequest(
  path: string,
  options: ApiBlobRequestOptions
): Promise<{ blob: Blob; filename: string }> {
  const { auth = "session", headers: extraHeaders = {}, errorFallback, fallbackFilename } = options;
  const headers =
    auth === "admin" ? buildAdminHeaders(extraHeaders) : buildHeaders(extraHeaders);

  const response = await fetch(apiUrl(path), { headers });

  if (!response.ok) {
    const data = await response.json().catch(() => ({} as ApiErrorResponse));
    throw new Error(getErrorMessage(data, response, errorFallback));
  }

  const blob = await response.blob();
  const filename =
    /filename=\"([^\"]+)\"/i.exec(response.headers.get("content-disposition") ?? "")?.[1] ??
    fallbackFilename;
  return { blob, filename };
}
