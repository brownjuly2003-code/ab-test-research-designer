import { memo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { isAdminMode } from "../lib/adminMode";
import ApiKeysTab from "./sidebar/ApiKeysTab";
import ProjectsTab from "./sidebar/ProjectsTab";
import styles from "./SidebarPanel.module.css";
import SystemTab from "./sidebar/SystemTab";
import type { SidebarTab } from "./sidebar/types";
import { useAdminToken } from "./sidebar/useAdminToken";
import { useAuditLog } from "./sidebar/useAuditLog";
import { useProjectFilters } from "./sidebar/useProjectFilters";
import { useSidebarActions } from "./sidebar/useSidebarActions";

/**
 * Shell for the operator sidebar: owns the tab selection, the hidden workspace-import
 * file input, and the state that outlives a tab switch. Every tab pulls what it needs
 * from the stores itself, so nothing here is prop-drilled.
 */
const SidebarPanel = memo(function SidebarPanel() {
  const { t } = useTranslation();
  const workspaceImportRef = useRef<HTMLInputElement | null>(null);
  const [activeTab, setActiveTab] = useState<SidebarTab>("projects");
  const [isAdmin] = useState(isAdminMode);
  const { handleWorkspaceImport } = useSidebarActions();
  const adminToken = useAdminToken(activeTab, setActiveTab);
  const auditLog = useAuditLog(activeTab);
  const filters = useProjectFilters();

  // The file input lives here, so the click that opens it has to be triggered from here too:
  // a ref created inside a tab would point at a different (unmounted) input.
  function onImportWorkspace() {
    workspaceImportRef.current?.click();
  }

  return (
    <aside className={`panel ${styles.sidebar}`}>
      <input
        ref={workspaceImportRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        aria-label={t("wizardPanel.aria.importWorkspaceFile")}
        onChange={handleWorkspaceImport}
      />
      {isAdmin ? (
      <div
        style={{
          display: "inline-flex",
          gap: 8,
          padding: 6,
          borderRadius: 999,
          background: "var(--color-surface-elevated)",
          border: "1px solid var(--line)",
          alignSelf: "flex-start"
        }}
      >
        <button
          type="button"
          className="btn"
          style={{
            background: activeTab === "projects" ? "var(--color-secondary)" : "transparent",
            color: activeTab === "projects" ? "#ffffff" : "var(--muted)",
            boxShadow: activeTab === "projects" ? "0 6px 16px var(--color-primary-ring)" : "none"
          }}
          onClick={() => setActiveTab("projects")}
        >
          {t("sidebarPanel.tabs.projects")}
        </button>
        <button
          type="button"
          className="btn"
          style={{
            background: activeTab === "system" ? "var(--color-secondary)" : "transparent",
            color: activeTab === "system" ? "#ffffff" : "var(--muted)",
            boxShadow: activeTab === "system" ? "0 6px 16px var(--color-primary-ring)" : "none"
          }}
          onClick={() => setActiveTab("system")}
        >
          {t("sidebarPanel.tabs.system")}
        </button>
        {adminToken.configured ? (
          <button
            type="button"
            className="btn"
            style={{
              background: activeTab === "apiKeys" ? "var(--color-secondary)" : "transparent",
              color: activeTab === "apiKeys" ? "#ffffff" : "var(--muted)",
              boxShadow: activeTab === "apiKeys" ? "0 6px 16px var(--color-primary-ring)" : "none"
            }}
            onClick={() => setActiveTab("apiKeys")}
          >
            {t("sidebarPanel.tabs.apiKeys")}
          </button>
        ) : null}
      </div>
      ) : null}

      {activeTab === "apiKeys" ? (
        <ApiKeysTab />
      ) : activeTab === "system" ? (
        <SystemTab auditLog={auditLog} adminToken={adminToken} onImportWorkspace={onImportWorkspace} />
      ) : (
        <ProjectsTab filters={filters} isAdmin={isAdmin} onImportWorkspace={onImportWorkspace} />
      )}
    </aside>
  );
});

export default SidebarPanel;
