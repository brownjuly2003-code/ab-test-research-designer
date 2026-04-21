import { useTranslation } from "react-i18next";

import Icon from "./Icon";
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
  const actions = [onNewExperiment, onLoadExample, onImportProject];
  const actionCards = [
    {
      title: t("empty_state.new_experiment"),
      description: t("empty_state.descriptions.new_experiment"),
      icon: "plus" as const,
      accent: "rgba(15, 118, 110, 0.12)"
    },
    {
      title: t("empty_state.load_example"),
      description: t("empty_state.descriptions.load_example"),
      icon: "activity" as const,
      accent: "rgba(79, 70, 229, 0.12)"
    },
    {
      title: t("empty_state.import_project"),
      description: t("empty_state.descriptions.import_project"),
      icon: "download" as const,
      accent: "rgba(245, 158, 11, 0.14)"
    }
  ];

  return (
    <section className={styles.root} aria-label={t("empty_state.ariaLabel")}>
      <div
        style={{
          display: "grid",
          gap: 24,
          minHeight: 420,
          alignContent: "center"
        }}
      >
        <div
          style={{
            display: "grid",
            gap: 10,
            maxWidth: 560,
            margin: "0 auto",
            textAlign: "center"
          }}
        >
          <span className={styles.eyebrow} style={{ justifySelf: "center" }}>
            {t("empty_state.eyebrow")}
          </span>
          <h2 style={{ margin: 0, fontSize: "clamp(30px, 5vw, 42px)", lineHeight: 0.95 }}>
            {t("empty_state.title")}
          </h2>
          <p className={styles.description} style={{ margin: 0, fontSize: 14 }}>
            {t("empty_state.subtitle")}
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gap: 16,
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))"
          }}
        >
          {actionCards.map((card, index) => (
            <div
              key={card.title}
              className={styles.card}
              onClick={actions[index]}
            >
              <button type="button" className={styles["action-button"]}>
                <span
                  className={styles["action-icon"]}
                  style={{
                    background: card.accent,
                  }}
                >
                  <Icon name={card.icon} className={styles.icon} />
                </span>
                {card.title}
              </button>
              <span className={styles["card-description"]}>{card.description}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
