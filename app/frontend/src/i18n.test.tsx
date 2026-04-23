// @vitest-environment jsdom

import { act } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "./i18n";
import { flushEffects, renderIntoDocument } from "./test/dom";

function I18nProbe() {
  const { t } = useTranslation();

  return <div>{t("app.title")}</div>;
}

describe("frontend i18n", () => {
  beforeEach(async () => {
    window.localStorage.clear();
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("supports all shipped locales", () => {
    expect(i18n.options.supportedLngs).toEqual(expect.arrayContaining(["en", "ru", "de", "es", "fr", "zh", "ar"]));
  });

  it("loads a target locale asynchronously before switching language", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy.mockClear();

    try {
      await act(async () => {
        await i18n.changeLanguage("fr");
      });

      expect(fetchSpy).toHaveBeenCalledWith("/locales/fr.json");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it.each([
    { locale: "ru", expectedTitle: "Конструктор исследований A/B-тестов" },
    { locale: "de", expectedTitle: "A/B-Test-Forschungsdesigner" },
    { locale: "es", expectedTitle: "Diseñador de investigación de pruebas A/B" },
    { locale: "fr", expectedTitle: "Concepteur de recherche pour tests A/B" },
    { locale: "zh", expectedTitle: "A/B 实验研究设计器" },
    { locale: "ar", expectedTitle: "مصمم أبحاث اختبارات A/B" }
  ] as const)("renders translated text after changeLanguage('$locale')", async ({ locale, expectedTitle }) => {
    const view = await renderIntoDocument(
      <I18nextProvider i18n={i18n}>
        <I18nProbe />
      </I18nextProvider>
    );

    try {
      expect(view.container.textContent).toContain("AB Test Research Designer");

      await act(async () => {
        await i18n.changeLanguage(locale);
      });
      await flushEffects();

      expect(view.container.textContent).toContain(expectedTitle);
    } finally {
      await view.unmount();
    }
  });
});
