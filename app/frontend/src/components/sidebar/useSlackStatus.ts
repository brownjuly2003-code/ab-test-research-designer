import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { requestSlackStatus, type SlackStatusResponse } from "../../lib/api";

/**
 * Slack install status. Fetched when the API keys tab mounts, which is the same moment the
 * previous single-component sidebar fetched it (its effect was gated on `activeTab`).
 */
export function useSlackStatus() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<SlackStatusResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError("");
    void requestSlackStatus()
      .then((response) => setStatus(response))
      .catch((caught) => {
        setStatus(null);
        setError(caught instanceof Error ? caught.message : t("sidebarPanel.slackApp.statusUnavailable"));
      })
      .finally(() => setLoading(false));
  }, [t]);

  return { status, error, loading };
}
