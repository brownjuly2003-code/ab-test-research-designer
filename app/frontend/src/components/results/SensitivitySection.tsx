import type { SensitivityResponse } from "../../lib/generated/api-contract";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import SensitivityOverview from "./internal/SensitivityOverview";
import { getDisplayedAnalysis } from "./resultsShared";

type SensitivitySectionProps = {
  sensitivityData: SensitivityResponse | null;
  sensitivityLoading: boolean;
  sensitivityUnavailableMessage: string;
  standaloneExporting: boolean;
  standaloneExportError: string;
  canExportPdf: boolean;
  onExportReport: (format: "markdown" | "html") => void;
  onExportPdf: () => void;
  onExportProjectData: (format: "csv" | "xlsx") => void;
  onExportStandalone: () => void;
};

export default function SensitivitySection(props: SensitivitySectionProps) {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const activeProject = useProjectStore((state) => state.activeProject);
  const projectHistory = useProjectStore((state) => state.projectHistory);
  const canMutateBackend = useProjectStore((state) => state.canMutateBackend);
  const backendMutationMessage = useProjectStore((state) => state.backendMutationMessage);
  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);

  if (!displayedAnalysis?.report) {
    return null;
  }

  return (
    <SensitivityOverview
      {...props}
      displayedAnalysis={displayedAnalysis}
      activeProject={activeProject}
      projectHistory={projectHistory}
      canMutateBackend={canMutateBackend}
      backendMutationMessage={backendMutationMessage}
    />
  );
}
