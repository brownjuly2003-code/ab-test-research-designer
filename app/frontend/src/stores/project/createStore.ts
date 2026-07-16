import { create } from "zustand";

import type { ProjectRecordResponse } from "../../lib/api";
import { deriveProjectState, toSavedProject, upsertSavedProject } from "./helpers";
import { createInitialProjectValues } from "./initialState";
import { createCrudActions } from "./slices/crud";
import { createExportsActions } from "./slices/exports";
import { createHealthAuthActions } from "./slices/healthAuth";
import { createHistoryActions } from "./slices/history";
import { createSelectionActions } from "./slices/selection";
import { createWorkspaceActions } from "./slices/workspace";
import type {
  ProjectStoreState,
  ProjectStoreValues,
  SyncPersistedProject
} from "./types";

export const useProjectStore = create<ProjectStoreState>((set, get) => {
  function applyStoreUpdate(
    update:
      | Partial<ProjectStoreValues>
      | ((state: ProjectStoreState) => Partial<ProjectStoreValues>)
  ) {
    const partial = typeof update === "function" ? update(get()) : update;
    const nextState = {
      ...get(),
      ...partial
    };

    set({
      ...partial,
      ...deriveProjectState(nextState)
    });
  }

  const syncPersistedProject: SyncPersistedProject = (
    record: ProjectRecordResponse,
    serializedPayloadFallback: string
  ) => {
    const savedProjectId = typeof record.id === "string" ? record.id : null;
    const savedProject = toSavedProject(record);
    const persistedSnapshot =
      record.payload ? JSON.stringify(record.payload) : serializedPayloadFallback;

    applyStoreUpdate((state) => ({
      activeProjectId: savedProjectId,
      savedProjectSnapshot: persistedSnapshot,
      dirtyState: {
        currentSerializedForm: persistedSnapshot,
        savedSerializedForm: persistedSnapshot
      },
      savedProjects: savedProject ? upsertSavedProject(state.savedProjects, savedProject) : state.savedProjects
    }));

    return { savedProjectId, savedProject };
  };

  return {
    ...createInitialProjectValues(),
    ...createSelectionActions(applyStoreUpdate),
    ...createCrudActions(applyStoreUpdate, get, syncPersistedProject),
    ...createHealthAuthActions(applyStoreUpdate, get),
    ...createWorkspaceActions(applyStoreUpdate, get),
    ...createHistoryActions(applyStoreUpdate, get),
    ...createExportsActions(applyStoreUpdate, get, syncPersistedProject)
  };
});
