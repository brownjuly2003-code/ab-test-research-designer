/**
 * Operator API-key client (`/api/v1/keys*`). Requires admin session token.
 * DTO types come from the OpenAPI-generated contract (audit F-08 / plan step 8).
 */

import type {
  ApiKeyCreateRequest,
  ApiKeyCreateResponse,
  ApiKeyDeleteResponse,
  ApiKeyListResponse,
  ApiKeyRecord
} from "../generated/api-contract";
import { apiJsonRequest } from "./client";

export type {
  ApiKeyCreateRequest,
  ApiKeyCreateResponse,
  ApiKeyDeleteResponse,
  ApiKeyListResponse,
  ApiKeyRecord
};

/** Issued key scopes only — matches generated `ApiKeyRecord.scope`. */
export type ApiKeyScope = ApiKeyRecord["scope"];

export async function listApiKeysRequest(): Promise<ApiKeyListResponse> {
  return apiJsonRequest<ApiKeyListResponse>("/api/v1/keys", {
    auth: "admin",
    errorFallback: "API key list request failed"
  });
}

export async function createApiKeyRequest(payload: ApiKeyCreateRequest): Promise<ApiKeyCreateResponse> {
  return apiJsonRequest<ApiKeyCreateResponse>("/api/v1/keys", {
    method: "POST",
    body: payload,
    auth: "admin",
    errorFallback: "API key creation failed"
  });
}

export async function revokeApiKeyRequest(apiKeyId: string): Promise<ApiKeyRecord> {
  return apiJsonRequest<ApiKeyRecord>(`/api/v1/keys/${apiKeyId}/revoke`, {
    method: "POST",
    auth: "admin",
    errorFallback: "API key revoke failed"
  });
}

export async function deleteApiKeyRequest(apiKeyId: string): Promise<ApiKeyDeleteResponse> {
  return apiJsonRequest<ApiKeyDeleteResponse>(`/api/v1/keys/${apiKeyId}`, {
    method: "DELETE",
    auth: "admin",
    errorFallback: "API key delete failed"
  });
}
