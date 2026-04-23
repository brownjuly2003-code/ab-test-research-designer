import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import ru from "./ru.json";
import de from "./de.json";
import es from "./es.json";
import fr from "./fr.json";
import zh from "./zh.json";
import ar from "./ar.json";

const SUPPORTED_LANGUAGES = ["en", "ru", "de", "es", "fr", "zh", "ar"] as const;
type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

function resolveFallbackLanguage(code?: string): [SupportedLanguage, "en"] | ["en"] {
  if (!code) {
    return ["en"];
  }

  const normalized = code.replace("_", "-").toLowerCase();
  const primary = normalized.split("-", 1)[0];

  if ((SUPPORTED_LANGUAGES as readonly string[]).includes(primary)) {
    if (primary === "en") {
      return ["en"];
    }

    return [primary as SupportedLanguage, "en"];
  }

  return ["en"];
}

const resources = {
  en: { common: en },
  ru: { common: ru },
  de: { common: de },
  es: { common: es },
  fr: { common: fr },
  zh: { common: zh },
  ar: { common: ar }
} as const;

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    supportedLngs: SUPPORTED_LANGUAGES,
    nonExplicitSupportedLngs: true,
    fallbackLng: resolveFallbackLanguage,
    defaultNS: "common",
    ns: ["common"],
    load: "languageOnly",
    cleanCode: true,
    detection: {
      order: ["querystring", "localStorage", "navigator"],
      lookupQuerystring: "lang",
      lookupLocalStorage: "ab-test:language",
      caches: ["localStorage"]
    },
    interpolation: {
      escapeValue: false
    },
    react: {
      useSuspense: false
    }
  });

export function t(key: string, vars?: Record<string, unknown>): string {
  return i18n.t(key, vars);
}

export default i18n;
