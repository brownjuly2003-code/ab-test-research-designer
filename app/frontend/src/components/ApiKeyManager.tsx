import { useEffect, useState, type FormEvent } from "react";

import {
  createApiKeyRequest,
  deleteApiKeyRequest,
  listApiKeysRequest,
  revokeApiKeyRequest,
  type ApiKeyCreateResponse,
  type ApiKeyRecord
} from "../lib/api";

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Not used yet";
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

export default function ApiKeyManager() {
  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [actionKeyId, setActionKeyId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"read" | "write" | "admin">("read");
  const [rateLimitRequests, setRateLimitRequests] = useState("");
  const [rateLimitWindowSeconds, setRateLimitWindowSeconds] = useState("");
  const [latestCreated, setLatestCreated] = useState<ApiKeyCreateResponse | null>(null);
  const [copyStatus, setCopyStatus] = useState("");

  async function loadKeys() {
    try {
      setLoading(true);
      setError("");
      const response = await listApiKeysRequest();
      setKeys(Array.isArray(response.keys) ? response.keys : []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "API key list unavailable.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadKeys();
  }, []);

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
        rate_limit_window_seconds: rateLimitWindowSeconds.trim() ? Number(rateLimitWindowSeconds) : undefined
      });
      setLatestCreated(created);
      setCreateOpen(false);
      setName("");
      setScope("read");
      setRateLimitRequests("");
      setRateLimitWindowSeconds("");
      await loadKeys();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "API key creation failed.");
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
      setError(revokeError instanceof Error ? revokeError.message : "API key revoke failed.");
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
      setError(deleteError instanceof Error ? deleteError.message : "API key delete failed.");
    } finally {
      setActionKeyId(null);
    }
  }

  async function copyPlaintextKey() {
    if (!latestCreated?.plaintext_key || !navigator.clipboard?.writeText) {
      setCopyStatus("Clipboard access unavailable.");
      return;
    }

    try {
      await navigator.clipboard.writeText(latestCreated.plaintext_key);
      setCopyStatus("Copied to clipboard.");
    } catch {
      setCopyStatus("Copy failed.");
    }
  }

  return (
    <>
      <div className="card">
        <div className="section-heading">
          <div>
            <h3>API keys</h3>
            <p className="muted">
              Create scoped keys for external consumers, revoke them when needed, and keep per-key rate limits isolated.
            </p>
          </div>
          <button className="btn secondary" type="button" onClick={() => setCreateOpen(true)}>
            Create new
          </button>
        </div>
        {error ? <div className="status">{error}</div> : null}
        {loading ? (
          <p className="muted">Loading API keys...</p>
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
                      Scope {key.scope} | Created {formatTimestamp(key.created_at)}
                    </p>
                  </div>
                  <div className="actions">
                    <span className="pill">{key.scope}</span>
                    {key.revoked_at ? <span className="pill">Revoked</span> : <span className="pill">Active</span>}
                  </div>
                </div>
                <ul className="list">
                  <li>
                    <strong>ID:</strong> <code>{key.id}</code>
                  </li>
                  <li>
                    <strong>Last used:</strong> {formatTimestamp(key.last_used_at)}
                  </li>
                  <li>
                    <strong>Rate limit override:</strong>{" "}
                    {key.rate_limit_requests && key.rate_limit_window_seconds
                      ? `${String(key.rate_limit_requests)} req / ${String(key.rate_limit_window_seconds)}s`
                      : "Global default"}
                  </li>
                  {key.revoked_at ? (
                    <li>
                      <strong>Revoked at:</strong> {formatTimestamp(key.revoked_at)}
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
                      {actionKeyId === key.id ? "Revoking..." : "Revoke"}
                    </button>
                  ) : (
                    <button
                      className="btn ghost"
                      type="button"
                      disabled={actionKeyId === key.id}
                      onClick={() => void onDelete(key.id)}
                    >
                      {actionKeyId === key.id ? "Deleting..." : "Delete"}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No API keys have been created yet.</p>
        )}
      </div>

      {latestCreated ? (
        <div className="card">
          <h3>Plaintext key</h3>
          <p className="muted">This secret is shown only once. Store it securely before leaving the page.</p>
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
                Copy key
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
            className="card"
            style={{
              width: "min(100%, 520px)",
              maxHeight: "calc(100vh - 48px)",
              overflow: "auto"
            }}
          >
            <div className="section-heading">
              <div>
                <h3 id="api-key-create-title">Create API key</h3>
                <p className="muted">Set a label, scope, and optional rate limit override.</p>
              </div>
              <button className="btn ghost" type="button" onClick={() => setCreateOpen(false)}>
                Close
              </button>
            </div>
            <form onSubmit={(event) => void onCreateSubmit(event)} style={{ display: "grid", gap: 16 }}>
              <div className="field">
                <label htmlFor="api-key-name">Name</label>
                <input
                  id="api-key-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Partner analytics"
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="api-key-scope">Scope</label>
                <select id="api-key-scope" value={scope} onChange={(event) => setScope(event.target.value as "read" | "write" | "admin")}>
                  <option value="read">Read</option>
                  <option value="write">Write</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="api-key-rate-limit-requests">Rate limit requests</label>
                <input
                  id="api-key-rate-limit-requests"
                  type="number"
                  min="1"
                  value={rateLimitRequests}
                  onChange={(event) => setRateLimitRequests(event.target.value)}
                  placeholder="Leave blank for global default"
                />
              </div>
              <div className="field">
                <label htmlFor="api-key-rate-limit-window">Rate limit window seconds</label>
                <input
                  id="api-key-rate-limit-window"
                  type="number"
                  min="1"
                  value={rateLimitWindowSeconds}
                  onChange={(event) => setRateLimitWindowSeconds(event.target.value)}
                  placeholder="Leave blank for global default"
                />
              </div>
              <div className="actions">
                <button className="btn secondary" type="submit" disabled={creating || name.trim().length === 0}>
                  {creating ? "Creating..." : "Create key"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
