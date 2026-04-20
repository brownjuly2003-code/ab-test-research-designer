import ErrorBoundary from "./components/ErrorBoundary";
import SidebarPanel from "./components/SidebarPanel";
import WizardPanel, { GlobalSideEffects, OnboardingPanel } from "./components/WizardPanel";
import { useDraftStore } from "./stores/draftStore";
import { useProjectStore } from "./stores/projectStore";
import { useThemeStore } from "./stores/themeStore";
import { useWizardStore } from "./stores/wizardStore";

export default function App() {
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const showOnboarding = useWizardStore((state) => state.showOnboarding);
  const step = useWizardStore((state) => state.step);
  const isDirty = useDraftStore((state) => state.isDirty);
  const activeProjectId = useProjectStore((state) => state.activeProjectId);
  const isEmptyState = showOnboarding && !isDirty && !activeProjectId && step === 0;

  return (
    <>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <main id="main-content" className="page" tabIndex={-1}>
        <div className="shell">
          <GlobalSideEffects />
          <section className="hero">
            <div className="hero-header">
              <div className="hero-copy">
                <span className="eyebrow">Local Experiment Planner</span>
                <h1>AB Test Research Designer</h1>
                <p>Fill in experiment context, run deterministic calculations, inspect warnings, and keep AI advice separate from hard math.</p>
              </div>
              <div className="theme-toggle" role="group" aria-label="Theme preference">
                <span className="theme-toggle-label">Theme</span>
                <div className="theme-toggle-buttons">
                  {(["light", "dark", "system"] as const).map((option) => (
                    <button
                      key={option}
                      type="button"
                      className="theme-toggle-button"
                      aria-label={option === "system" ? "System theme" : `${option === "light" ? "Light" : "Dark"} theme`}
                      aria-pressed={theme === option}
                      title={option === "system" ? "System theme" : `${option === "light" ? "Light" : "Dark"} theme`}
                      onClick={() => setTheme(option)}
                    >
                      {option === "light" ? "Light" : option === "dark" ? "Dark" : "Auto"}
                    </button>
                  ))}
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
