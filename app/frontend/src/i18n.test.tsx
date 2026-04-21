// @vitest-environment jsdom

import { act } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

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

  it("renders Russian text after changeLanguage('ru')", async () => {
    const view = await renderIntoDocument(
      <I18nextProvider i18n={i18n}>
        <I18nProbe />
      </I18nextProvider>
    );

    try {
      expect(view.container.textContent).toContain("AB Test Research Designer");

      await act(async () => {
        await i18n.changeLanguage("ru");
      });
      await flushEffects();

      expect(view.container.textContent).toContain("Конструктор исследований A/B-тестов");
    } finally {
      await view.unmount();
    }
  });
});
