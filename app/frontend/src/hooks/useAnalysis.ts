import { useState } from "react";

import type { AnalysisResponse } from "../lib/api";
import { type FullPayload, type ResultsState, validateForm } from "../lib/experiment";

export function useAnalysis() {
  const [results, setResults] = useState<ResultsState>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [resultsProjectId, setResultsProjectId] = useState<string | null>(null);
  const [resultsAnalysisRunId, setResultsAnalysisRunId] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  function getPersistableAnalysis(state: ResultsState = results): AnalysisResponse | null {
    if (!state.calculations || !state.report || !state.advice) {
      return null;
    }

    return {
      calculations: state.calculations,
      report: state.report,
      advice: state.advice
    };
  }

  function ensureValidForm(form: FullPayload): boolean {
    const issues = validateForm(form);

    if (issues.length > 0) {
      setValidationErrors(issues);
      setError("");
      setStatusMessage("");
      return false;
    }

    setValidationErrors([]);
    return true;
  }

  function invalidateResults() {
    setResultsProjectId(null);
    setResultsAnalysisRunId(null);
    setResults((current) => (Object.keys(current).length > 0 ? {} : current));
    setStatusMessage((current) => (current ? "" : current));
    setError((current) => (current ? "" : current));
    setValidationErrors((current) => (current.length > 0 ? [] : current));
  }

  function resetAnalysisState() {
    setResults({});
    setResultsProjectId(null);
    setResultsAnalysisRunId(null);
    setError("");
    setStatusMessage("");
    setValidationErrors([]);
  }

  return {
    results,
    setResults,
    loading,
    setLoading,
    saving,
    setSaving,
    error,
    setError,
    statusMessage,
    setStatusMessage,
    resultsProjectId,
    setResultsProjectId,
    resultsAnalysisRunId,
    setResultsAnalysisRunId,
    validationErrors,
    setValidationErrors,
    getPersistableAnalysis,
    ensureValidForm,
    invalidateResults,
    resetAnalysisState
  };
}
