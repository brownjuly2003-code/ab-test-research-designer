import { useTranslation } from "react-i18next";

import { useProjectStore } from "../../stores/projectStore";
import InlineConfirmButton from "../InlineConfirmButton";
import ProjectListFilters from "../ProjectListFilters";
import ProjectListSkeleton from "../ProjectListSkeleton";
import styles from "../SidebarPanel.module.css";
import { formatProjectTimestamp } from "./formatters";
import type { ProjectFilters } from "./useProjectFilters";
import { useProjectStats } from "./useProjectStats";
import { useSidebarActions } from "./useSidebarActions";

type ProjectsTabProps = {
  filters: ProjectFilters;
  isAdmin: boolean;
  onImportWorkspace: () => void;
};

export default function ProjectsTab({ filters, isAdmin, onImportWorkspace }: ProjectsTabProps) {
  const { t } = useTranslation();
  const {
    loadingProjects,
    importingWorkspace,
    exportingWorkspace,
    deletingProjectId,
    restoringProjectId,
    savedProjects: allSavedProjects,
    archivedProjects,
    activeProjectId,
    activeProject,
    projectHistory,
    projectRevisions,
    projectHistoryError,
    projectRevisionsError,
    loadingProjectHistory,
    loadingProjectRevisions,
    selectedHistoryRunId,
    projectComparison,
    projectMultiComparison,
    projectComparisonError,
    loadingProjectComparison,
    comparingProjectId,
    hasUnsavedChanges,
    canMutateBackend
  } = useProjectStore();
  const {
    onRefreshProjectHistory,
    onRefreshProjectRevisions,
    onLoadMoreAnalysisHistory,
    onLoadMoreExportHistory,
    onLoadMoreProjectRevisions,
    onLoadProjects,
    onClearHistoryRunSelection,
    onOpenHistoryRun,
    onLoadProjectRevision,
    onCompareProject,
    onExportWorkspace,
    onLoadProject,
    onDeleteProject,
    onRestoreProject,
    onPermanentlyDeleteProject
  } = useSidebarActions();
  const {
    savedProjectsTotal,
    projectsWithoutSnapshots,
    formatOptionalProjectTimestamp,
    translateMetricType,
    translateRevisionSource
  } = useProjectStats();

  const hasMoreAnalysisHistory = Boolean(
    projectHistory && projectHistory.analysis_runs.length < projectHistory.analysis_total
  );
  const hasMoreExportHistory = Boolean(
    projectHistory && projectHistory.export_events.length < projectHistory.export_total
  );
  const hasMoreProjectRevisions = Boolean(
    projectRevisions && projectRevisions.revisions.length < projectRevisions.total
  );

  return (
    <>
      <div className="card">
        <h3>{t("sidebarPanel.activeProject.title")}</h3>
        {activeProjectId ? (
          <>
            <div className="actions">
              <span className="pill">
                {hasUnsavedChanges
                  ? t("sidebarPanel.activeProject.unsavedChanges")
                  : t("sidebarPanel.activeProject.savedLocally")}
              </span>
            </div>
            <ul className="list">
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.projectName")}:</strong>{" "}
                {activeProject?.project_name ?? t("sidebarPanel.activeProject.unknownProject")}
              </li>
              {isAdmin ? (
                <li>
                  <strong>{t("sidebarPanel.activeProject.labels.projectId")}:</strong> {activeProjectId}
                </li>
              ) : null}
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.status")}:</strong>{" "}
                {hasUnsavedChanges
                  ? t("sidebarPanel.activeProject.statusNeedsLocalUpdate")
                  : t("sidebarPanel.activeProject.statusInSync")}
              </li>
              {isAdmin ? (
                <li>
                  <strong>{t("sidebarPanel.activeProject.labels.payloadSchema")}:</strong>{" "}
                  {String(activeProject?.payload_schema_version ?? 1)}
                </li>
              ) : null}
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.savedRevisions")}:</strong>{" "}
                {String(activeProject?.revision_count ?? 0)}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.lastSave")}:</strong>{" "}
                {formatOptionalProjectTimestamp(activeProject?.last_revision_at)}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.lastAnalysis")}:</strong>{" "}
                {formatOptionalProjectTimestamp(activeProject?.last_analysis_at)}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.lastExport")}:</strong>{" "}
                {formatOptionalProjectTimestamp(activeProject?.last_exported_at)}
              </li>
              {isAdmin ? (
                <li>
                  <strong>{t("sidebarPanel.activeProject.labels.snapshotStored")}:</strong>{" "}
                  {activeProject?.has_analysis_snapshot ? t("wizardDraft.common.yes") : t("wizardDraft.common.no")}
                </li>
              ) : null}
            </ul>
          </>
        ) : (
          <p className="muted">{t("sidebarPanel.activeProject.empty")}</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.projectHistory.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>{t("sidebarPanel.projectHistory.description")}</p>
          </div>
          <button
            className="btn ghost"
            disabled={loadingProjectHistory || !activeProjectId}
            onClick={() => {
              if (activeProjectId) {
                onRefreshProjectHistory(activeProjectId);
              }
            }}
          >
            {loadingProjectHistory ? t("sidebarPanel.projectHistory.refreshing") : t("sidebarPanel.projectHistory.refresh")}
          </button>
        </div>
        {!activeProjectId ? (
          <p className="muted">{t("sidebarPanel.projectHistory.empty")}</p>
        ) : projectHistoryError ? (
          <div className="status">{t("sidebarPanel.projectHistory.unavailable")} {projectHistoryError}</div>
        ) : loadingProjectHistory && !projectHistory ? (
          <p className="muted">{t("sidebarPanel.projectHistory.loading")}</p>
        ) : projectHistory ? (
          <>
            <p className="muted">
              {t("sidebarPanel.projectHistory.summary", {
                analysisVisible: projectHistory.analysis_runs.length,
                analysisTotal: projectHistory.analysis_total,
                exportVisible: projectHistory.export_events.length,
                exportTotal: projectHistory.export_total
              })}
            </p>
            {selectedHistoryRunId ? (
              <div className="actions">
                <button className="btn secondary" onClick={onClearHistoryRunSelection}>
                  {t("sidebarPanel.projectHistory.closeOpenedSnapshot")}
                </button>
              </div>
            ) : null}
            <div className={styles["timeline-card"]}>
              <h3>{t("sidebarPanel.projectHistory.analysisRunsTitle")}</h3>
              <div className={styles["timeline-list"]}>
                {projectHistory.analysis_runs.length > 0 ? (
                  projectHistory.analysis_runs.map((run) => (
                    <div key={run.id} className={styles["timeline-item"]}>
                      <div className={styles["timeline-title"]}>
                        <strong>{formatProjectTimestamp(run.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {translateMetricType(run.summary.metric_type)}
                        {" | "}n={String(run.summary.total_sample_size ?? "-")}
                        {" | "}
                        {t("sidebarPanel.common.daysShort", { value: String(run.summary.estimated_duration_days ?? "-") })}
                        {" | "}
                        {t("sidebarPanel.projectHistory.warningsCount", { count: run.summary.warnings_count })}
                        {run.summary.advice_available ? ` | ${t("sidebarPanel.projectHistory.aiAdvice")}` : ""}
                      </div>
                      <div className="actions">
                        <button className="btn secondary" onClick={() => onOpenHistoryRun(run.id)}>
                          {selectedHistoryRunId === run.id
                            ? t("sidebarPanel.projectHistory.opened")
                            : t("sidebarPanel.projectHistory.openSnapshot")}
                        </button>
                        {selectedHistoryRunId === run.id ? <span className="pill">{t("sidebarPanel.projectHistory.viewing")}</span> : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>{t("sidebarPanel.projectHistory.noAnalysisHistory")}</div>
                  </div>
                )}
              </div>
              {hasMoreAnalysisHistory && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreAnalysisHistory(activeProjectId)}>
                    {t("sidebarPanel.projectHistory.loadOlderAnalysisRuns")}
                  </button>
                </div>
              ) : null}
            </div>
            <div className={styles["timeline-card"]}>
              <h3>{t("sidebarPanel.projectHistory.exportEventsTitle")}</h3>
              <div className={styles["timeline-list"]}>
                {projectHistory.export_events.length > 0 ? (
                  projectHistory.export_events.map((event) => (
                    <div key={event.id} className={styles["timeline-item"]}>
                      <div className={styles["timeline-title"]}>
                        <strong>{formatProjectTimestamp(event.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {event.format.toUpperCase()}
                        {event.analysis_run_id
                          ? ` | ${t("sidebarPanel.projectHistory.linkedSnapshot")}`
                          : ` | ${t("sidebarPanel.projectHistory.unlinkedExport")}`}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>{t("sidebarPanel.projectHistory.noExportHistory")}</div>
                  </div>
                )}
              </div>
              {hasMoreExportHistory && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreExportHistory(activeProjectId)}>
                    {t("sidebarPanel.projectHistory.loadOlderExportEvents")}
                  </button>
                </div>
              ) : null}
            </div>
          </>
        ) : (
          <p className="muted">{t("sidebarPanel.projectHistory.notLoaded")}</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.revisions.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.revisions.description")}
            </p>
          </div>
          <button
            className="btn ghost"
            disabled={loadingProjectRevisions || !activeProjectId}
            onClick={() => {
              if (activeProjectId) {
                onRefreshProjectRevisions(activeProjectId);
              }
            }}
          >
            {loadingProjectRevisions ? t("sidebarPanel.revisions.refreshing") : t("sidebarPanel.revisions.refresh")}
          </button>
        </div>
        {!activeProjectId ? (
          <p className="muted">{t("sidebarPanel.revisions.empty")}</p>
        ) : projectRevisionsError ? (
          <div className="status">{t("sidebarPanel.revisions.unavailable")} {projectRevisionsError}</div>
        ) : loadingProjectRevisions && !projectRevisions ? (
          <p className="muted">{t("sidebarPanel.revisions.loading")}</p>
        ) : projectRevisions ? (
          <>
            <p className="muted">
              {t("sidebarPanel.revisions.summary", {
                visible: projectRevisions.revisions.length,
                total: projectRevisions.total
              })}
            </p>
            <div className={styles["timeline-card"]}>
              <div className={styles["timeline-list"]}>
                {projectRevisions.revisions.length > 0 ? (
                  projectRevisions.revisions.map((revision) => (
                    <div key={revision.id} className={styles["timeline-item"]}>
                      <div className={styles["timeline-title"]}>
                        <strong>{formatProjectTimestamp(revision.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {translateRevisionSource(revision.source)}
                        {" | "}
                        {revision.payload.project.project_name}
                      </div>
                      <div className="actions">
                        <button className="btn secondary" onClick={() => onLoadProjectRevision(revision.id)}>
                          {t("sidebarPanel.revisions.loadIntoWizard")}
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>{t("sidebarPanel.revisions.noEntries")}</div>
                  </div>
                )}
              </div>
              {hasMoreProjectRevisions && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreProjectRevisions(activeProjectId)}>
                    {t("sidebarPanel.revisions.loadOlder")}
                  </button>
                </div>
              ) : null}
            </div>
          </>
        ) : (
          <p className="muted">{t("sidebarPanel.revisions.notLoaded")}</p>
        )}
      </div>

      <div className="card" data-testid="project-compare-panel">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.savedProjects.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>{t("sidebarPanel.savedProjects.description")}</p>
          </div>
          <button className="btn ghost" disabled={loadingProjects} onClick={onLoadProjects}>
            {loadingProjects ? t("sidebarPanel.savedProjects.loading") : t("sidebarPanel.savedProjects.load")}
          </button>
        </div>
        <div className="actions">
          <span className="pill">{t("sidebarPanel.savedProjects.savedCount", { count: savedProjectsTotal })}</span>
          <span className="pill">
            {t("sidebarPanel.savedProjects.withoutSavedAnalysisCount", { count: projectsWithoutSnapshots })}
          </span>
        </div>
        {loadingProjects ? (
          <ProjectListSkeleton />
        ) : allSavedProjects.length > 0 ? (
          <>
            <ProjectListFilters
              query={filters.query}
              status={filters.status}
              metricType={filters.metricType}
              sortBy={filters.sortBy}
              onQueryChange={filters.setQuery}
              onStatusChange={filters.setStatus}
              onMetricTypeChange={filters.setMetricType}
              onSortByChange={filters.setSortBy}
              onClearFilters={filters.resetFilters}
            />
            <p className="muted">
              {t("sidebarPanel.savedProjects.shownExperiments", { count: filters.filteredProjects.length })}
            </p>
            {filters.compareCandidates.length > 0 ? (
              <>
                <p className="muted">{t("sidebarPanel.savedProjects.compareDescription")}</p>
                <div className="actions">
                  <span className="pill">{t("sidebarPanel.savedProjects.selectedForComparison", { count: filters.selectedComparisonProjectIds.length })}</span>
                  <button
                    className="btn secondary"
                    data-testid="project-compare-submit"
                    id="compare-selected-projects-button"
                    type="button"
                    disabled={!filters.canCompareSelected || loadingProjectComparison}
                    onClick={() => void filters.onCompareSelectedProjects()}
                  >
                    {loadingProjectComparison
                      ? t("sidebarPanel.savedProjects.actions.comparing")
                      : t("sidebarPanel.savedProjects.actions.compareSelected")}
                  </button>
                </div>
                {projectMultiComparison ? (
                  <p className="muted">{t("sidebarPanel.savedProjects.currentDashboard", { count: projectMultiComparison.projects.length })}</p>
                ) : projectComparison ? (
                  <p className="muted">
                    {t("sidebarPanel.savedProjects.currentComparison", {
                      baseProject: projectComparison.base_project.project_name,
                      candidateProject: projectComparison.candidate_project.project_name
                    })}
                  </p>
                ) : null}
                {projectComparisonError ? (
                  <div className="status">{t("sidebarPanel.savedProjects.comparisonUnavailable")} {projectComparisonError}</div>
                ) : null}
              </>
            ) : (
              <p className="muted">{t("sidebarPanel.savedProjects.compareRequiresSnapshot")}</p>
            )}
            <div className={styles["project-card-list"]}>
              {filters.filteredProjects.map((project) => (
                <div
                  key={project.id}
                  className={[styles["project-card"], project.id === activeProjectId ? styles.active : ""].filter(Boolean).join(" ")}
                >
                  <div className={styles["project-card-head"]}>
                    {project.is_archived ? (
                      <strong>{project.project_name}</strong>
                    ) : (
                      <button className={`btn ghost ${styles["project-load-btn"]}`} onClick={() => onLoadProject(project.id)}>
                        {project.project_name}
                      </button>
                    )}
                    <div className={styles["project-badges"]}>
                      {project.id === activeProjectId ? <span className="pill">{t("sidebarPanel.savedProjects.badges.loaded")}</span> : null}
                      {project.has_analysis_snapshot ? <span className="pill">{t("sidebarPanel.savedProjects.badges.snapshot")}</span> : null}
                      {project.is_archived ? <span className="pill">{t("sidebarPanel.savedProjects.badges.archived")}</span> : null}
                    </div>
                  </div>
                  <div className={styles["project-meta"]}>
                    <div className="muted">
                      {t("sidebarPanel.savedProjects.updatedAt", { timestamp: formatProjectTimestamp(project.updated_at) })}
                      {project.last_revision_at
                        ? ` | ${t("sidebarPanel.savedProjects.savedAt", { timestamp: formatProjectTimestamp(project.last_revision_at) })}`
                        : ""}
                      {project.last_analysis_at
                        ? ` | ${t("sidebarPanel.savedProjects.analyzedAt", { timestamp: formatProjectTimestamp(project.last_analysis_at) })}`
                        : ""}
                    </div>
                    <div className="muted">
                      {project.hypothesis ? `${project.hypothesis} | ` : ""}
                      {project.metric_type ? `${translateMetricType(project.metric_type)} | ` : ""}
                      {project.duration_days
                        ? `${t("sidebarPanel.common.daysShort", { value: String(project.duration_days) })} | `
                        : ""}
                      {t("sidebarPanel.savedProjects.revisionsCount", { count: project.revision_count ?? 0 })}
                      {" | "}
                      {project.last_exported_at
                        ? t("sidebarPanel.savedProjects.exportedAt", { timestamp: formatProjectTimestamp(project.last_exported_at) })
                        : t("sidebarPanel.savedProjects.noExportsYet")}
                      {project.id === activeProjectId ? ` | ${t("sidebarPanel.savedProjects.loadedInWizard")}` : ""}
                    </div>
                  </div>
                  <div className="actions">
                    {project.has_analysis_snapshot && !project.is_archived ? (
                      <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                        <input
                          data-project-id={project.id}
                          data-testid="project-compare-checkbox"
                          type="checkbox"
                          checked={filters.selectedComparisonProjectIds.includes(project.id)}
                          onChange={(event) => filters.toggleComparisonSelection(project.id, event.target.checked)}
                        />
                        <span>{t("sidebarPanel.savedProjects.actions.selectForComparison")}</span>
                      </label>
                    ) : null}
                    {activeProjectId && project.id !== activeProjectId && project.has_analysis_snapshot && !project.is_archived ? (
                      <button
                        className="btn secondary"
                        type="button"
                        disabled={loadingProjectComparison}
                        onClick={() => void onCompareProject(project.id)}
                      >
                        {loadingProjectComparison && comparingProjectId === project.id
                          ? t("sidebarPanel.savedProjects.actions.comparing")
                          : t("sidebarPanel.savedProjects.actions.compare")}
                      </button>
                    ) : null}
                    {project.is_archived ? (
                      <button
                        className="btn secondary"
                        disabled={!canMutateBackend || restoringProjectId === project.id}
                        onClick={() => onRestoreProject(project.id)}
                      >
                        {restoringProjectId === project.id
                          ? t("sidebarPanel.savedProjects.actions.restoring")
                          : t("sidebarPanel.savedProjects.actions.restore")}
                      </button>
                    ) : (
                      <>
                        <InlineConfirmButton
                          label={t("sidebarPanel.savedProjects.actions.archive")}
                          disabled={!canMutateBackend || deletingProjectId === project.id}
                          ariaLabel={t("sidebarPanel.savedProjects.archiveAriaLabel", { projectName: project.project_name })}
                          onConfirm={() => onDeleteProject(project.id, project.project_name)}
                        />
                        <InlineConfirmButton
                          label={t("sidebarPanel.savedProjects.actions.delete")}
                          disabled={!canMutateBackend || deletingProjectId === project.id}
                          ariaLabel={t("sidebarPanel.savedProjects.deleteAriaLabel", { projectName: project.project_name })}
                          onConfirm={() => onPermanentlyDeleteProject(project.id, project.project_name)}
                        />
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {filters.filteredProjects.length === 0 ? (
              <div className="actions">
                <p className="muted">{t("sidebarPanel.savedProjects.noMatches")}</p>
                <button
                  className="btn ghost"
                  type="button"
                  onClick={filters.resetFilters}
                >
                  {t("projectListFilters.clear")}
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <p className="muted">{t("sidebarPanel.savedProjects.empty")}</p>
        )}
      </div>

      {filters.showArchivedSection ? (
        <div className="card">
          <div className="section-heading">
            <div>
              <h3>{t("sidebarPanel.archivedProjects.title")}</h3>
              <p className={`muted ${styles["compact-text"]}`}>{t("sidebarPanel.archivedProjects.description")}</p>
            </div>
          </div>
          {archivedProjects.length > 0 ? (
            <div className={styles["project-card-list"]}>
              {archivedProjects.map((project) => (
                <div key={project.id} className={styles["project-card"]}>
                  <div className={styles["project-card-head"]}>
                    <strong>{project.project_name}</strong>
                    <div className={styles["project-badges"]}>
                      <span className="pill">{t("sidebarPanel.savedProjects.badges.archived")}</span>
                    </div>
                  </div>
                  <div className={styles["project-meta"]}>
                    <div className="muted">
                      {t("sidebarPanel.archivedProjects.archivedAt", {
                        timestamp: formatOptionalProjectTimestamp(project.archived_at)
                      })}
                      {project.last_analysis_at
                        ? ` | ${t("sidebarPanel.archivedProjects.lastAnalysisAt", {
                          timestamp: formatProjectTimestamp(project.last_analysis_at)
                        })}`
                        : ""}
                    </div>
                    <div className="muted">
                      {t("sidebarPanel.savedProjects.revisionsCount", { count: project.revision_count ?? 0 })}
                      {" | "}
                      {project.last_exported_at
                        ? t("sidebarPanel.savedProjects.exportedAt", { timestamp: formatProjectTimestamp(project.last_exported_at) })
                        : t("sidebarPanel.savedProjects.noExportsYet")}
                    </div>
                  </div>
                  <div className="actions">
                    <button
                      className="btn secondary"
                      disabled={!canMutateBackend || restoringProjectId === project.id}
                      onClick={() => onRestoreProject(project.id)}
                    >
                      {restoringProjectId === project.id
                        ? t("sidebarPanel.savedProjects.actions.restoring")
                        : t("sidebarPanel.savedProjects.actions.restore")}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">{t("sidebarPanel.archivedProjects.empty")}</p>
          )}
        </div>
      ) : null}

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.workspaceBackup.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.workspaceBackup.projectsDescription")}
            </p>
          </div>
        </div>
        <div className="actions">
          <button className="btn ghost" disabled={exportingWorkspace} onClick={onExportWorkspace}>
            {exportingWorkspace ? t("sidebarPanel.workspaceBackup.exporting") : t("sidebarPanel.workspaceBackup.export")}
          </button>
          <button className="btn secondary" disabled={!canMutateBackend || importingWorkspace} onClick={onImportWorkspace}>
            {importingWorkspace ? t("sidebarPanel.workspaceBackup.importing") : t("sidebarPanel.workspaceBackup.import")}
          </button>
        </div>
      </div>
    </>
  );
}
