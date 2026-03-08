import { useEffect, useState } from "react";

import {
  browserDraftStorageKey,
  buildDraftTransferFile,
  cloneInitialState,
  parseImportedDraft,
  type FullPayload
} from "../lib/experiment";

export type DraftBootstrap = {
  form: FullPayload;
  restored: boolean;
  warning: string;
};

function describeStorageError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown storage error";
}

export function readDraftBootstrap(): DraftBootstrap {
  const fallback = { form: cloneInitialState(), restored: false, warning: "" };

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
      warning: ""
    };
  } catch (error) {
    console.warn("localStorage restore failed:", error);
    try {
      window.localStorage.removeItem(browserDraftStorageKey);
    } catch (cleanupError) {
      console.warn("localStorage cleanup failed:", cleanupError);
    }

    return {
      ...fallback,
      warning: `Stored browser draft could not be restored: ${describeStorageError(error)}`
    };
  }
}

export function useDraftPersistence(form: FullPayload, initialWarning = "") {
  const [draftStorageWarning, setDraftStorageWarning] = useState(initialWarning);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    try {
      window.localStorage.setItem(browserDraftStorageKey, JSON.stringify(buildDraftTransferFile(form)));
      setDraftStorageWarning((current) => (current ? "" : current));
    } catch (error) {
      console.warn("localStorage save failed:", error);
      setDraftStorageWarning(`Browser draft could not be saved locally: ${describeStorageError(error)}`);
    }
  }, [form]);

  function parseImportedDraftText(raw: string): FullPayload {
    return parseImportedDraft(raw);
  }

  function clearDraftStorageWarning() {
    setDraftStorageWarning("");
  }

  return {
    draftStorageWarning,
    clearDraftStorageWarning,
    parseImportedDraftText
  };
}
