import { useState, type ReactNode } from "react";

import Icon from "./Icon";

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

  return (
    <section className="accordion">
      <button
        className="accordion-toggle"
        type="button"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="accordion-title-group">
          <Icon name="chevron" className={`icon accordion-chevron ${open ? "open" : ""}`} />
          <span>{title}</span>
        </span>
        {badge ? <span className={`accordion-badge accordion-badge-${badgeColor}`}>{badge}</span> : null}
      </button>
      <div className={`accordion-body ${open ? "open" : "collapsed"}`}>
        <div className="accordion-inner">{children}</div>
      </div>
    </section>
  );
}
