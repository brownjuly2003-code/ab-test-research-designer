import { useTranslation } from "react-i18next";

import { useProjectStore } from "../../stores/projectStore";
import { formatOptionalTimestamp, formatRevisionSource } from "./formatters";

/**
 * Workspace-wide counters and label helpers derived from the saved-project list.
 * Both the Projects and the System tab read these.
 */
export function useProjectStats() {
  const { t } = useTranslation();
  const allSavedProjects = useProjectStore((state) => state.savedProjects);
  const backendDiagnostics = useProjectStore((state) => state.backendDiagnostics);

  const savedProjectsTotal = allSavedProjects.length;
  const archivedProjectsTotal = allSavedProjects.filter((project) => project.is_archived).length;
  const projectsWithSnapshots = allSavedProjects.filter((project) => project.has_analysis_snapshot).length;
  const projectsWithoutSnapshots = savedProjectsTotal - projectsWithSnapshots;
  const projectsWithExports = allSavedProjects.filter((project) => Boolean(project.last_exported_at)).length;
  const projectsWithMultipleRevisions = allSavedProjects.filter((project) => (project.revision_count ?? 0) > 1).length;
  const latestWorkspaceUpdate =
    backendDiagnostics?.storage.latest_project_updated_at ??
    (allSavedProjects[0]?.updated_at ?? null);

  const formatOptionalProjectTimestamp = (timestamp: string | null | undefined) =>
    formatOptionalTimestamp(timestamp, t("sidebarPanel.common.notRecordedYet"));

  const translateMetricType = (metricType: string | null | undefined) => {
    if (!metricType) {
      return t("sidebarPanel.common.unknownMetric");
    }
    if (metricType === "binary") {
      return t("projectListFilters.metricType.binary");
    }
    if (metricType === "continuous") {
      return t("projectListFilters.metricType.continuous");
    }
    if (metricType === "ratio") {
      return t("projectListFilters.metricType.ratio");
    }
    return metricType;
  };

  const translateRevisionSource = (source: string) =>
    formatRevisionSource(source, {
      importedWorkspaceSnapshot: t("sidebarPanel.revisions.sources.importedWorkspaceSnapshot"),
      projectUpdate: t("sidebarPanel.revisions.sources.projectUpdate"),
      initialSave: t("sidebarPanel.revisions.sources.initialSave")
    });

  return {
    savedProjectsTotal,
    archivedProjectsTotal,
    projectsWithSnapshots,
    projectsWithoutSnapshots,
    projectsWithExports,
    projectsWithMultipleRevisions,
    latestWorkspaceUpdate,
    formatOptionalProjectTimestamp,
    translateMetricType,
    translateRevisionSource
  };
}
