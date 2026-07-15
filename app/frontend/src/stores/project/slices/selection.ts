/** Selection / dirty-state / comparison-clear actions. */
import {
  initialProjectHistoryWindow,
  initialProjectRevisionWindow,
  type ApplyStoreUpdate,
  type ProjectStoreActions
} from "../types";

export function createSelectionActions(
  applyStoreUpdate: ApplyStoreUpdate
): Pick<
  ProjectStoreActions,
  "clearProjectError" | "clearComparison" | "markDraftChanged" | "resetProjectSelection"
> {
  return {
    clearProjectError: () => {
      applyStoreUpdate({ projectError: "" });
    },
    clearComparison: () => {
      applyStoreUpdate({
        projectComparison: null,
        projectMultiComparison: null,
        projectComparisonError: "",
        loadingProjectComparison: false,
        comparingProjectId: null
      });
    },
    markDraftChanged: (serializedForm) => {
      applyStoreUpdate((state) => ({
        selectedHistoryRunId: null,
        projectComparison: null,
        projectMultiComparison: null,
        projectComparisonError: "",
        loadingProjectComparison: false,
        comparingProjectId: null,
        dirtyState:
          serializedForm === undefined
            ? state.dirtyState
            : {
                ...state.dirtyState,
                currentSerializedForm: serializedForm
              }
      }));
    },
    resetProjectSelection: () => {
      applyStoreUpdate({
        activeProjectId: null,
        savedProjectSnapshot: null,
        dirtyState: {
          currentSerializedForm: null,
          savedSerializedForm: null
        },
        projectHistory: null,
        projectHistoryWindow: initialProjectHistoryWindow,
        projectHistoryError: "",
        loadingProjectHistory: false,
        projectRevisions: null,
        projectRevisionWindow: initialProjectRevisionWindow,
        projectRevisionsError: "",
        loadingProjectRevisions: false,
        selectedHistoryRunId: null,
        projectComparison: null,
        projectMultiComparison: null,
        projectComparisonError: "",
        loadingProjectComparison: false,
        comparingProjectId: null
      });
    },

  };
}
