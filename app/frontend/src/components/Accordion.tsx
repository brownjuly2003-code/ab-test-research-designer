import { useId, useState, type ReactNode } from "react";

import Icon from "./Icon";
import styles from "./Accordion.module.css";

type AccordionProps = {
  title: string;
  badge?: string;
  badgeColor?: "accent" | "warn" | "danger";
  defaultOpen?: boolean;
  children: ReactNode;
};

export default function Accordion({
  title,
  badge,
  badgeColor = "accent",
  defaultOpen = false,
  children
}: AccordionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId().replace(/:/g, "");
  const headingId = `accordion-heading-${id}`;
  const panelId = `accordion-panel-${id}`;

  return (
    <section className={styles.accordion}>
      <button
        className={styles["accordion-toggle"]}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        id={headingId}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={styles["accordion-title-group"]}>
          <Icon
            name="chevron"
            className={`${styles["accordion-chevron"]} ${open ? styles.open : ""}`}
            aria-hidden={true}
          />
          <span>{title}</span>
        </span>
        {badge ? <span className={`${styles["accordion-badge"]} ${styles[`accordion-badge-${badgeColor}`]}`}>{badge}</span> : null}
      </button>
      <div
        id={panelId}
        role="region"
        aria-labelledby={headingId}
        aria-hidden={!open}
        className={`${styles["accordion-body"]} ${open ? styles.open : ""}`}
      >
        <div className={styles["accordion-inner"]}>{children}</div>
      </div>
    </section>
  );
}
