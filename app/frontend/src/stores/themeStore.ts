import { create } from "zustand";

export type Theme = "light" | "dark" | "system";

export interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  hydrateTheme: () => void;
}

const themeStorageKey = "ab-test:theme";
const legacyThemeStorageKey = "ab-test-research-designer:theme:v1";

function isTheme(value: string | null): value is Theme {
  return value === "light" || value === "dark" || value === "system";
}

function readStoredTheme(): Theme {
  if (typeof window === "undefined") {
    return "light";
  }

  const storedTheme = window.localStorage.getItem(themeStorageKey);
  if (isTheme(storedTheme)) {
    return storedTheme;
  }

  const legacyTheme = window.localStorage.getItem(legacyThemeStorageKey);
  return isTheme(legacyTheme) ? legacyTheme : "light";
}

function persistTheme(theme: Theme) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(themeStorageKey, theme);
    window.localStorage.setItem(legacyThemeStorageKey, theme);
  } catch {}
}

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") {
    return;
  }

  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
    root.style.removeProperty("color-scheme");
    return;
  }

  root.setAttribute("data-theme", theme);
  root.style.colorScheme = theme;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readStoredTheme(),
  setTheme: (theme) => {
    persistTheme(theme);
    applyTheme(theme);
    set({ theme });
  },
  toggleTheme: () => {
    const nextTheme = get().theme === "dark" ? "light" : "dark";
    persistTheme(nextTheme);
    applyTheme(nextTheme);
    set({ theme: nextTheme });
  },
  hydrateTheme: () => {
    const theme = readStoredTheme();
    applyTheme(theme);
    set({ theme });
  }
}));

applyTheme(useThemeStore.getState().theme);
