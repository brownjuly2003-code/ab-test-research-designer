// Locale-aware integer grouping for displayed counts (sample sizes, traffic, user totals).
//
// Two reasons this exists rather than a bare `value.toLocaleString()`:
//   1. Consistency — every count in the UI groups thousands the same way (some call sites used a
//      raw `String(n)` with no grouping, others `toLocaleString()`), so "20345" and "20,345" no
//      longer appear for the same quantity on the same screen.
//   2. Locale correctness — the grouping locale follows the *selected UI language*
//      (`document.documentElement.lang`), not the browser's default, matching how the help pages
//      format numbers. Arabic is pinned to Western (Latin) digits via the `-u-nu-latn` extension,
//      the same choice the localized help widgets make, so a count reads "20,345" and not
//      "٢٠٬٣٤٥" inside an otherwise Latin-digit metric card.
function resolveLocale(locale?: string): string | undefined {
  const lang = locale ?? (typeof document !== "undefined" ? document.documentElement.lang?.trim() : undefined);
  if (!lang) {
    return undefined;
  }
  // Arabic: keep Western digits so counts match the rest of the numeric UI (see help pages).
  return lang === "ar" || lang.startsWith("ar-") ? "ar-u-nu-latn" : lang;
}

// Grouped integer, e.g. 20345 -> "20,345" (en) / "20 345" (ru) / "20.345" (de). Non-finite input
// falls back to a plain string so a bad value never renders as "NaN,NaN".
export function formatCount(value: number, locale?: string): string {
  if (!Number.isFinite(value)) {
    return String(value);
  }
  return new Intl.NumberFormat(resolveLocale(locale), { maximumFractionDigits: 0 }).format(value);
}
