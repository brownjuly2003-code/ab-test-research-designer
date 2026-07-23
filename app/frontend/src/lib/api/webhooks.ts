/**
 * Operator webhook client (`/api/v1/webhooks*`). Requires admin session token.
 * DTO types come from the OpenAPI-generated contract (audit F-08 / plan step 8).
 */

import { apiUrl } from "../experiment";
import type {
  WebhookDeleteResponse,
  WebhookDeliveryListResponse,
  WebhookDeliveryRecord,
  WebhookListResponse,
  WebhookSubscriptionCreateRequest,
  WebhookSubscriptionRecord,
  WebhookTestResponse
} from "../generated/api-contract";
import { apiJsonRequest } from "./client";

export type {
  WebhookDeleteResponse,
  WebhookDeliveryListResponse,
  WebhookDeliveryRecord,
  WebhookListResponse,
  WebhookSubscriptionRecord,
  WebhookTestResponse
};

/** Stable alias used by UI forms — same shape as generated create request. */
export type WebhookCreateRequest = WebhookSubscriptionCreateRequest;

export type WebhookFormat = NonNullable<WebhookSubscriptionRecord["format"]>;
export type WebhookScope = NonNullable<WebhookSubscriptionRecord["scope"]>;
export type WebhookDeliveryStatus = WebhookDeliveryRecord["status"];

export type SlackStatusResponse = {
  configured: boolean;
  installed: boolean;
  team_id?: string | null;
  team_name?: string | null;
  installed_at?: string | null;
};

export async function listWebhooksRequest(): Promise<WebhookListResponse> {
  return apiJsonRequest<WebhookListResponse>("/api/v1/webhooks", {
    auth: "admin",
    errorFallback: "Webhook list request failed"
  });
}

export async function requestSlackStatus(): Promise<SlackStatusResponse> {
  return apiJsonRequest<SlackStatusResponse>("/api/v1/slack/status", {
    errorFallback: "Slack status request failed"
  });
}

export function slackInstallUrl(): string {
  return apiUrl("/slack/install");
}

export async function createWebhookRequest(
  payload: WebhookCreateRequest
): Promise<WebhookSubscriptionRecord> {
  return apiJsonRequest<WebhookSubscriptionRecord>("/api/v1/webhooks", {
    method: "POST",
    body: payload,
    auth: "admin",
    errorFallback: "Webhook creation failed"
  });
}

export async function deleteWebhookRequest(subscriptionId: string): Promise<WebhookDeleteResponse> {
  return apiJsonRequest<WebhookDeleteResponse>(`/api/v1/webhooks/${subscriptionId}`, {
    method: "DELETE",
    auth: "admin",
    errorFallback: "Webhook deletion failed"
  });
}

export async function testWebhookRequest(subscriptionId: string): Promise<WebhookTestResponse> {
  return apiJsonRequest<WebhookTestResponse>(`/api/v1/webhooks/${subscriptionId}/test`, {
    method: "POST",
    auth: "admin",
    errorFallback: "Webhook test delivery failed"
  });
}

export async function listWebhookDeliveriesRequest(
  subscriptionId: string,
  options: { limit?: number; status?: WebhookDeliveryStatus } = {}
): Promise<WebhookDeliveryListResponse> {
  const params = new URLSearchParams();
  if (typeof options.limit === "number") {
    params.set("limit", String(options.limit));
  }
  if (options.status) {
    params.set("status", options.status);
  }

  const path =
    params.size > 0
      ? `/api/v1/webhooks/${subscriptionId}/deliveries?${params.toString()}`
      : `/api/v1/webhooks/${subscriptionId}/deliveries`;
  return apiJsonRequest<WebhookDeliveryListResponse>(path, {
    auth: "admin",
    errorFallback: "Webhook delivery history failed"
  });
}
