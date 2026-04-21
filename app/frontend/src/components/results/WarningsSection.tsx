import { useTranslation } from "react-i18next";

import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import styles from "./WarningsSection.module.css";

export default function WarningsSection() {
  const { t } = useTranslation();
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = selectedHistoryAnalysis ?? analysisResult;
  const warnings = displayedAnalysis?.calculations.warnings ?? [];

  return (
    <div className={styles["warning-stack"]}>
      {warnings.length > 0 ? (
        warnings.map((warning) => (
          <div
            key={String(warning.code)}
            className={[styles["warning-row"], styles[`severity-${String(warning.severity)}`]].filter(Boolean).join(" ")}
          >
            <div className={styles["warning-title"]}>
              <Icon
                name={warning.severity === "high" ? "warning" : warning.severity === "medium" ? "info" : "check"}
                className="icon icon-inline"
              />
              <strong>{String(warning.code)}</strong>
            </div>
            <div className="muted">{String(warning.message)}</div>
          </div>
        ))
      ) : (
        <div className={[styles["warning-row"], styles["severity-low"]].join(" ")}>
          <div className={styles["warning-title"]}>
            <Icon name="check" className="icon icon-inline" />
            <strong>{t("results.warnings.noneTitle")}</strong>
          </div>
          <div className="muted">{t("results.warnings.noneDescription")}</div>
        </div>
      )}
    </div>
  );
}
