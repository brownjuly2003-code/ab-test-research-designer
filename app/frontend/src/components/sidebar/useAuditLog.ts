import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { exportAuditLogRequest, listAuditLogRequest } from "../../lib/api";
import type { AuditLogEntry } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { downloadBlob } from "./formatters";
import type { SidebarTab } from "./types";

/**
 * Audit-log window for the System tab. Kept in the shell so the chosen project filter and
 * the already-fetched page survive a trip to another tab, exactly as before the split.
 */
export function useAuditLog(activeTab: SidebarTab) {
  const { t } = useTranslation();
  const showStatus = useAnalysisStore((state) => state.showStatus);
  const showError = useAnalysisStore((state) => state.showError);

  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [projectId, setProjectId] = useState("");

  async function loadAuditLog(filterProjectId: string) {
    try {
      setLoading(true);
      setError("");
      const response = await listAuditLogRequest(filterProjectId ? { projectId: filterProjectId } : {});
      setEntries(response.entries);
      setTotal(response.total);
    } catch (caught) {
      setEntries([]);
      setTotal(0);
      setError(caught instanceof Error ? caught.message : t("sidebarPanel.auditLog.unavailable"));
    } finally {
      setLoading(false);
    }
  }

  async function onExport() {
    try {
      const { blob, filename } = await exportAuditLogRequest(projectId ? { projectId } : {});
      downloadBlob(blob, filename);
      showStatus(t("sidebarPanel.status.auditExported"), "success");
    } catch (caught) {
      showError(caught instanceof Error ? caught.message : t("sidebarPanel.status.auditExportFailed"), "error");
    }
  }

  useEffect(() => {
    if (activeTab !== "system") {
      return;
    }
    void loadAuditLog(projectId);
  }, [activeTab, projectId]);

  return {
    entries,
    total,
    loading,
    error,
    projectId,
    setProjectId,
    reload: () => void loadAuditLog(projectId),
    onExport
  };
}

export type AuditLog = ReturnType<typeof useAuditLog>;
