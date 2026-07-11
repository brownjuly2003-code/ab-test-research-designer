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

// Significant-figures formatter for the small, few-digit statistics shown in result cards — test
// statistics, effect sizes, hazard ratios, rates, achieved power. It trims trailing zeros so a value
// never advertises more precision than it carries (0.2000 -> "0.2", 12.3456 -> "12.3"), while small
// magnitudes keep their meaningful digits (0.012345 -> "0.0123"). This is the decimal counterpart to
// formatCount (which groups integer counts); statistics keep a "." decimal separator to match the
// rest of the numeric result UI. Non-finite input falls back to a plain string.
export function formatStat(value: number, sig = 3): string {
  if (!Number.isFinite(value)) {
    return String(value);
  }
  if (value === 0) {
    return "0";
  }
  // `toPrecision` yields `sig` significant digits; the Number() round-trip drops trailing zeros and,
  // across the magnitudes shown here (roughly 1e-4 .. 1e4) never leaves exponential notation.
  return String(Number(value.toPrecision(sig)));
}

// p-value formatter. Shows "< 0.001" for very small values — a plain toFixed(6) collapsed a genuine
// 1e-9 to a misleading "0.000000" that reads as exactly zero — and otherwise up to four decimals with
// trailing zeros trimmed (0.032000 -> "0.032", 0.0012 -> "0.0012"). Non-finite input falls back to a
// plain string.
export function formatPValue(value: number): string {
  if (!Number.isFinite(value)) {
    return String(value);
  }
  if (value < 0.001) {
    return "< 0.001";
  }
  return String(Number(value.toFixed(4)));
}
