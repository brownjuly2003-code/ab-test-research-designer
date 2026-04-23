import i18n from "i18next";
import type { Resource } from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import type { DetectorOptions } from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

const SUPPORTED_LANGUAGES = ["en", "ru", "de", "es", "fr", "zh", "ar"] as const;
type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];
type LocaleMessages = Record<string, unknown>;

const DEFAULT_LANGUAGE: SupportedLanguage = "en";
const DEFAULT_NAMESPACE = "common";
const DETECTION_OPTIONS: DetectorOptions = {
  order: ["querystring", "localStorage", "navigator"],
  lookupQuerystring: "lang",
  lookupLocalStorage: "ab-test:language",
  caches: ["localStorage"]
};
const localeBundles = new Map<SupportedLanguage, LocaleMessages>();
const pendingLocaleLoads = new Map<SupportedLanguage, Promise<LocaleMessages>>();

function resolveFallbackLanguage(code?: string): SupportedLanguage[] {
  if (!code) {
    return [DEFAULT_LANGUAGE];
  }

  const normalized = code.replace("_", "-").toLowerCase();
  const primary = normalized.split("-", 1)[0];

  if ((SUPPORTED_LANGUAGES as readonly string[]).includes(primary)) {
    if (primary === DEFAULT_LANGUAGE) {
      return [DEFAULT_LANGUAGE];
    }

    return [primary as SupportedLanguage, "en"];
  }

  return [DEFAULT_LANGUAGE];
}

function resolveSupportedLanguage(code?: string): SupportedLanguage {
  return resolveFallbackLanguage(code)[0];
}

function detectInitialLanguage(): SupportedLanguage {
  const detector = new LanguageDetector(undefined, DETECTION_OPTIONS);
  const detected = detector.detect();

  if (Array.isArray(detected)) {
    for (const candidate of detected) {
      const resolved = resolveSupportedLanguage(candidate);
      if (resolved !== DEFAULT_LANGUAGE || candidate?.toLowerCase().startsWith(DEFAULT_LANGUAGE)) {
        return resolved;
      }
    }

    return DEFAULT_LANGUAGE;
  }

  return resolveSupportedLanguage(detected);
}

async function fetchLocale(language: SupportedLanguage): Promise<LocaleMessages> {
  const response = await fetch(`/locales/${language}.json`);

  if (!response.ok) {
    throw new Error(`Failed to load locale '${language}' (${response.status})`);
  }

  return response.json() as Promise<LocaleMessages>;
}

async function loadLocale(language: SupportedLanguage): Promise<LocaleMessages> {
  const cachedBundle = localeBundles.get(language);
  if (cachedBundle) {
    return cachedBundle;
  }

  const pendingLoad = pendingLocaleLoads.get(language);
  if (pendingLoad) {
    return pendingLoad;
  }

  const loadPromise = fetchLocale(language)
    .then((messages) => {
      localeBundles.set(language, messages);

      if (i18n.isInitialized && !i18n.hasResourceBundle(language, DEFAULT_NAMESPACE)) {
        i18n.addResourceBundle(language, DEFAULT_NAMESPACE, messages, true, true);
      }

      return messages;
    })
    .finally(() => {
      pendingLocaleLoads.delete(language);
    });

  pendingLocaleLoads.set(language, loadPromise);
  return loadPromise;
}

async function buildInitialResources(language: SupportedLanguage): Promise<Resource> {
  const initialLanguages = language === DEFAULT_LANGUAGE
    ? [DEFAULT_LANGUAGE]
    : [DEFAULT_LANGUAGE, language];
  const resources: Resource = {};

  for (const candidate of initialLanguages) {
    resources[candidate] = {
      [DEFAULT_NAMESPACE]: await loadLocale(candidate)
    };
  }

  return resources;
}

const baseChangeLanguage = i18n.changeLanguage.bind(i18n);
const initialLanguage = detectInitialLanguage();

i18n.changeLanguage = (async (...args: Parameters<typeof i18n.changeLanguage>) => {
  const [language, callback] = args;

  if (!language) {
    return baseChangeLanguage(language, callback);
  }

  const nextLanguage = resolveSupportedLanguage(language);

  try {
    await loadLocale(nextLanguage);
    return await baseChangeLanguage(nextLanguage, callback);
  } catch {
    await loadLocale(DEFAULT_LANGUAGE);
    return baseChangeLanguage(DEFAULT_LANGUAGE, callback);
  }
}) as typeof i18n.changeLanguage;

await i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    lng: initialLanguage,
    resources: await buildInitialResources(initialLanguage),
    supportedLngs: SUPPORTED_LANGUAGES,
    nonExplicitSupportedLngs: true,
    fallbackLng: resolveFallbackLanguage,
    defaultNS: DEFAULT_NAMESPACE,
    ns: [DEFAULT_NAMESPACE],
    load: "languageOnly",
    cleanCode: true,
    detection: DETECTION_OPTIONS,
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
