// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  browserDraftStorageKey,
  buildDraftTransferFile,
  cloneInitialState
} from "../lib/experiment";

function createQuotaExceededError() {
  const error = new Error("Quota exceeded");
  error.name = "QuotaExceededError";
  return error;
}

async function loadDraftStore() {
  vi.resetModules();
  return await import("./draftStore");
}

describe("draftStore", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("initializes the default draft when browser storage is empty", async () => {
    const { readDraftBootstrap, useDraftStore } = await loadDraftStore();

    const bootstrap = readDraftBootstrap();

    expect(bootstrap.warningLevel).toBeNull();
    expect(bootstrap.warningMessage).toBeNull();
    expect(bootstrap.form.project.project_name).toBe("Checkout redesign");
    expect(useDraftStore.getState().draft.project.project_name).toBe("Checkout redesign");
  });

  it("does not write a synthetic browser draft on module load when storage is empty", async () => {
    await loadDraftStore();

    expect(window.localStorage.getItem(browserDraftStorageKey)).toBeNull();
  });

  it("restores a previously saved browser draft", async () => {
    const restoredDraft = cloneInitialState();
    restoredDraft.project.project_name = "Recovered draft";

    window.localStorage.setItem(
      browserDraftStorageKey,
      JSON.stringify(buildDraftTransferFile(restoredDraft))
    );

    const { readDraftBootstrap, useDraftStore } = await loadDraftStore();
    const bootstrap = readDraftBootstrap();

    expect(bootstrap.restored).toBe(true);
    expect(bootstrap.warningLevel).toBeNull();
    expect(bootstrap.warningMessage).toBeNull();
    expect(bootstrap.form.project.project_name).toBe("Recovered draft");
    expect(useDraftStore.getState().draft.project.project_name).toBe("Recovered draft");
  });

  it("cleans up corrupted storage payloads and surfaces a restore warning", async () => {
    const removeItemSpy = vi.spyOn(Storage.prototype, "removeItem");
    window.localStorage.setItem(browserDraftStorageKey, "{broken-json");

    const { useDraftStore } = await loadDraftStore();

    expect(removeItemSpy).toHaveBeenCalledWith(browserDraftStorageKey);
    expect(window.localStorage.getItem(browserDraftStorageKey)).not.toBe("{broken-json");
    expect(useDraftStore.getState().draftStorageWarning).toBe("cleared");
    expect(useDraftStore.getState().draftStorageMessage).toContain(
      "Stored browser draft could not be restored:"
    );
  });

  it("surfaces quota warnings and clears them after a later successful autosave", async () => {
    const originalSetItem = Storage.prototype.setItem;
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    setItemSpy
      .mockImplementationOnce(() => {
        throw createQuotaExceededError();
      })
      .mockImplementation(function (this: Storage, key: string, value: string) {
        return originalSetItem.call(this, key, value);
      });

    const { useDraftStore } = await loadDraftStore();

    useDraftStore.getState().updateDraftField("project.project_name", "Will fail once");

    expect(useDraftStore.getState().draftStorageWarning).toBe("full");
    expect(useDraftStore.getState().draftStorageMessage).toBe(
      "Storage full - draft not saved. Clear old data or use Export."
    );

    useDraftStore.getState().updateDraftField("project.project_name", "Saved after retry");

    expect(useDraftStore.getState().draft.project.project_name).toBe("Saved after retry");
    expect(useDraftStore.getState().draftStorageWarning).toBeNull();
    expect(useDraftStore.getState().draftStorageMessage).toBeNull();
    expect(window.localStorage.getItem(browserDraftStorageKey)).toContain("Saved after retry");
  });

  it("marks external replacements as dirty and resetDraft returns to a clean baseline", async () => {
    const replacement = cloneInitialState();
    replacement.project.project_name = "Imported draft";

    const { useDraftStore } = await loadDraftStore();

    expect(useDraftStore.getState().isDirty).toBe(false);

    useDraftStore.getState().replaceDraft(replacement, { markDirty: true });

    expect(useDraftStore.getState().draft.project.project_name).toBe("Imported draft");
    expect(useDraftStore.getState().isDirty).toBe(true);

    useDraftStore.getState().resetDraft();

    expect(useDraftStore.getState().draft.project.project_name).toBe("Checkout redesign");
    expect(useDraftStore.getState().isDirty).toBe(false);
  });

  it("rejects invalid imported JSON text", async () => {
    const { useDraftStore } = await loadDraftStore();

    expect(() => useDraftStore.getState().parseImportedDraftText("{not-json")).toThrow(
      "Draft JSON is invalid."
    );
  });

  it("parses valid imported JSON text into a wizard-ready draft", async () => {
    const importedDraft = cloneInitialState();
    importedDraft.project.project_name = "Imported draft";
    importedDraft.setup.traffic_split = "60,40";

    const { useDraftStore } = await loadDraftStore();
    const parsed = useDraftStore.getState().parseImportedDraftText(
      JSON.stringify(buildDraftTransferFile(importedDraft))
    );

    expect(parsed.project.project_name).toBe("Imported draft");
    expect(parsed.setup.traffic_split).toBe("60,40");
  });
});
