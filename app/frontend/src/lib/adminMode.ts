// Operator/admin surfaces (saved-project management, backend status, API keys,
// webhooks, workspace import/export, diagnostics, audit log) are hidden from the
// public app. They stay one query param away for the owner: open with `?admin=1`
// (persisted to localStorage) and `?admin=0` to leave operator mode again.
export function isAdminMode(): boolean {
  try {
    const flag = new URLSearchParams(window.location.search).get("admin");
    if (flag === "1" || flag === "true") {
      window.localStorage.setItem("ab-test:admin", "1");
      return true;
    }
    if (flag === "0" || flag === "false") {
      window.localStorage.removeItem("ab-test:admin");
      return false;
    }
    return window.localStorage.getItem("ab-test:admin") === "1";
  } catch {
    return false;
  }
}
