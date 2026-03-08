import type { ReactNode } from "react";

import Icon from "./Icon";

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
  return (
    <div className={`metric-card metric-card-${tone}`}>
      <div className="metric-card-top">
        <span className="metric-icon">
          <Icon name={icon} />
        </span>
        <span className="metric-title">{title}</span>
        {badge ? <span className="metric-badge">{badge}</span> : null}
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-subtitle">{subtitle}</div>
      {meta ? <div className="metric-meta">{meta}</div> : null}
    </div>
  );
}
