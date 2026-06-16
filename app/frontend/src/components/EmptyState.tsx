import { useTranslation } from "react-i18next";

import styles from "./EmptyState.module.css";

type EmptyStateProps = {
  onNewExperiment: () => void;
  onLoadExample: () => void;
  onImportProject: () => void;
};

export default function EmptyState({
  onNewExperiment,
  onLoadExample,
  onImportProject
}: EmptyStateProps) {
  const { t } = useTranslation();

  return (
    <section className={styles.root} aria-label={t("empty_state.ariaLabel")}>
      <span className={styles.eyebrow}>{t("empty_state.eyebrow")}</span>
      <h1 className={styles.title}>{t("empty_state.title")}</h1>
      <p className={styles.subtitle}>{t("empty_state.subtitle")}</p>

      <div className={styles.actions}>
        <button type="button" className={`btn primary ${styles.primary}`} onClick={onNewExperiment}>
          {t("empty_state.new_experiment")}
        </button>
        <button type="button" className={`btn secondary ${styles.secondary}`} onClick={onLoadExample}>
          {t("empty_state.load_example")}
        </button>
      </div>

      <button type="button" className={styles.importLink} onClick={onImportProject}>
        {t("empty_state.import_project")}
      </button>
    </section>
  );
}
