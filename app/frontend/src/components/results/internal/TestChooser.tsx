import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  type ObservedBaseMetricType,
  type ObservedChooserAnswers,
  type ObservedTestSelection,
  observedChooserQuestions,
  observedTestLabelKey,
  recommendObservedTest
} from "../observedResultsShared";

type TestChooserProps = {
  baseMetricType: ObservedBaseMetricType;
  onSelectTest: (test: ObservedTestSelection) => void;
};

// A guided "which test should I use?" selector for the post-hoc test toggle. At seven continuous
// options the flat toggle gives no guidance (audit finding 6.2 §7), so a few questions map to a
// recommendation the user can apply with one click. The questions and the decision live in
// observedResultsShared (pure, unit-tested); this component only renders them.
export default function TestChooser({ baseMetricType, onSelectTest }: TestChooserProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [answers, setAnswers] = useState<ObservedChooserAnswers>({});
  const questions = observedChooserQuestions(baseMetricType);

  if (questions.length === 0) {
    return null;
  }

  const recommendation = recommendObservedTest(baseMetricType, answers);

  return (
    <div style={{ marginTop: "var(--space-3)" }}>
      <button type="button" className="btn ghost" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        {t("results.observedResults.chooser.toggle")}
      </button>
      {open ? (
        <div className="note" style={{ marginTop: "var(--space-3)", display: "grid", gap: "var(--space-3)" }}>
          <p className="muted" style={{ margin: 0 }}>{t("results.observedResults.chooser.description")}</p>
          {questions.map((question) => (
            <fieldset key={question.id} style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "8px" }}>
              <legend style={{ padding: 0, fontWeight: 600 }}>{t(question.labelKey)}</legend>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
                {question.options.map((option) => {
                  const optionId = `chooser-${question.id}-${option.value}`;
                  return (
                    <label key={option.value} htmlFor={optionId} style={{ display: "inline-flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                      <input
                        id={optionId}
                        type="radio"
                        name={`chooser-${question.id}`}
                        value={option.value}
                        checked={answers[question.id] === option.value}
                        // The radio only ever emits a value from the question's own option list, so it is
                        // always a valid answer for this key; the cast just narrows string -> the union.
                        onChange={() => setAnswers((current) => ({ ...current, [question.id]: option.value }) as ObservedChooserAnswers)}
                      />
                      <span>{t(option.labelKey)}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}
          {recommendation ? (
            <div className="callout" style={{ display: "grid", gap: "8px" }}>
              <strong>{t("results.observedResults.chooser.recommendation", { test: t(observedTestLabelKey(baseMetricType, recommendation.test)) })}</strong>
              <span>{t(recommendation.rationaleKey)}</span>
              <div className="actions" style={{ marginTop: "var(--space-2)" }}>
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => {
                    onSelectTest(recommendation.test);
                    setOpen(false);
                  }}
                >
                  {t("results.observedResults.chooser.apply")}
                </button>
              </div>
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>{t("results.observedResults.chooser.incomplete")}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
