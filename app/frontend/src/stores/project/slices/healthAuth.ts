/** Backend health, diagnostics, and session API token. */
import {
  clearApiSessionToken,
  hasApiSessionToken,
  requestDiagnostics,
  requestHealth,
  setApiSessionToken
} from "../../../lib/api";
import { resolveErrorMessage } from "../helpers";
import type {
  ApplyStoreUpdate,
  ProjectStoreActions,
  ProjectStoreGet
} from "../types";

export function createHealthAuthActions(
  applyStoreUpdate: ApplyStoreUpdate,
  get: ProjectStoreGet
): Pick<
  ProjectStoreActions,
  | "loadBackendHealth"
  | "loadBackendDiagnostics"
  | "refreshBackendState"
  | "updateApiTokenDraft"
  | "saveRuntimeApiToken"
  | "clearRuntimeApiToken"
> {
  return {
    loadBackendHealth: async () => {
      applyStoreUpdate({ loadingHealth: true });

      try {
        const health = await requestHealth();
        applyStoreUpdate({
          backendHealth: health,
          healthError: ""
        });
        return health;
      } catch (error) {
        applyStoreUpdate({
          backendHealth: null,
          healthError: resolveErrorMessage(error, "Unexpected backend health error")
        });
        return null;
      } finally {
        applyStoreUpdate({ loadingHealth: false });
      }
    },
    loadBackendDiagnostics: async () => {
      applyStoreUpdate({ loadingDiagnostics: true });

      try {
        const diagnostics = await requestDiagnostics();
        applyStoreUpdate({
          backendDiagnostics: diagnostics,
          diagnosticsError: ""
        });
        return diagnostics;
      } catch (error) {
        applyStoreUpdate({
          backendDiagnostics: null,
          diagnosticsError: resolveErrorMessage(error, "Unexpected backend diagnostics error")
        });
        return null;
      } finally {
        applyStoreUpdate({ loadingDiagnostics: false });
      }
    },
    refreshBackendState: async (options = {}) => {
      get().clearProjectError();
      const [health, diagnostics] = await Promise.all([
        get().loadBackendHealth(),
        get().loadBackendDiagnostics()
      ]);

      if (health || diagnostics) {
        const loaded = await get().refreshProjects();
        if (!loaded && options.suppressProjectErrors) {
          get().clearProjectError();
        }
      }

      return diagnostics;
    },
    updateApiTokenDraft: (value) => {
      applyStoreUpdate({ apiTokenDraft: value });
    },
    saveRuntimeApiToken: async () => {
      get().clearProjectError();
      const normalizedToken = get().apiTokenDraft.trim();

      if (!normalizedToken) {
        return null;
      }

      setApiSessionToken(normalizedToken);
      applyStoreUpdate({
        apiTokenStatus: "Verifying token against backend diagnostics...",
        apiTokenConfigured: hasApiSessionToken(),
        apiTokenDraft: ""
      });

      const diagnostics = await get().refreshBackendState({ suppressProjectErrors: true });

      if (!diagnostics) {
        const message = "Token saved in this browser session, but backend access is still not confirmed.";
        applyStoreUpdate({ apiTokenStatus: message });
        return message;
      }

      if (!diagnostics.auth.enabled) {
        const message = "Backend is open. A session token is not required for this runtime.";
        applyStoreUpdate({ apiTokenStatus: message });
        return message;
      }

      const message = diagnostics.auth.session_can_write
        ? "Token accepted. Write-capable backend access is available in this browser session."
        : "Token accepted, but this backend session remains read-only.";

      applyStoreUpdate({ apiTokenStatus: message });
      return message;
    },
    clearRuntimeApiToken: async () => {
      get().clearProjectError();
      clearApiSessionToken();
      applyStoreUpdate({
        apiTokenConfigured: false,
        apiTokenDraft: ""
      });
      get().resetProjectSelection();
      applyStoreUpdate({
        savedProjects: []
      });
      const message = "Token cleared from this browser session.";
      applyStoreUpdate({ apiTokenStatus: message });
      await get().refreshBackendState({ suppressProjectErrors: true });
      return message;
    },

  };
}
