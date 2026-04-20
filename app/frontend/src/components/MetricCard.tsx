import type { ReactNode } from "react";

import Icon from "./Icon";
import styles from "./MetricCard.module.css";

type MetricCardProps = {
  icon: "activity" | "check" | "clock" | "warning";
  title: string;
  value: string;
  subtitle: string;
  meta?: string;
  tone?: "default" | "warning";
  badge?: ReactNode;
};

export default function MetricCard({
  icon,
  title,
  value,
  subtitle,
  meta,
  tone = "default",
  badge
}: MetricCardProps) {
  const cardClassName = [styles["metric-card"], tone === "warning" ? styles["metric-card-warning"] : ""].filter(Boolean).join(" ");

  return (
    <div className={cardClassName}>
      <div className={styles["metric-card-top"]}>
        <span className={styles["metric-icon"]}>
          <Icon name={icon} />
        </span>
        <span className={styles["metric-title"]}>{title}</span>
        {badge ? <span className={styles["metric-badge"]}>{badge}</span> : null}
      </div>
      <div className={styles["metric-value"]}>{value}</div>
      <div className={styles["metric-subtitle"]}>{subtitle}</div>
      {meta ? <div className={styles["metric-meta"]}>{meta}</div> : null}
    </div>
  );
}
