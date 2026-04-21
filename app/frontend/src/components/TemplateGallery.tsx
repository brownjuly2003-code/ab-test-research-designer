import { useEffect, useRef, useState } from "react";

import { hydrateLoadedPayload, type FullPayload, type TemplateRecord } from "../lib/experiment";
import { listTemplatesRequest, useTemplateRequest } from "../lib/api";

type TemplateGalleryProps = {
  onClose: () => void;
  onApplyTemplate: (draft: FullPayload, templateName: string) => void;
};

const categoryOrder = ["All", "Revenue", "Engagement", "Performance"] as const;

export default function TemplateGallery({ onClose, onApplyTemplate }: TemplateGalleryProps) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [templates, setTemplates] = useState<TemplateRecord[]>([]);
  const [activeCategory, setActiveCategory] = useState<(typeof categoryOrder)[number]>("All");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [usingTemplateId, setUsingTemplateId] = useState<string | null>(null);

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadTemplates() {
      try {
        setLoading(true);
        setError("");
        const loaded = await listTemplatesRequest();
        if (!cancelled) {
          setTemplates(loaded);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : "Template library unavailable.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadTemplates();

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
      cancelled = true;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocusRef.current?.isConnected) {
        previousFocusRef.current.focus();
      }
    };
  }, [onClose]);

  async function handleUseTemplate(templateId: string) {
    try {
      setUsingTemplateId(templateId);
      setError("");
      const template = await useTemplateRequest(templateId);
      onApplyTemplate(hydrateLoadedPayload(template.payload), template.name);
      onClose();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Template apply failed.");
    } finally {
      setUsingTemplateId(null);
    }
  }

  const filteredTemplates = templates.filter((template) => (
    activeCategory === "All" ? true : template.category === activeCategory
  ));

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
        aria-labelledby="template-gallery-title"
        tabIndex={-1}
        style={{
          width: "min(960px, 100%)",
          maxHeight: "min(86vh, 800px)",
          overflow: "auto",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-border)",
          background: "var(--color-bg-card)",
          boxShadow: "var(--shadow-lg)",
          padding: "24px",
          display: "grid",
          gap: "16px"
        }}
      >
        <div className="actions" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 id="template-gallery-title" style={{ margin: 0 }}>Experiment templates</h2>
            <p className="muted" style={{ margin: "8px 0 0" }}>
              Start from a built-in setup and adjust the wizard fields before saving or running analysis.
            </p>
          </div>
          <button ref={closeButtonRef} type="button" className="btn secondary" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="actions" style={{ flexWrap: "wrap" }}>
          {categoryOrder.map((category) => (
            <button
              key={category}
              type="button"
              className={activeCategory === category ? "btn secondary" : "btn ghost"}
              aria-pressed={activeCategory === category}
              onClick={() => setActiveCategory(category)}
            >
              {category}
            </button>
          ))}
        </div>

        {error ? <div className="error">{error}</div> : null}
        {loading ? <p className="muted">Loading templates...</p> : null}

        {!loading ? (
          <div
            style={{
              display: "grid",
              gap: "16px",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))"
            }}
          >
            {filteredTemplates.map((template) => (
              <article
                key={template.id}
                className="card"
                style={{
                  display: "grid",
                  gap: "12px",
                  alignContent: "start"
                }}
              >
                <div className="actions" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <strong>{template.name}</strong>
                    <div className="muted">{template.category}</div>
                  </div>
                  <span className="pill">{template.usage_count} uses</span>
                </div>
                <p className="muted" style={{ margin: 0 }}>{template.description}</p>
                <div className="actions" style={{ flexWrap: "wrap", justifyContent: "flex-start" }}>
                  {template.tags.map((tag) => (
                    <span key={`${template.id}-${tag}`} className="pill">{tag}</span>
                  ))}
                </div>
                <div className="actions" style={{ justifyContent: "space-between", alignItems: "center" }}>
                  {template.built_in ? <span className="muted">Built-in template</span> : <span className="muted">Saved template</span>}
                  <button
                    type="button"
                    className="btn primary"
                    aria-label={`Use template ${template.name}`}
                    disabled={usingTemplateId === template.id}
                    onClick={() => void handleUseTemplate(template.id)}
                  >
                    {usingTemplateId === template.id ? "Applying..." : "Use template"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {!loading && filteredTemplates.length === 0 ? (
          <p className="muted">No templates found for this category.</p>
        ) : null}
      </div>
    </div>
  );
}
