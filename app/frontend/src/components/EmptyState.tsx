import Icon from "./Icon";
import styles from "./EmptyState.module.css";

type EmptyStateProps = {
  onNewExperiment: () => void;
  onLoadExample: () => void;
  onImportProject: () => void;
};

const actionCards = [
  {
    title: "New experiment",
    description: "Start from scratch",
    icon: "plus" as const,
    accent: "rgba(15, 118, 110, 0.12)"
  },
  {
    title: "Load example",
    description: "See a filled experiment in 1 click",
    icon: "activity" as const,
    accent: "rgba(79, 70, 229, 0.12)"
  },
  {
    title: "Import project",
    description: "Restore from a workspace backup",
    icon: "download" as const,
    accent: "rgba(245, 158, 11, 0.14)"
  }
];

export default function EmptyState({
  onNewExperiment,
  onLoadExample,
  onImportProject
}: EmptyStateProps) {
  const actions = [onNewExperiment, onLoadExample, onImportProject];

  return (
    <section className={styles.root} aria-label="Onboarding">
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
            Start here
          </span>
          <h2 style={{ margin: 0, fontSize: "clamp(30px, 5vw, 42px)", lineHeight: 0.95 }}>
            Plan your A/B experiment
          </h2>
          <p className={styles.description} style={{ margin: 0, fontSize: 14 }}>
            Deterministic calculations. Local-first. No cloud required.
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
