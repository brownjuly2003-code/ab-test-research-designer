// Operator/admin surfaces (saved-project management, backend status, API keys,
// webhooks, workspace import/export, diagnostics, audit log) are hidden from the
// public app. They stay one query param away for the owner: open with `?admin=1`
// and `?admin=0` to leave operator mode again.
//
// IMPORTANT: admin mode is scoped to the browser *session* (sessionStorage), never
// localStorage. Visiting `?admin=1` once (e.g. to verify the gating) must NOT make the
// operator panel reappear on the public demo on every later visit. The previous
// implementation persisted to localStorage and stuck forever; we purge that legacy key
// on read so an old flag can never resurface.
const ADMIN_KEY = "ab-test:admin";

export function isAdminMode(): boolean {
  try {
    // Drop the legacy persistent flag so a past `?admin=1` visit cannot keep showing
    // operator surfaces on the public demo.
    window.localStorage.removeItem(ADMIN_KEY);

    const flag = new URLSearchParams(window.location.search).get("admin");
    if (flag === "1" || flag === "true") {
      window.sessionStorage.setItem(ADMIN_KEY, "1");
      return true;
    }
    if (flag === "0" || flag === "false") {
      window.sessionStorage.removeItem(ADMIN_KEY);
      return false;
    }
    return window.sessionStorage.getItem(ADMIN_KEY) === "1";
  } catch {
    return false;
  }
}
