import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";

import { slackInstallUrl } from "../../lib/api";
import { useSlackStatus } from "./useSlackStatus";

const ApiKeyManager = lazy(() => import("../ApiKeyManager"));
const WebhookManager = lazy(() => import("../WebhookManager"));

export default function ApiKeysTab() {
  const { t } = useTranslation();
  const { status: slackStatus, error: slackStatusError, loading: slackStatusLoading } = useSlackStatus();

  return (
    <Suspense
      fallback={
        <div className="card">
          <h3>{t("sidebarPanel.apiKeysFallback.title")}</h3>
          <p className="muted">{t("sidebarPanel.apiKeysFallback.loading")}</p>
        </div>
      }
    >
      <ApiKeyManager />
      <div className="card" data-testid="slack-app-tile">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.slackApp.title")}</h3>
            <p className="muted">{t("sidebarPanel.slackApp.description")}</p>
          </div>
          <span className="pill">
            {slackStatusLoading
              ? t("sidebarPanel.slackApp.checking")
              : slackStatus?.installed
                ? t("sidebarPanel.slackApp.installed")
                : t("sidebarPanel.slackApp.notInstalled")}
          </span>
        </div>
        {slackStatusError ? <div className="status">{slackStatusError}</div> : null}
        {slackStatus?.installed ? (
          <p className="muted">
            {t("sidebarPanel.slackApp.installedWorkspace", {
              workspace: slackStatus.team_name || slackStatus.team_id || t("sidebarPanel.slackApp.unknownWorkspace")
            })}
          </p>
        ) : (
          <p className="muted">
            {slackStatus?.configured === false
              ? t("sidebarPanel.slackApp.notConfigured")
              : t("sidebarPanel.slackApp.readyToInstall")}
          </p>
        )}
        <div className="actions">
          <button
            className="btn secondary"
            type="button"
            disabled={slackStatus?.configured === false}
            onClick={() => {
              window.location.assign(slackInstallUrl());
            }}
          >
            {slackStatus?.installed
              ? t("sidebarPanel.slackApp.reinstall")
              : t("sidebarPanel.slackApp.install")}
          </button>
        </div>
      </div>
      <WebhookManager />
    </Suspense>
  );
}
