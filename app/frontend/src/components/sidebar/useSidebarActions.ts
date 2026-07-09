import type { ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

import type { ToastType } from "../../hooks/useToast";
import { hydrateLoadedPayload, stepLabels } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useDraftStore } from "../../stores/draftStore";
import { useProjectStore } from "../../stores/projectStore";
import { useWizardStore } from "../../stores/wizardStore";

/**
 * Handlers shared by the sidebar shell and its tabs. Every one of them is derived
 * from the stores alone, so each caller can invoke this hook independently instead
 * of threading twenty callbacks through props.
 */
export function useSidebarActions() {
  const { t } = useTranslation();
  const analysis = useAnalysisStore();
  const draftStore = useDraftStore();
  const project = useProjectStore();
  const openWizard = useWizardStore((state) => state.openWizard);

  async function showAsyncStatus(action: Promise<string | null>, type: ToastType) {
    const message = await action;
    if (message) {
      analysis.showStatus(message, type);
    }
  }

  function blockMutations(): boolean {
    if (project.canMutateBackend) {
      return false;
    }
    analysis.clearFeedback();
    analysis.showError(project.backendMutationMessage || t("sidebarPanel.status.readOnlyMode"), "warning");
    return true;
  }

  const onRefreshHealth = () => void project.loadBackendHealth();
  const onRefreshDiagnostics = () => void project.loadBackendDiagnostics();
  const onApiTokenDraftChange = (value: string) => project.updateApiTokenDraft(value);
  const onRefreshProjectHistory = (projectId: string) => void project.refreshProjectHistory(projectId);
  const onRefreshProjectRevisions = (projectId: string) => void project.refreshProjectRevisions(projectId);
  const onLoadMoreAnalysisHistory = (projectId: string) => void project.loadMoreAnalysisHistory(projectId);
  const onLoadMoreExportHistory = (projectId: string) => void project.loadMoreExportHistory(projectId);
  const onLoadMoreProjectRevisions = (projectId: string) => void project.loadMoreProjectRevisions(projectId);
  const onLoadProjects = () => void project.refreshProjects();

  async function onSaveApiToken() {
    analysis.clearFeedback();
    await showAsyncStatus(project.saveRuntimeApiToken(), "info");
  }

  async function onClearApiToken() {
    analysis.clearFeedback();
    await showAsyncStatus(project.clearRuntimeApiToken(), "info");
    analysis.clearAnalysis();
  }

  function onClearHistoryRunSelection() {
    if (!project.clearHistoryRunSelection()) {
      return;
    }
    analysis.clearFeedback();
    analysis.showStatus(
      analysis.results.report
        ? t("sidebarPanel.status.returnedToCurrentResults")
        : t("sidebarPanel.status.closedSnapshotPreview"),
      "info"
    );
  }

  async function onOpenHistoryRun(runId: string) {
    if (!project.openHistoryRun(runId)) {
      return;
    }
    analysis.clearFeedback();
    analysis.showStatus(t("sidebarPanel.status.openedSnapshotFromHistory"), "info");
    openWizard(stepLabels.length - 1);
  }

  function onLoadProjectRevision(revisionId: string) {
    const revision = project.loadProjectRevision(revisionId);
    if (!revision) {
      return;
    }
    draftStore.replaceDraft(revision.draft, { markDirty: true });
    analysis.clearAnalysis();
    analysis.showStatus(revision.message, "info");
    openWizard();
  }

  async function onCompareProject(projectId: string) {
    const message = await project.compareProject(projectId);
    if (message) {
      analysis.showStatus(message, "info");
    }
  }

  async function onExportWorkspace() {
    if (blockMutations()) {
      return;
    }
    analysis.clearFeedback();
    await showAsyncStatus(project.exportWorkspace(), "success");
  }

  async function handleWorkspaceImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    event.target.value = "";
    if (blockMutations()) {
      return;
    }
    analysis.clearFeedback();
    await showAsyncStatus(project.importWorkspace(await file.text()), "success");
  }

  async function onLoadProject(projectId: string) {
    analysis.clearFeedback();
    const loaded = await project.loadProject(projectId);
    if (!loaded) {
      return;
    }
    draftStore.replaceDraft(hydrateLoadedPayload(loaded.payload), { markDirty: true });
    analysis.clearAnalysis();
    analysis.showStatus(
      t("sidebarPanel.status.loadedProjectIntoWizard", { projectName: String(loaded.project_name) }),
      "info"
    );
    openWizard();
  }

  async function onDeleteProject(projectId: string, projectName: string) {
    if (blockMutations()) {
      return;
    }
    analysis.clearFeedback();
    const result = await project.archiveProject(projectId);
    if (!result.deleted) {
      return;
    }
    if (result.deletedActive) {
      analysis.clearAnalysis();
      analysis.showStatus(t("sidebarPanel.status.projectArchivedCurrentDraft", { projectName }), "success");
      return;
    }
    analysis.showStatus(t("sidebarPanel.status.projectArchived", { projectName }), "success");
  }

  async function onRestoreProject(projectId: string) {
    analysis.clearFeedback();
    const restored = await project.restoreProject(projectId);
    if (!restored) {
      return;
    }
    if (useProjectStore.getState().activeProjectId === projectId) {
      draftStore.replaceDraft(hydrateLoadedPayload(restored.payload), { markDirty: true });
    }
    analysis.showStatus(
      t("sidebarPanel.status.projectRestored", { projectName: String(restored.project_name) }),
      "success"
    );
  }

  async function onPermanentlyDeleteProject(projectId: string, projectName: string) {
    if (blockMutations()) {
      return;
    }
    analysis.clearFeedback();
    const result = await project.deleteProject(projectId);
    if (!result.deleted) {
      return;
    }
    if (result.deletedActive) {
      analysis.clearAnalysis();
      analysis.showStatus(t("sidebarPanel.status.projectDeletedCurrentDraft", { projectName }), "success");
      return;
    }
    analysis.showStatus(t("sidebarPanel.status.projectDeleted", { projectName }), "success");
  }

  return {
    blockMutations,
    showAsyncStatus,
    handleWorkspaceImport,
    onRefreshHealth,
    onRefreshDiagnostics,
    onApiTokenDraftChange,
    onRefreshProjectHistory,
    onRefreshProjectRevisions,
    onLoadMoreAnalysisHistory,
    onLoadMoreExportHistory,
    onLoadMoreProjectRevisions,
    onLoadProjects,
    onSaveApiToken,
    onClearApiToken,
    onClearHistoryRunSelection,
    onOpenHistoryRun,
    onLoadProjectRevision,
    onCompareProject,
    onExportWorkspace,
    onLoadProject,
    onDeleteProject,
    onRestoreProject,
    onPermanentlyDeleteProject
  };
}

export type SidebarActions = ReturnType<typeof useSidebarActions>;
