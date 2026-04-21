import { useEffect, useRef, useState } from "react";

import { t } from "../i18n";
import styles from "./InlineConfirmButton.module.css";

type InlineConfirmButtonProps = {
  onConfirm: () => void;
  label: string;
  confirmLabel?: string;
  countdownSeconds?: number;
  variant?: "danger" | "warning";
  ariaLabel?: string;
  disabled?: boolean;
};

export default function InlineConfirmButton({
  onConfirm,
  label,
  confirmLabel = t("inlineConfirmButton.confirmLabel"),
  countdownSeconds = 3,
  variant = "danger",
  ariaLabel,
  disabled = false
}: InlineConfirmButtonProps) {
  const [confirming, setConfirming] = useState(false);
  const [count, setCount] = useState(countdownSeconds);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function cancel() {
    setConfirming(false);
    setCount(countdownSeconds);
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function confirm() {
    cancel();
    onConfirm();
  }

  function startConfirm() {
    cancel();
    setConfirming(true);
    setCount(countdownSeconds);
    timerRef.current = setInterval(() => {
      setCount((current) => {
        if (current <= 1) {
          cancel();
          return countdownSeconds;
        }

        return current - 1;
      });
    }, 1000);
  }

  useEffect(() => () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (disabled) {
      cancel();
    }
  }, [disabled, countdownSeconds]);

  useEffect(() => {
    if (!confirming) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!(event.target instanceof Node) || buttonRef.current?.contains(event.target)) {
        return;
      }

      cancel();
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [confirming, countdownSeconds]);

  return (
    <button
      ref={buttonRef}
      type="button"
      className={[styles.button, confirming ? styles[variant] : styles.secondary].join(" ")}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => {
        if (confirming) {
          confirm();
          return;
        }

        startConfirm();
      }}
    >
      {confirming ? `${confirmLabel} (${String(count)})` : label}
    </button>
  );
}
