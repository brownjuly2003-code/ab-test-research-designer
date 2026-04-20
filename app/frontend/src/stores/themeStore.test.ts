// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const themeStorageKey = "ab-test:theme";
const legacyThemeStorageKey = "ab-test-research-designer:theme:v1";

async function loadThemeStore() {
  vi.resetModules();
  return import("./themeStore");
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.style.removeProperty("color-scheme");
});

describe("themeStore", () => {
  it("initializes from localStorage", async () => {
    window.localStorage.setItem(themeStorageKey, "dark");

    const { useThemeStore } = await loadThemeStore();

    expect(useThemeStore.getState().theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("setTheme persists the selected theme", async () => {
    const { useThemeStore } = await loadThemeStore();

    useThemeStore.getState().setTheme("dark");

    expect(useThemeStore.getState().theme).toBe("dark");
    expect(window.localStorage.getItem(themeStorageKey)).toBe("dark");
    expect(window.localStorage.getItem(legacyThemeStorageKey)).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("toggleTheme flips between light and dark", async () => {
    const { useThemeStore } = await loadThemeStore();

    useThemeStore.getState().setTheme("light");
    useThemeStore.getState().toggleTheme();
    expect(useThemeStore.getState().theme).toBe("dark");

    useThemeStore.getState().toggleTheme();
    expect(useThemeStore.getState().theme).toBe("light");
  });
});
