(() => {
  try {
    const root = document.documentElement;
    const storedTheme =
      localStorage.getItem("ab-test:theme") ||
      localStorage.getItem("ab-test-research-designer:theme:v1");
    const resolvedTheme =
      storedTheme === "light" || storedTheme === "dark"
        ? storedTheme
        : storedTheme === "system"
          ? null
          : window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";
    if (resolvedTheme) {
      root.setAttribute("data-theme", resolvedTheme);
      root.style.colorScheme = resolvedTheme;
    } else {
      root.removeAttribute("data-theme");
      root.style.removeProperty("color-scheme");
    }
  } catch {}
})();
