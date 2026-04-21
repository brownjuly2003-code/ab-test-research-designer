import { useTranslation } from "react-i18next";

import ErrorBoundary from "./components/ErrorBoundary";
import SidebarPanel from "./components/SidebarPanel";
import WizardPanel, { GlobalSideEffects, OnboardingPanel } from "./components/WizardPanel";
import { useDraftStore } from "./stores/draftStore";
import { useProjectStore } from "./stores/projectStore";
import { useThemeStore } from "./stores/themeStore";
import { useWizardStore } from "./stores/wizardStore";

export default function App() {
  const { t, i18n } = useTranslation();
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const showOnboarding = useWizardStore((state) => state.showOnboarding);
  const step = useWizardStore((state) => state.step);
  const isDirty = useDraftStore((state) => state.isDirty);
  const activeProjectId = useProjectStore((state) => state.activeProjectId);
  const isEmptyState = showOnboarding && !isDirty && !activeProjectId && step === 0;
  const language = i18n.resolvedLanguage === "ru" ? "ru" : "en";

  async function handleLanguageChange(nextLanguage: "en" | "ru") {
    window.localStorage.setItem("ab-test:language", nextLanguage);
    await i18n.changeLanguage(nextLanguage);
  }

  return (
    <>
      <a href="#main-content" className="skip-link">{t("app.skipToMainContent")}</a>
      <main id="main-content" className="page" tabIndex={-1}>
        <div className="shell">
          <GlobalSideEffects />
          <section className="hero">
            <div className="hero-header">
              <div className="hero-copy">
                <span className="eyebrow">{t("app.eyebrow")}</span>
                <h1>{t("app.title")}</h1>
                <p>{t("app.tagline")}</p>
              </div>
              <div style={{ display: "grid", gap: 12 }}>
                <div className="theme-toggle" role="group" aria-label={t("app.language.ariaLabel")}>
                  <span className="theme-toggle-label">{t("app.language.label")}</span>
                  <div className="theme-toggle-buttons">
                    {(["en", "ru"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        className="theme-toggle-button"
                        aria-label={t(`app.language.options.${option}`)}
                        aria-pressed={language === option}
                        title={t(`app.language.options.${option}`)}
                        onClick={() => void handleLanguageChange(option)}
                      >
                        {option.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="theme-toggle" role="group" aria-label={t("app.theme.ariaLabel")}>
                  <span className="theme-toggle-label">{t("app.theme.label")}</span>
                  <div className="theme-toggle-buttons">
                    {(["light", "dark", "system"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        className="theme-toggle-button"
                        aria-label={t(`app.theme.buttonAria.${option}`)}
                        aria-pressed={theme === option}
                        title={t(`app.theme.buttonAria.${option}`)}
                        onClick={() => setTheme(option)}
                      >
                        {t(`app.theme.options.${option}`)}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </section>
          <div className="grid">
            {isEmptyState ? <OnboardingPanel /> : <ErrorBoundary><WizardPanel /></ErrorBoundary>}
            <ErrorBoundary><SidebarPanel /></ErrorBoundary>
          </div>
        </div>
      </main>
    </>
  );
}
