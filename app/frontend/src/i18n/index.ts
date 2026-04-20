import en from "./en.json";

const translations = en;

export function t(key: string, vars?: Record<string, string | number>): string {
  const parts = key.split(".");
  let value: unknown = translations;

  for (const part of parts) {
    if (typeof value !== "object" || value === null) {
      return key;
    }

    value = Reflect.get(value, part);
    if (value === undefined) {
      return key;
    }
  }

  if (typeof value !== "string") {
    return key;
  }

  if (!vars) {
    return value;
  }

  return value.replace(/\{(\w+)\}/g, (_match, variable) => String(vars[variable] ?? `{${variable}}`));
}
