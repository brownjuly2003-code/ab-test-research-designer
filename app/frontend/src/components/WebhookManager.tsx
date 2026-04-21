import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import {
  createWebhookRequest,
  deleteWebhookRequest,
  listWebhookDeliveriesRequest,
  listWebhooksRequest,
  testWebhookRequest,
  type WebhookDeliveryRecord,
  type WebhookFormat,
  type WebhookScope,
  type WebhookSubscriptionRecord
} from "../lib/api";

function formatTimestamp(value: string | null | undefined, emptyLabel: string): string {
  if (!value) {
    return emptyLabel;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

function parseEventFilter(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function WebhookManager() {
  const { t } = useTranslation();
  const [subscriptions, setSubscriptions] = useState<WebhookSubscriptionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [deliveriesOpen, setDeliveriesOpen] = useState(false);
  const [deliveriesLoading, setDeliveriesLoading] = useState(false);
  const [deliveriesTitle, setDeliveriesTitle] = useState("");
  const [deliveries, setDeliveries] = useState<WebhookDeliveryRecord[]>([]);
  const [deliveriesError, setDeliveriesError] = useState("");
  const [name, setName] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [format, setFormat] = useState<WebhookFormat>("generic");
  const [eventFilter, setEventFilter] = useState("");
  const [scope, setScope] = useState<WebhookScope>("global");
  const [apiKeyId, setApiKeyId] = useState("");
  const dialogRef = useRef<HTMLDivElement | null>(null);

  async function loadSubscriptions() {
    try {
      setLoading(true);
      setError("");
      const response = await listWebhooksRequest();
      setSubscriptions(Array.isArray(response.subscriptions) ? response.subscriptions : []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("webhooks.status.loadFailed"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSubscriptions();
  }, []);

  useEffect(() => {
    if (!createOpen) {
      return;
    }

    const dialog = dialogRef.current;
    const queryFocusable = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"
        ) ?? []
      ).filter((element) => !element.hasAttribute("disabled"));

    const initialFocusable = queryFocusable()[0];
    initialFocusable?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setCreateOpen(false);
        return;
      }
      if (event.key !== "Tab") {
        return;
      }

      const focusable = queryFocusable();
      if (focusable.length === 0) {
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [createOpen]);

  function resetForm() {
    setName("");
    setTargetUrl("");
    setSecret("");
    setFormat("generic");
    setEventFilter("");
    setScope("global");
    setApiKeyId("");
  }

  async function onCreateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setError("");
    setStatusMessage("");

    try {
      const payload: {
        name: string;
        target_url: string;
        secret: string;
        format: WebhookFormat;
        event_filter: string[];
        scope: WebhookScope;
        api_key_id?: string;
      } = {
        name: name.trim(),
        target_url: targetUrl.trim(),
        secret: secret.trim(),
        format,
        event_filter: parseEventFilter(eventFilter),
        scope
      };
      if (scope === "api_key" && apiKeyId.trim()) {
        payload.api_key_id = apiKeyId.trim();
      }

      await createWebhookRequest(payload);
      setCreateOpen(false);
      resetForm();
      setStatusMessage(t("webhooks.status.created"));
      await loadSubscriptions();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : t("webhooks.status.createFailed"));
    } finally {
      setCreating(false);
    }
  }

  async function onTest(subscriptionId: string) {
    try {
      setActionId(subscriptionId);
      setError("");
      const response = await testWebhookRequest(subscriptionId);
      setStatusMessage(
        t("webhooks.status.testSuccess", {
          code: response.response_code ?? "n/a"
        })
      );
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : t("webhooks.status.testFailed"));
    } finally {
      setActionId(null);
    }
  }

  async function onOpenDeliveries(subscription: WebhookSubscriptionRecord) {
    try {
      setDeliveriesOpen(true);
      setDeliveriesLoading(true);
      setDeliveriesError("");
      setDeliveriesTitle(subscription.name);
      const response = await listWebhookDeliveriesRequest(subscription.id);
      setDeliveries(Array.isArray(response.deliveries) ? response.deliveries : []);
    } catch (deliveryError) {
      setDeliveries([]);
      setDeliveriesError(
        deliveryError instanceof Error ? deliveryError.message : t("webhooks.status.deliveriesFailed")
      );
    } finally {
      setDeliveriesLoading(false);
    }
  }

  async function onDelete(subscriptionId: string) {
    try {
      setActionId(subscriptionId);
      setError("");
      await deleteWebhookRequest(subscriptionId);
      setStatusMessage(t("webhooks.status.deleted"));
      if (deliveriesOpen) {
        setDeliveriesOpen(false);
      }
      await loadSubscriptions();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : t("webhooks.status.deleteFailed"));
    } finally {
      setActionId(null);
    }
  }

  return (
    <>
      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("webhooks.title")}</h3>
            <p className="muted">{t("webhooks.description")}</p>
          </div>
          <button
            className="btn secondary"
            type="button"
            onClick={() => {
              resetForm();
              setCreateOpen(true);
            }}
          >
            {t("webhooks.actions.create")}
          </button>
        </div>
        {statusMessage ? <div className="status">{statusMessage}</div> : null}
        {error ? <div className="status">{error}</div> : null}
        {loading ? (
          <p className="muted">{t("webhooks.loading")}</p>
        ) : subscriptions.length > 0 ? (
          <div style={{ display: "grid", gap: 12 }}>
            {subscriptions.map((subscription) => (
              <div
                key={subscription.id}
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 16,
                  padding: 16,
                  background: "var(--panel)"
                }}
              >
                <div className="section-heading">
                  <div>
                    <h4 style={{ margin: 0 }}>{subscription.name}</h4>
                    <p className="muted" style={{ margin: "6px 0 0" }}>
                      {subscription.format} | {subscription.scope}
                    </p>
                  </div>
                  <div className="actions">
                    <span className="pill">
                      {subscription.enabled ? t("webhooks.labels.enabled") : t("webhooks.labels.disabled")}
                    </span>
                    <span className="pill">{subscription.format}</span>
                  </div>
                </div>
                <ul className="list">
                  <li>
                    <strong>{t("webhooks.labels.targetUrl")}:</strong> <code>{subscription.target_url}</code>
                  </li>
                  <li>
                    <strong>{t("webhooks.labels.events")}:</strong>{" "}
                    {subscription.event_filter.length > 0
                      ? subscription.event_filter.join(", ")
                      : t("webhooks.labels.allEvents")}
                  </li>
                  {subscription.api_key_id ? (
                    <li>
                      <strong>{t("webhooks.labels.apiKeyId")}:</strong> <code>{subscription.api_key_id}</code>
                    </li>
                  ) : null}
                  <li>
                    <strong>{t("webhooks.labels.lastDelivered")}:</strong>{" "}
                    {formatTimestamp(subscription.last_delivered_at, t("webhooks.labels.never"))}
                  </li>
                  <li>
                    <strong>{t("webhooks.labels.lastError")}:</strong>{" "}
                    {formatTimestamp(subscription.last_error_at, t("webhooks.labels.never"))}
                  </li>
                </ul>
                <div className="actions">
                  <button
                    className="btn ghost"
                    type="button"
                    disabled={actionId === subscription.id}
                    onClick={() => void onTest(subscription.id)}
                  >
                    {t("webhooks.actions.test")}
                  </button>
                  <button
                    className="btn ghost"
                    type="button"
                    disabled={actionId === subscription.id}
                    onClick={() => void onOpenDeliveries(subscription)}
                  >
                    {t("webhooks.actions.deliveries")}
                  </button>
                  <button
                    className="btn ghost"
                    type="button"
                    disabled={actionId === subscription.id}
                    onClick={() => void onDelete(subscription.id)}
                  >
                    {t("webhooks.actions.delete")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">{t("webhooks.empty")}</p>
        )}
      </div>

      {createOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="webhook-create-title"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.45)",
            display: "grid",
            placeItems: "center",
            padding: 24,
            zIndex: 30
          }}
        >
          <div
            ref={dialogRef}
            className="card"
            style={{
              width: "min(100%, 560px)",
              maxHeight: "calc(100vh - 48px)",
              overflow: "auto"
            }}
          >
            <div className="section-heading">
              <div>
                <h3 id="webhook-create-title">{t("webhooks.createDialog.title")}</h3>
                <p className="muted">{t("webhooks.createDialog.description")}</p>
              </div>
              <button className="btn ghost" type="button" onClick={() => setCreateOpen(false)}>
                {t("webhooks.actions.close")}
              </button>
            </div>
            <form onSubmit={(event) => void onCreateSubmit(event)} style={{ display: "grid", gap: 16 }}>
              <div className="field">
                <label htmlFor="webhook-name">{t("webhooks.fields.name")}</label>
                <input
                  id="webhook-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder={t("webhooks.placeholders.name")}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="webhook-target-url">{t("webhooks.fields.targetUrl")}</label>
                <input
                  id="webhook-target-url"
                  value={targetUrl}
                  onChange={(event) => setTargetUrl(event.target.value)}
                  placeholder={t("webhooks.placeholders.targetUrl")}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="webhook-secret">{t("webhooks.fields.secret")}</label>
                <input
                  id="webhook-secret"
                  value={secret}
                  onChange={(event) => setSecret(event.target.value)}
                  placeholder={t("webhooks.placeholders.secret")}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="webhook-format">{t("webhooks.fields.format")}</label>
                <select
                  id="webhook-format"
                  value={format}
                  onChange={(event) => setFormat(event.target.value as WebhookFormat)}
                >
                  <option value="generic">{t("webhooks.formats.generic")}</option>
                  <option value="slack">{t("webhooks.formats.slack")}</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="webhook-scope">{t("webhooks.fields.scope")}</label>
                <select
                  id="webhook-scope"
                  value={scope}
                  onChange={(event) => setScope(event.target.value as WebhookScope)}
                >
                  <option value="global">{t("webhooks.scopes.global")}</option>
                  <option value="api_key">{t("webhooks.scopes.apiKey")}</option>
                </select>
              </div>
              {scope === "api_key" ? (
                <div className="field">
                  <label htmlFor="webhook-api-key-id">{t("webhooks.fields.apiKeyId")}</label>
                  <input
                    id="webhook-api-key-id"
                    value={apiKeyId}
                    onChange={(event) => setApiKeyId(event.target.value)}
                    placeholder={t("webhooks.placeholders.apiKeyId")}
                    required
                  />
                </div>
              ) : null}
              <div className="field">
                <label htmlFor="webhook-event-filter">{t("webhooks.fields.eventFilter")}</label>
                <input
                  id="webhook-event-filter"
                  value={eventFilter}
                  onChange={(event) => setEventFilter(event.target.value)}
                  placeholder={t("webhooks.placeholders.eventFilter")}
                />
              </div>
              <div className="actions">
                <button
                  className="btn secondary"
                  type="submit"
                  disabled={creating || name.trim().length === 0 || targetUrl.trim().length === 0 || secret.trim().length === 0}
                >
                  {creating ? t("webhooks.actions.saving") : t("webhooks.actions.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {deliveriesOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="webhook-deliveries-title"
          style={{
            position: "fixed",
            inset: "0 0 0 auto",
            width: "min(100%, 420px)",
            background: "var(--surface, #ffffff)",
            borderLeft: "1px solid var(--line)",
            boxShadow: "-18px 0 36px rgba(15, 23, 42, 0.14)",
            padding: 24,
            zIndex: 25,
            overflow: "auto"
          }}
        >
          <div className="section-heading">
            <div>
              <h3 id="webhook-deliveries-title">{t("webhooks.drawer.title", { name: deliveriesTitle })}</h3>
              <p className="muted">{t("webhooks.drawer.description")}</p>
            </div>
            <button className="btn ghost" type="button" onClick={() => setDeliveriesOpen(false)}>
              {t("webhooks.actions.close")}
            </button>
          </div>
          {deliveriesError ? <div className="status">{deliveriesError}</div> : null}
          {deliveriesLoading ? (
            <p className="muted">{t("webhooks.drawer.loading")}</p>
          ) : deliveries.length > 0 ? (
            <div style={{ display: "grid", gap: 12 }}>
              {deliveries.map((delivery) => (
                <div
                  key={delivery.id}
                  style={{
                    border: "1px solid var(--line)",
                    borderRadius: 16,
                    padding: 16,
                    background: "var(--panel)"
                  }}
                >
                  <div className="section-heading">
                    <strong>{delivery.id}</strong>
                    <span className="pill">{delivery.status}</span>
                  </div>
                  <ul className="list">
                    <li>
                      <strong>{t("webhooks.drawer.labels.responseCode")}:</strong> {String(delivery.response_code ?? "n/a")}
                    </li>
                    <li>
                      <strong>{t("webhooks.drawer.labels.attempts")}:</strong> {String(delivery.attempt_count)}
                    </li>
                    <li>
                      <strong>{t("webhooks.drawer.labels.lastAttempt")}:</strong>{" "}
                      {formatTimestamp(delivery.last_attempt_at, t("webhooks.labels.never"))}
                    </li>
                    {delivery.error_message ? (
                      <li>
                        <strong>{t("webhooks.drawer.labels.error")}:</strong> {delivery.error_message}
                      </li>
                    ) : null}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">{t("webhooks.drawer.empty")}</p>
          )}
        </div>
      ) : null}
    </>
  );
}
