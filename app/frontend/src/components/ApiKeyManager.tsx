import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import "../i18n";
import {
  createApiKeyRequest,
  deleteApiKeyRequest,
  listApiKeysRequest,
  revokeApiKeyRequest,
  type ApiKeyCreateResponse,
  type ApiKeyRecord
} from "../lib/api";
import { formatLocalizedTimestamp } from "../lib/formatDate";
import InlineConfirmButton from "./InlineConfirmButton";

function formatTimestamp(value: string | null | undefined, emptyLabel: string): string {
  if (!value) {
    return emptyLabel;
  }

  return formatLocalizedTimestamp(value);
}

export default function ApiKeyManager() {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [actionKeyId, setActionKeyId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"read" | "write">("read");
  const [rateLimitRequests, setRateLimitRequests] = useState("");
  const [rateLimitWindowSeconds, setRateLimitWindowSeconds] = useState("");
  const [latestCreated, setLatestCreated] = useState<ApiKeyCreateResponse | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const openButtonRef = useRef<HTMLButtonElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  async function loadKeys() {
    try {
      setLoading(true);
      setError("");
      const response = await listApiKeysRequest();
      setKeys(Array.isArray(response.keys) ? response.keys : []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("apiKeys.status.loadFailed"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadKeys();
  }, []);

  useEffect(() => {
    if (!createOpen) {
      return;
    }

    restoreFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : openButtonRef.current;

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
      restoreFocusRef.current?.focus();
    };
  }, [createOpen]);

  async function onCreateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setError("");
    setCopyStatus("");

    try {
      const created = await createApiKeyRequest({
        name: name.trim(),
        scope,
        rate_limit_requests: rateLimitRequests.trim() ? Number(rateLimitRequests) : undefined,
        rate_limit_window_seconds: rateLimitWindowSeconds.trim()
          ? Number(rateLimitWindowSeconds)
          : undefined
      });
      setLatestCreated(created);
      setCreateOpen(false);
      setName("");
      setScope("read");
      setRateLimitRequests("");
      setRateLimitWindowSeconds("");
      await loadKeys();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : t("apiKeys.status.createFailed"));
    } finally {
      setCreating(false);
    }
  }

  async function onRevoke(apiKeyId: string) {
    try {
      setActionKeyId(apiKeyId);
      setError("");
      await revokeApiKeyRequest(apiKeyId);
      await loadKeys();
    } catch (revokeError) {
      setError(revokeError instanceof Error ? revokeError.message : t("apiKeys.status.revokeFailed"));
    } finally {
      setActionKeyId(null);
    }
  }

  async function onDelete(apiKeyId: string) {
    try {
      setActionKeyId(apiKeyId);
      setError("");
      await deleteApiKeyRequest(apiKeyId);
      await loadKeys();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : t("apiKeys.status.deleteFailed"));
    } finally {
      setActionKeyId(null);
    }
  }

  async function copyPlaintextKey() {
    if (!latestCreated?.plaintext_key || !navigator.clipboard?.writeText) {
      setCopyStatus(t("apiKeys.status.clipboardUnavailable"));
      return;
    }

    try {
      await navigator.clipboard.writeText(latestCreated.plaintext_key);
      setCopyStatus(t("apiKeys.status.copied"));
    } catch {
      setCopyStatus(t("apiKeys.status.copyFailed"));
    }
  }

  const notUsedYet = t("apiKeys.labels.notUsedYet");

  return (
    <>
      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("apiKeys.title")}</h3>
            <p className="muted">{t("apiKeys.description")}</p>
          </div>
          <button
            ref={openButtonRef}
            className="btn secondary"
            type="button"
            onClick={() => setCreateOpen(true)}
          >
            {t("apiKeys.actions.createNew")}
          </button>
        </div>
        {error ? <div className="status">{error}</div> : null}
        {loading ? (
          <p className="muted">{t("apiKeys.loading")}</p>
        ) : keys.length > 0 ? (
          <div style={{ display: "grid", gap: 12 }}>
            {keys.map((key) => (
              <div
                key={key.id}
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 16,
                  padding: 16,
                  background: "var(--panel)"
                }}
              >
                <div className="section-heading">
                  <div>
                    <h4 style={{ margin: 0 }}>{key.name}</h4>
                    <p className="muted" style={{ margin: "6px 0 0" }}>
                      {t("apiKeys.labels.scopeCreated", {
                        scope: t(`apiKeys.scopes.${key.scope}`),
                        created: formatTimestamp(key.created_at, notUsedYet)
                      })}
                    </p>
                  </div>
                  <div className="actions">
                    <span className="pill">{t(`apiKeys.scopes.${key.scope}`)}</span>
                    {key.revoked_at ? (
                      <span className="pill">{t("apiKeys.labels.revoked")}</span>
                    ) : (
                      <span className="pill">{t("apiKeys.labels.active")}</span>
                    )}
                  </div>
                </div>
                <ul className="list">
                  <li>
                    <strong>{t("apiKeys.labels.id")}:</strong> <code>{key.id}</code>
                  </li>
                  <li>
                    <strong>{t("apiKeys.labels.lastUsed")}:</strong>{" "}
                    {formatTimestamp(key.last_used_at, notUsedYet)}
                  </li>
                  <li>
                    <strong>{t("apiKeys.labels.rateLimitOverride")}:</strong>{" "}
                    {key.rate_limit_requests && key.rate_limit_window_seconds
                      ? t("apiKeys.labels.rateLimitValue", {
                          requests: String(key.rate_limit_requests),
                          seconds: String(key.rate_limit_window_seconds)
                        })
                      : t("apiKeys.labels.globalDefault")}
                  </li>
                  {key.revoked_at ? (
                    <li>
                      <strong>{t("apiKeys.labels.revokedAt")}:</strong>{" "}
                      {formatTimestamp(key.revoked_at, notUsedYet)}
                    </li>
                  ) : null}
                </ul>
                <div className="actions">
                  {!key.revoked_at ? (
                    <button
                      className="btn ghost"
                      type="button"
                      disabled={actionKeyId === key.id}
                      onClick={() => void onRevoke(key.id)}
                    >
                      {actionKeyId === key.id
                        ? t("apiKeys.actions.revoking")
                        : t("apiKeys.actions.revoke")}
                    </button>
                  ) : (
                    <InlineConfirmButton
                      label={
                        actionKeyId === key.id
                          ? t("apiKeys.actions.deleting")
                          : t("apiKeys.actions.delete")
                      }
                      disabled={actionKeyId === key.id}
                      onConfirm={() => void onDelete(key.id)}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">{t("apiKeys.empty")}</p>
        )}
      </div>

      {latestCreated ? (
        <div className="card">
          <h3>{t("apiKeys.plaintext.title")}</h3>
          <p className="muted">{t("apiKeys.plaintext.warning")}</p>
          <div
            style={{
              border: "1px solid rgba(217, 119, 6, 0.25)",
              background: "rgba(254, 243, 199, 0.55)",
              borderRadius: 16,
              padding: 16,
              display: "grid",
              gap: 12
            }}
          >
            <code style={{ wordBreak: "break-all" }}>{latestCreated.plaintext_key}</code>
            <div className="actions">
              <button className="btn secondary" type="button" onClick={() => void copyPlaintextKey()}>
                {t("apiKeys.actions.copyKey")}
              </button>
            </div>
            {copyStatus ? <div className="status">{copyStatus}</div> : null}
          </div>
        </div>
      ) : null}

      {createOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="api-key-create-title"
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
              width: "min(100%, 520px)",
              maxHeight: "calc(100vh - 48px)",
              overflow: "auto"
            }}
          >
            <div className="section-heading">
              <div>
                <h3 id="api-key-create-title">{t("apiKeys.createDialog.title")}</h3>
                <p className="muted">{t("apiKeys.createDialog.description")}</p>
              </div>
              <button className="btn ghost" type="button" onClick={() => setCreateOpen(false)}>
                {t("apiKeys.actions.close")}
              </button>
            </div>
            <form onSubmit={(event) => void onCreateSubmit(event)} style={{ display: "grid", gap: 16 }}>
              <div className="field">
                <label htmlFor="api-key-name">{t("apiKeys.fields.name")}</label>
                <input
                  id="api-key-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder={t("apiKeys.placeholders.name")}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="api-key-scope">{t("apiKeys.fields.scope")}</label>
                <select
                  id="api-key-scope"
                  value={scope}
                  onChange={(event) => setScope(event.target.value as "read" | "write")}
                >
                  <option value="read">{t("apiKeys.scopes.read")}</option>
                  <option value="write">{t("apiKeys.scopes.write")}</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="api-key-rate-limit-requests">
                  {t("apiKeys.fields.rateLimitRequests")}
                </label>
                <input
                  id="api-key-rate-limit-requests"
                  type="number"
                  min="1"
                  value={rateLimitRequests}
                  onChange={(event) => setRateLimitRequests(event.target.value)}
                  placeholder={t("apiKeys.placeholders.rateLimitDefault")}
                />
              </div>
              <div className="field">
                <label htmlFor="api-key-rate-limit-window">
                  {t("apiKeys.fields.rateLimitWindow")}
                </label>
                <input
                  id="api-key-rate-limit-window"
                  type="number"
                  min="1"
                  value={rateLimitWindowSeconds}
                  onChange={(event) => setRateLimitWindowSeconds(event.target.value)}
                  placeholder={t("apiKeys.placeholders.rateLimitDefault")}
                />
              </div>
              <div className="actions">
                <button className="btn secondary" type="submit" disabled={creating || name.trim().length === 0}>
                  {creating ? t("apiKeys.actions.creating") : t("apiKeys.actions.createKey")}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
