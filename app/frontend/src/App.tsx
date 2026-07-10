import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import ErrorBoundary from "./components/ErrorBoundary";
import SidebarPanel from "./components/SidebarPanel";
import WizardPanel, { GlobalSideEffects, OnboardingPanel } from "./components/WizardPanel";
import { isAdminMode } from "./lib/adminMode";
import { useDraftStore } from "./stores/draftStore";
import { useProjectStore } from "./stores/projectStore";
import { useThemeStore } from "./stores/themeStore";
import { useWizardStore } from "./stores/wizardStore";

const SUPPORTED_LANGUAGES = ["en", "ru", "de", "es", "fr", "zh", "ar"] as const;
type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

function resolveLanguage(candidate: string | undefined): SupportedLanguage {
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(candidate ?? "")
    ? (candidate as SupportedLanguage)
    : "en";
}

export default function App() {
  const { t, i18n } = useTranslation();
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const showOnboarding = useWizardStore((state) => state.showOnboarding);
  const step = useWizardStore((state) => state.step);
  const isDirty = useDraftStore((state) => state.isDirty);
  const activeProjectId = useProjectStore((state) => state.activeProjectId);
  const isEmptyState = showOnboarding && !isDirty && !activeProjectId && step === 0;
  const language = resolveLanguage(i18n.resolvedLanguage);
  const helpHref = language === "en" ? "/help.html" : `/help.${language}.html`;
  // Operator surfaces (saved-project sidebar) are hidden from the public app.
  const [admin] = useState(isAdminMode);

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
  }, [language]);

  async function handleLanguageChange(nextLanguage: SupportedLanguage) {
    window.localStorage.setItem("ab-test:language", nextLanguage);
    await i18n.changeLanguage(nextLanguage);
  }

  return (
    <>
      <a href="#main-content" className="skip-link">{t("app.skipToMainContent")}</a>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="/" aria-label={t("app.title")}>
            <span className="brand-mark" aria-hidden="true">
              <span>A</span>
              <span>B</span>
            </span>
            <span className="brand-text">
              <span className="brand-name">{t("app.title")}</span>
              <span className="brand-tag">{t("app.eyebrow")}</span>
            </span>
          </a>
          <div className="topbar-controls">
            <a className="topbar-link" href={helpHref}>
              {t("app.helpLink")}
            </a>
            <select
              className="lang-select"
              value={language}
              aria-label={t("app.language.ariaLabel")}
              onChange={(event) => void handleLanguageChange(event.target.value as SupportedLanguage)}
            >
              {SUPPORTED_LANGUAGES.map((option) => (
                <option key={option} value={option}>
                  {t(`app.language.options.${option}`)}
                </option>
              ))}
            </select>
            <div className="theme-seg" role="group" aria-label={t("app.theme.ariaLabel")}>
              {(["light", "dark", "system"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  className="theme-seg-button"
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
      </header>
      <main id="main-content" className="page" tabIndex={-1}>
        <div className={admin ? "workspace workspace--admin" : "workspace"}>
          <GlobalSideEffects />
          {isEmptyState ? <OnboardingPanel /> : <ErrorBoundary><WizardPanel /></ErrorBoundary>}
          {admin ? <ErrorBoundary><SidebarPanel /></ErrorBoundary> : null}
        </div>
      </main>
    </>
  );
}
