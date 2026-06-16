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
      <div className={styles.copy}>
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
      </div>

      {/* Illustrative sample of the plan the tool produces; decorative, hidden from a11y tree. */}
      <aside className={styles.preview} aria-hidden="true">
        <div className={styles.previewSplit}>
          <span className={styles.segA}>A</span>
          <span className={styles.segB}>B</span>
        </div>
        <dl className={styles.previewRows}>
          <div className={styles.previewRow}>
            <dt>{t("results.sample_size_per_variant")}</dt>
            <dd>4,317</dd>
          </div>
          <div className={styles.previewRow}>
            <dt>{t("results.duration_days")}</dt>
            <dd>14</dd>
          </div>
          <div className={styles.previewRow}>
            <dt>{t("results.total_sample_size")}</dt>
            <dd>12,951</dd>
          </div>
        </dl>
      </aside>
    </section>
  );
}
