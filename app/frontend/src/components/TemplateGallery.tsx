import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { hydrateLoadedPayload, type FullPayload, type TemplateRecord } from "../lib/experiment";
import { listTemplatesRequest, useTemplateRequest } from "../lib/api";

type TemplateGalleryProps = {
  onClose: () => void;
  onApplyTemplate: (draft: FullPayload, templateName: string) => void;
};

export default function TemplateGallery({ onClose, onApplyTemplate }: TemplateGalleryProps) {
  const { t } = useTranslation();
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [templates, setTemplates] = useState<TemplateRecord[]>([]);
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
          setError(requestError instanceof Error ? requestError.message : t("templateGallery.errors.libraryUnavailable"));
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
      setError(requestError instanceof Error ? requestError.message : t("templateGallery.errors.applyFailed"));
    } finally {
      setUsingTemplateId(null);
    }
  }

  const templatesByCategory = new Map<string, TemplateRecord[]>();
  for (const template of [...templates].sort((left, right) => (
    left.category.localeCompare(right.category) || left.name.localeCompare(right.name)
  ))) {
    const categoryTemplates = templatesByCategory.get(template.category);
    if (categoryTemplates) {
      categoryTemplates.push(template);
      continue;
    }
    templatesByCategory.set(template.category, [template]);
  }
  const groupedTemplates = Array.from(templatesByCategory.entries());

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
            <h2 id="template-gallery-title" style={{ margin: 0 }}>{t("templateGallery.title")}</h2>
            <p className="muted" style={{ margin: "8px 0 0" }}>
              {t("templateGallery.description")}
            </p>
          </div>
          <button ref={closeButtonRef} type="button" className="btn secondary" onClick={onClose}>
            {t("templateGallery.close")}
          </button>
        </div>

        {error ? <div className="error">{error}</div> : null}
        {loading ? <p className="muted">{t("templateGallery.loading")}</p> : null}

        {!loading ? (
          <div style={{ display: "grid", gap: "20px" }}>
            {groupedTemplates.map(([category, categoryTemplates], categoryIndex) => (
              <section
                key={category}
                aria-labelledby={`template-gallery-category-${categoryIndex}`}
                style={{
                  display: "grid",
                  gap: "12px"
                }}
              >
                <div>
                  <h3 id={`template-gallery-category-${categoryIndex}`} style={{ margin: 0 }}>{category}</h3>
                </div>
                <div
                  style={{
                    display: "grid",
                    gap: "16px",
                    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))"
                  }}
                >
                  {categoryTemplates.map((template) => (
                    <article
                      key={template.id}
                      className="card"
                      style={{
                        display: "grid",
                        gap: "12px",
                        alignContent: "start",
                        minWidth: 0
                      }}
                    >
                      <div className="actions" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                          <strong>{template.name}</strong>
                          <div className="muted">{template.category}</div>
                        </div>
                        <span className="pill">{t("templateGallery.usageCount", { count: template.usage_count })}</span>
                      </div>
                      <p className="muted" style={{ margin: 0 }}>{template.description}</p>
                      <div className="actions" style={{ flexWrap: "wrap", justifyContent: "flex-start" }}>
                        {template.tags.map((tag) => (
                          <span key={`${template.id}-${tag}`} className="pill">{tag}</span>
                        ))}
                      </div>
                      <div className="actions" style={{ justifyContent: "space-between", alignItems: "center" }}>
                        {template.built_in ? <span className="muted">{t("templateGallery.builtInTemplate")}</span> : <span className="muted">{t("templateGallery.savedTemplate")}</span>}
                        <button
                          type="button"
                          className="btn primary"
                          aria-label={t("templateGallery.useTemplateAriaLabel", { name: template.name })}
                          disabled={usingTemplateId === template.id}
                          onClick={() => void handleUseTemplate(template.id)}
                        >
                          {usingTemplateId === template.id ? t("templateGallery.applying") : t("templateGallery.useTemplate")}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : null}

        {!loading && groupedTemplates.length === 0 ? (
          <p className="muted">{t("templateGallery.empty")}</p>
        ) : null}
      </div>
    </div>
  );
}
