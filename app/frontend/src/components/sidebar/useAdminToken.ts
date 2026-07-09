import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { clearAdminSessionToken, hasAdminSessionToken, listApiKeysRequest, setAdminSessionToken } from "../../lib/api";
import type { SidebarTab } from "./types";

/**
 * Admin session token. Straddles the shell/tab boundary on purpose: the System tab renders
 * the form, but the shell needs `configured` to decide whether the API keys tab exists at all,
 * and a successful save jumps the operator straight to that tab.
 */
export function useAdminToken(activeTab: SidebarTab, setActiveTab: (tab: SidebarTab) => void) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState("");
  const [configured, setConfigured] = useState(hasAdminSessionToken());
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (configured || activeTab !== "apiKeys") {
      return;
    }
    setActiveTab("system");
  }, [activeTab, configured]);

  async function onSave() {
    const normalizedToken = draft.trim();
    if (!normalizedToken) {
      return;
    }

    setStatus(t("sidebarPanel.status.verifyingAdminToken"));
    setAdminSessionToken(normalizedToken);

    try {
      await listApiKeysRequest();
      setConfigured(true);
      setDraft("");
      setStatus(t("sidebarPanel.status.adminTokenAccepted"));
      setActiveTab("apiKeys");
    } catch (error) {
      clearAdminSessionToken();
      setConfigured(false);
      setStatus(error instanceof Error ? error.message : t("sidebarPanel.status.adminTokenVerificationFailed"));
    }
  }

  function onClear() {
    clearAdminSessionToken();
    setConfigured(false);
    setDraft("");
    setStatus(t("sidebarPanel.status.adminTokenCleared"));
  }

  return { draft, setDraft, configured, status, onSave, onClear };
}

export type AdminToken = ReturnType<typeof useAdminToken>;
