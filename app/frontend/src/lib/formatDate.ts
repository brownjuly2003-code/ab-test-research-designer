const DEFAULT_OPTIONS: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" };

export function formatLocalizedTimestamp(
  value: string | number | Date,
  options: Intl.DateTimeFormatOptions = DEFAULT_OPTIONS
): string {
  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }

  const locale = typeof document !== "undefined" ? document.documentElement.lang?.trim() || undefined : undefined;
  return new Intl.DateTimeFormat(locale, options).format(parsed);
}
