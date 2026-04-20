import { create } from "zustand";

import {
  browserDraftStorageKey,
  buildDraftTransferFile,
  cloneInitialState,
  parseImportedDraft,
  setSectionFieldValue,
  type DraftFieldValue,
  type FullPayload,
  type FullPayloadSectionKey
} from "../lib/experiment";

export type StorageWarningLevel = "full" | "nearFull" | "cleared" | null;

export type DraftBootstrap = {
  form: FullPayload;
  restored: boolean;
  warningLevel: StorageWarningLevel;
  warningMessage: string | null;
};

type ReplaceDraftOptions = {
  markDirty?: boolean;
};

type DraftStoreState = {
  draft: FullPayload;
  isDirty: boolean;
  draftStorageWarning: StorageWarningLevel;
  draftStorageMessage: string | null;
  restoredFromBootstrap: boolean;
  readDraftBootstrap: () => DraftBootstrap;
  updateDraft: (partial: Partial<FullPayload>) => void;
  updateDraftField: (path: string, value: DraftFieldValue) => void;
  replaceDraft: (nextDraft: FullPayload, options?: ReplaceDraftOptions) => void;
  resetDraft: () => void;
  parseImportedDraftText: (raw: string) => FullPayload;
  clearDraftStorageWarning: () => void;
  clearStorageWarning: () => void;
};

type InternalDraftState = {
  baselineDraft: string;
  restoreWarningLevel: StorageWarningLevel;
  restoreWarningMessage: string | null;
};

type StorageWarningState = Pick<
  DraftStoreState,
  "draftStorageMessage" | "draftStorageWarning"
>;

function describeStorageError(error: unknown): string {
  if (error instanceof Error) {
    const detail = error.message.trim();
    if (detail.length > 0) {
      return detail;
    }
    if (error.name && error.name !== "Error") {
      return error.name;
    }
  }

  return "Unknown storage error";
}

function isQuotaExceededError(error: unknown): boolean {
  if (error instanceof DOMException) {
    return error.name === "QuotaExceededError";
  }

  return error instanceof Error && error.name === "QuotaExceededError";
}

function buildDraftSaveWarning(error: unknown): StorageWarningState {
  if (isQuotaExceededError(error)) {
    return {
      draftStorageWarning: "full",
      draftStorageMessage: "Storage full - draft not saved. Clear old data or use Export."
    };
  }

  return {
    draftStorageWarning: "nearFull",
    draftStorageMessage: `Browser draft could not be saved locally: ${describeStorageError(error)}`
  };
}

function clearStorageWarningState(): StorageWarningState {
  return {
    draftStorageWarning: null,
    draftStorageMessage: null
  };
}

function buildRestoredDraftWarning(error: unknown): StorageWarningState {
  return {
    draftStorageWarning: "cleared",
    draftStorageMessage: `Stored browser draft could not be restored: ${describeStorageError(error)}`
  };
}

function serializeDraft(form: FullPayload): string {
  return JSON.stringify(buildDraftTransferFile(form));
}

function isSectionKey(value: string): value is Extract<FullPayloadSectionKey, string> {
  return value === "project" ||
    value === "hypothesis" ||
    value === "setup" ||
    value === "metrics" ||
    value === "constraints" ||
    value === "additional_context";
}

export function readDraftBootstrap(): DraftBootstrap {
  const fallback = {
    form: cloneInitialState(),
    restored: false,
    warningLevel: null,
    warningMessage: null
  };

  if (typeof window === "undefined") {
    return fallback;
  }

  try {
    const storedDraft = window.localStorage.getItem(browserDraftStorageKey);
    if (!storedDraft) {
      return fallback;
    }

    return {
      form: parseImportedDraft(storedDraft),
      restored: true,
      warningLevel: null,
      warningMessage: null
    };
  } catch (error) {
    console.warn("localStorage restore failed:", error);
    try {
      window.localStorage.removeItem(browserDraftStorageKey);
    } catch (cleanupError) {
      console.warn("localStorage cleanup failed:", cleanupError);
    }
    const warning = buildRestoredDraftWarning(error);

    return {
      ...fallback,
      warningLevel: warning.draftStorageWarning,
      warningMessage: warning.draftStorageMessage
    };
  }
}

const initialBootstrap = readDraftBootstrap();

function persistSerializedDraft(serializedDraft: string) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(browserDraftStorageKey, serializedDraft);
    useDraftStore.setState((state) => {
      const keepWarning =
        state.draftStorageWarning !== null &&
        state.draftStorageWarning === state.restoreWarningLevel &&
        state.draftStorageMessage === state.restoreWarningMessage;
      const nextWarning = keepWarning
        ? {
            draftStorageWarning: state.draftStorageWarning,
            draftStorageMessage: state.draftStorageMessage
          }
        : clearStorageWarningState();

      if (
        state.draftStorageWarning === nextWarning.draftStorageWarning &&
        state.draftStorageMessage === nextWarning.draftStorageMessage
      ) {
        return state;
      }

      return nextWarning;
    });
  } catch (error) {
    console.warn("localStorage save failed:", error);
    useDraftStore.setState(buildDraftSaveWarning(error));
  }
}

function setDraftState(nextDraft: FullPayload, options: ReplaceDraftOptions = {}) {
  const currentSerializedDraft = serializeDraft(useDraftStore.getState().draft);
  const nextSerializedDraft = serializeDraft(nextDraft);

  useDraftStore.setState((state) => {
    const nextBaselineDraft = options.markDirty ? state.baselineDraft : nextSerializedDraft;
    return {
      draft: nextDraft,
      baselineDraft: nextBaselineDraft,
      isDirty: nextSerializedDraft !== nextBaselineDraft
    };
  });

  if (nextSerializedDraft === currentSerializedDraft) {
    return;
  }

  persistSerializedDraft(nextSerializedDraft);
}

export const useDraftStore = create<DraftStoreState & InternalDraftState>((set, get) => ({
  draft: initialBootstrap.form,
  baselineDraft: serializeDraft(initialBootstrap.form),
  isDirty: false,
  restoredFromBootstrap: initialBootstrap.restored,
  restoreWarningLevel: initialBootstrap.warningLevel,
  restoreWarningMessage: initialBootstrap.warningMessage,
  draftStorageWarning: initialBootstrap.warningLevel,
  draftStorageMessage: initialBootstrap.warningMessage,
  readDraftBootstrap: () => {
    const bootstrap = readDraftBootstrap();
    const serializedDraft = serializeDraft(bootstrap.form);

    set({
      draft: bootstrap.form,
      baselineDraft: serializedDraft,
      isDirty: false,
      restoredFromBootstrap: bootstrap.restored,
      restoreWarningLevel: bootstrap.warningLevel,
      restoreWarningMessage: bootstrap.warningMessage,
      draftStorageWarning: bootstrap.warningLevel,
      draftStorageMessage: bootstrap.warningMessage
    });
    persistSerializedDraft(serializedDraft);

    return bootstrap;
  },
  updateDraft: (partial) => {
    setDraftState({ ...get().draft, ...partial }, { markDirty: true });
  },
  updateDraftField: (path, value) => {
    const [section, key] = path.split(".");

    if (!section || !key || !isSectionKey(section)) {
      return;
    }

    setDraftState(
      setSectionFieldValue(get().draft, section, key, value),
      { markDirty: true }
    );
  },
  replaceDraft: (nextDraft, options = {}) => {
    setDraftState(nextDraft, options);
  },
  resetDraft: () => {
    setDraftState(cloneInitialState());
  },
  parseImportedDraftText: (raw) => parseImportedDraft(raw),
  clearDraftStorageWarning: () => {
    set(clearStorageWarningState());
  },
  clearStorageWarning: () => {
    set(clearStorageWarningState());
  }
}));
