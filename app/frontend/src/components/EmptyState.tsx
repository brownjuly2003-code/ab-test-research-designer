import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { isAdminMode } from "../lib/adminMode";
import { listProjectsRequest } from "../lib/api";
import type { SavedProject } from "../lib/experiment";
import { useProjectStore } from "../stores/projectStore";
import styles from "./EmptyState.module.css";

const DEMO_PROJECT_PREFIX = "Demo - ";
const MAX_DEMO_CARDS = 4;

type EmptyStateProps = {
  onNewExperiment: () => void;
  onLoadExample: () => void;
  onImportProject: () => void;
  onOpenDemo: (projectId: string, projectName: string) => void;
};

export default function EmptyState({
  onNewExperiment,
  onLoadExample,
  onImportProject,
  onOpenDemo
}: EmptyStateProps) {
  const { t } = useTranslation();
  const isReadOnlySession = useProjectStore((state) => state.isReadOnlySession);
  const [demoProjects, setDemoProjects] = useState<SavedProject[]>([]);
  const [openingDemoId, setOpeningDemoId] = useState<string | null>(null);

  useEffect(() => {
    // Demo cards are the guest landing surface; the operator (`?admin=1`) already
    // has the full project list in the sidebar.
    if (isAdminMode()) {
      return;
    }
    let cancelled = false;
    listProjectsRequest({ limit: 50 })
      .then((projects) => {
        if (cancelled) {
          return;
        }
        setDemoProjects(
          projects
            .filter((project) => project.project_name.startsWith(DEMO_PROJECT_PREFIX) && !project.is_archived)
            .slice(0, MAX_DEMO_CARDS)
        );
      })
      .catch(() => {
        // No backend or no read access: the landing simply shows no demo cards.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function openDemo(project: SavedProject) {
    setOpeningDemoId(project.id);
    try {
      onOpenDemo(project.id, project.project_name);
    } finally {
      setOpeningDemoId(null);
    }
  }

  function metricTypeLabel(metricType: SavedProject["metric_type"]): string | null {
    if (!metricType) {
      return null;
    }
    return t(`projectListFilters.metricType.${metricType}`);
  }

  const hasDemos = demoProjects.length > 0;

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

        {isReadOnlySession ? null : (
          <button type="button" className={styles.importLink} onClick={onImportProject}>
            {t("empty_state.import_project")}
          </button>
        )}
      </div>

      {hasDemos ? (
        <div className={styles.demos} aria-label={t("empty_state.demos.heading")}>
          <div className={styles.demosHeading}>
            <h2 className={styles.demosTitle}>{t("empty_state.demos.heading")}</h2>
            <p className={styles.demosSubtitle}>{t("empty_state.demos.subtitle")}</p>
          </div>
          <div className={styles.demoGrid}>
            {demoProjects.map((project) => (
              <button
                key={project.id}
                type="button"
                className={styles.demoCard}
                disabled={openingDemoId !== null}
                onClick={() => void openDemo(project)}
              >
                <span className={styles.demoTags}>
                  {metricTypeLabel(project.metric_type) ? (
                    <span className={styles.demoTag}>{metricTypeLabel(project.metric_type)}</span>
                  ) : null}
                  {project.has_analysis_snapshot ? (
                    <span className={styles.demoTagQuiet}>{t("empty_state.demos.analyzed")}</span>
                  ) : null}
                </span>
                <span className={styles.demoName}>
                  {project.project_name.slice(DEMO_PROJECT_PREFIX.length) || project.project_name}
                </span>
                {project.hypothesis ? <span className={styles.demoHypothesis}>{project.hypothesis}</span> : null}
                <span className={styles.demoMeta}>
                  {typeof project.duration_days === "number"
                    ? t("empty_state.demos.durationDays", { count: project.duration_days })
                    : null}
                  <span className={styles.demoOpen}>
                    {openingDemoId === project.id ? t("empty_state.demos.opening") : t("empty_state.demos.open")}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <p className={styles.facts}>{t("empty_state.facts")}</p>
        </div>
      ) : (
        /* Illustrative sample of the plan the tool produces; decorative, hidden from a11y tree. */
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
      )}
    </section>
  );
}
