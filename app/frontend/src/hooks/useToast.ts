import { useCallback, useEffect, useRef, useState } from "react";

export type ToastType = "success" | "error" | "warning" | "info";

export type Toast = {
  id: string;
  type: ToastType;
  message: string;
  autoDismiss?: number;
};

function createToastId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }

  return `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const removeToast = useCallback((id: string) => {
    const timer = timersRef.current[id];
    if (timer) {
      clearTimeout(timer);
      delete timersRef.current[id];
    }

    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const addToast = useCallback((type: ToastType, message: string, autoDismiss?: number) => {
    const id = createToastId();
    const resolvedAutoDismiss =
      typeof autoDismiss === "number"
        ? autoDismiss
        : type === "error"
          ? 0
          : 5000;

    setToasts((current) => [...current, { id, type, message, autoDismiss: resolvedAutoDismiss }]);

    if (resolvedAutoDismiss > 0) {
      timersRef.current[id] = setTimeout(() => {
        removeToast(id);
      }, resolvedAutoDismiss);
    }

    return id;
  }, [removeToast]);

  useEffect(() => () => {
    Object.values(timersRef.current).forEach((timer) => clearTimeout(timer));
    timersRef.current = {};
  }, []);

  return {
    toasts,
    addToast,
    removeToast
  };
}
