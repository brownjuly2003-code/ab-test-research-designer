import { useId, useState } from "react";
import { autoUpdate, flip, offset, shift, useFloating } from "@floating-ui/react-dom";
import { createPortal } from "react-dom";

import Icon from "./Icon";
import styles from "./Tooltip.module.css";

type TooltipProps = {
  content?: string;
  text?: string;
};

export default function Tooltip({ content, text }: TooltipProps) {
  const tooltipText = content ?? text ?? "";
  const tooltipId = useId();
  const [isHovered, setIsHovered] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const isVisible = isHovered || isFocused;
  const { refs, floatingStyles } = useFloating({
    placement: "top",
    strategy: "fixed",
    middleware: [offset(10), flip({ padding: 12 }), shift({ padding: 12 })],
    whileElementsMounted: autoUpdate
  });

  if (!tooltipText) {
    return null;
  }

  return (
    <>
      <span
        ref={refs.setReference}
        className={styles["tooltip-trigger"]}
        role="note"
        tabIndex={0}
        aria-describedby={isVisible ? tooltipId : undefined}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
      >
        <Icon name="info" className={styles["field-info-icon"]} />
        <span className={styles["sr-only"]}>{tooltipText}</span>
      </span>
      {isVisible
        ? createPortal(
            <span
              id={tooltipId}
              role="tooltip"
              ref={refs.setFloating}
              style={floatingStyles}
              className={styles["tooltip-popup"]}
            >
              {tooltipText}
            </span>,
            document.body
          )
        : null}
    </>
  );
}
