import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import ru from "./ru.json";

const resources = {
  en: { common: en },
  ru: { common: ru }
} as const;

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    supportedLngs: ["en", "ru"],
    nonExplicitSupportedLngs: true,
    fallbackLng: "en",
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
