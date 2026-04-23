import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

type LlmProvider = "local" | "openai" | "anthropic";

function readProvider(): LlmProvider {
  const provider = String(window.sessionStorage.getItem("ab_llm_provider") ?? "").trim().toLowerCase();
  return provider === "openai" || provider === "anthropic" ? provider : "local";
}

function readToken(): string {
  return String(window.sessionStorage.getItem("ab_llm_token") ?? "").trim();
}

function clearStoredConfig() {
  window.sessionStorage.removeItem("ab_llm_provider");
  window.sessionStorage.removeItem("ab_llm_token");
}

export default function LlmProviderSettings() {
  const { t } = useTranslation();
  const [provider, setProvider] = useState<LlmProvider>(readProvider);
  const [token, setToken] = useState(readToken);

  useEffect(() => {
    function handleBeforeUnload() {
      clearStoredConfig();
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  function handleProviderChange(nextProvider: LlmProvider) {
    if (nextProvider === "local") {
      clearStoredConfig();
      setProvider("local");
      setToken("");
      return;
    }

    window.sessionStorage.setItem("ab_llm_provider", nextProvider);
    setProvider(nextProvider);
  }

  function handleTokenChange(nextToken: string) {
    setToken(nextToken);
    const normalized = nextToken.trim();
    if (!normalized) {
      window.sessionStorage.removeItem("ab_llm_token");
      return;
    }
    window.sessionStorage.setItem("ab_llm_token", normalized);
  }

  function handleUseLocalInstead() {
    clearStoredConfig();
    setProvider("local");
    setToken("");
  }

  const showWarning = provider !== "local" && token.trim().length === 0;

  return (
    <div className="card">
      <div className="section-heading">
        <div>
          <h3>{t("app.preferences.llm.title")}</h3>
          <p className="muted">{t("app.preferences.llm.description")}</p>
        </div>
      </div>
      <div className="field">
        <label htmlFor="llm-provider-select">{t("app.preferences.llm.providerLabel")}</label>
        <select
          id="llm-provider-select"
          value={provider}
          onChange={(event) => handleProviderChange(event.target.value as LlmProvider)}
        >
          <option value="local">{t("app.preferences.llm.providers.local")}</option>
          <option value="openai">{t("app.preferences.llm.providers.openai")}</option>
          <option value="anthropic">{t("app.preferences.llm.providers.anthropic")}</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="llm-provider-token">{t("app.preferences.llm.tokenLabel")}</label>
        <input
          id="llm-provider-token"
          type="password"
          value={token}
          disabled={provider === "local"}
          onChange={(event) => handleTokenChange(event.target.value)}
        />
      </div>
      <p className="muted">{t("app.preferences.llm.info")}</p>
      <div className="actions">
        <button
          className="btn ghost"
          type="button"
          disabled={provider === "local" && token.trim().length === 0}
          onClick={handleUseLocalInstead}
        >
          {t("app.preferences.llm.useLocal")}
        </button>
      </div>
      {showWarning ? <div className="status">{t("app.preferences.llm.tokenRequiredFallback")}</div> : null}
    </div>
  );
}
