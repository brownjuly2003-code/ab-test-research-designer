import type { Toast } from "../hooks/useToast";
import Icon from "./Icon";
import styles from "./ToastSystem.module.css";

type ToastSystemProps = {
  toasts: Toast[];
  onDismiss: (id: string) => void;
};

function iconName(type: Toast["type"]): "check" | "warning" | "info" {
  if (type === "success") {
    return "check";
  }

  return type === "error" || type === "warning" ? "warning" : "info";
}

export default function ToastSystem({ toasts, onDismiss }: ToastSystemProps) {
  if (toasts.length === 0) {
    return null;
  }

  return (
    <div className={styles["toast-stack"]} role="alert" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={[styles["toast-item"], styles[`toast-${toast.type}`]].join(" ")}
          role={toast.type === "error" ? "alert" : "status"}
          aria-live={toast.type === "error" ? "assertive" : "polite"}
          aria-atomic="true"
        >
          <div className={styles["toast-item-copy"]}>
            <Icon name={iconName(toast.type)} className={styles.icon} />
            <span>{toast.message}</span>
          </div>
          <button
            type="button"
            className={styles["toast-close"]}
            aria-label="Dismiss toast"
            onClick={() => onDismiss(toast.id)}
          >
            Close
          </button>
        </div>
      ))}
    </div>
  );
}
