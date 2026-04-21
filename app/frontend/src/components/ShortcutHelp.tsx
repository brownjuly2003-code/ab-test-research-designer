import { useEffect, useRef } from "react";

type ShortcutHelpProps = {
  onClose: () => void;
};

const shortcuts = [
  ["?", "Open keyboard shortcut help"],
  ["/", "Focus saved project search"],
  ["Ctrl+Enter", "Run analysis"],
  ["ArrowLeft / ArrowRight", "Move between wizard steps"],
  ["Ctrl+E", "Export markdown report"],
  ["Ctrl+S", "Save project"],
  ["Ctrl+Shift+D", "Toggle light/dark theme"],
  ["Esc", "Close this dialog"],
] as const;

export default function ShortcutHelp({ onClose }: ShortcutHelpProps) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusableElements = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      ).filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");
      if (focusableElements.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement;
      if (!(activeElement instanceof HTMLElement) || !dialog.contains(activeElement)) {
        event.preventDefault();
        (event.shiftKey ? lastElement : firstElement).focus();
        return;
      }
      if (!event.shiftKey && activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
      if (event.shiftKey && activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocusRef.current?.isConnected) {
        previousFocusRef.current.focus();
      }
    };
  }, []);

  return (
    <div
      aria-hidden="false"
      style={{
        position: "fixed",
        inset: 0,
        background: "color-mix(in srgb, var(--color-text) 20%, transparent)",
        display: "grid",
        placeItems: "center",
        padding: "24px",
        zIndex: 1000
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcut-help-title"
        tabIndex={-1}
        style={{
          width: "min(640px, 100%)",
          maxHeight: "min(80vh, 720px)",
          overflow: "auto",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-border)",
          background: "var(--color-bg-card)",
          boxShadow: "var(--shadow-lg)",
          padding: "24px"
        }}
      >
        <div className="actions" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h2 id="shortcut-help-title" style={{ margin: 0 }}>Keyboard shortcuts</h2>
            <p className="muted" style={{ margin: "8px 0 0" }}>
              Faster navigation and export actions for the wizard.
            </p>
          </div>
          <button ref={closeButtonRef} type="button" className="btn secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Shortcut</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {shortcuts.map(([shortcut, action]) => (
              <tr key={shortcut}>
                <td><strong>{shortcut}</strong></td>
                <td>{action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
