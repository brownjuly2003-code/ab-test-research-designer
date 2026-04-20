import { create } from "zustand";

import {
  type AnalysisResponsePayload,
  type FullPayload,
  type ResultsState,
  validateForm
} from "../lib/experiment";
import { requestAnalysis } from "../lib/api";
import type { ToastType } from "../hooks/useToast";

type AnalysisStoreState = {
  results: ResultsState;
  analysisResult: AnalysisResponsePayload | null;
  isAnalyzing: boolean;
  loading: boolean;
  analysisError: string;
  error: string;
  statusMessage: string;
  statusToastType: ToastType | null;
  errorToastType: ToastType | null;
  resultsProjectId: string | null;
  resultsAnalysisRunId: string | null;
  validationErrors: string[];
  getPersistableAnalysis: (
    currentResult?: AnalysisResponsePayload | null
  ) => AnalysisResponsePayload | null;
  validateDraft: (form: FullPayload) => string[];
  ensureValidForm: (form: FullPayload) => boolean;
  runAnalysis: (form: FullPayload) => Promise<AnalysisResponsePayload | null>;
  clearAnalysis: () => void;
  invalidateResults: () => void;
  clearFeedback: () => void;
  showError: (message: string, type?: ToastType) => void;
  showStatus: (message: string, type?: ToastType) => void;
  linkResultToProject: (projectId: string | null, analysisRunId?: string | null) => void;
};

let abortController: AbortController | null = null;
let statusTimeoutId: number | null = null;

function resolveErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function toResultsState(
  analysisResult: AnalysisResponsePayload | null
): ResultsState {
  if (analysisResult === null) {
    return {};
  }

  return {
    calculations: analysisResult.calculations,
    report: analysisResult.report,
    advice: analysisResult.advice
  };
}

function clearStatusTimer() {
  if (statusTimeoutId === null || typeof window === "undefined") {
    statusTimeoutId = null;
    return;
  }

  window.clearTimeout(statusTimeoutId);
  statusTimeoutId = null;
}

function scheduleStatusClear(message: string, type: ToastType) {
  clearStatusTimer();

  if (typeof window === "undefined") {
    return;
  }

  statusTimeoutId = window.setTimeout(() => {
    const state = useAnalysisStore.getState();
    if (state.statusMessage !== message || state.statusToastType !== type) {
      return;
    }

    useAnalysisStore.setState({
      statusMessage: "",
      statusToastType: null
    });
    statusTimeoutId = null;
  }, 5000);
}

export const useAnalysisStore = create<AnalysisStoreState>((set, get) => ({
  results: {},
  analysisResult: null,
  isAnalyzing: false,
  loading: false,
  analysisError: "",
  error: "",
  statusMessage: "",
  statusToastType: null,
  errorToastType: null,
  resultsProjectId: null,
  resultsAnalysisRunId: null,
  validationErrors: [],
  getPersistableAnalysis: (currentResult = get().analysisResult) => {
    if (!currentResult?.calculations || !currentResult.report || !currentResult.advice) {
      return null;
    }

    return {
      calculations: currentResult.calculations,
      report: currentResult.report,
      advice: currentResult.advice
    };
  },
  validateDraft: (form) => {
    const issues = validateForm(form);
    set({ validationErrors: issues });
    return issues;
  },
  ensureValidForm: (form) => {
    const issues = get().validateDraft(form);

    if (issues.length > 0) {
      clearStatusTimer();
      set({
        analysisError: "",
        error: "",
        errorToastType: null,
        statusMessage: "",
        statusToastType: null
      });
      return false;
    }

    return true;
  },
  runAnalysis: async (form) => {
    if (!get().ensureValidForm(form)) {
      return null;
    }

    abortController?.abort();
    const controller = new AbortController();
    abortController = controller;
    clearStatusTimer();

    set({
      isAnalyzing: true,
      loading: true,
      analysisError: "",
      error: "",
      errorToastType: null,
      statusMessage: "",
      statusToastType: null
    });

    try {
      const data = await requestAnalysis(form, { signal: controller.signal });
      if (abortController !== controller) {
        return null;
      }

      set({
        analysisResult: data,
        results: toResultsState(data),
        resultsProjectId: null,
        resultsAnalysisRunId: null,
        validationErrors: []
      });
      return data;
    } catch (error) {
      if (!isAbortError(error) && abortController === controller) {
        const message = resolveErrorMessage(error, "Unexpected request error");
        set({
          analysisError: message,
          error: message
        });
      }
      return null;
    } finally {
      if (abortController === controller) {
        abortController = null;
        set({
          isAnalyzing: false,
          loading: false
        });
      }
    }
  },
  clearAnalysis: () => {
    abortController?.abort();
    abortController = null;
    clearStatusTimer();
    set({
      results: {},
      analysisResult: null,
      isAnalyzing: false,
      loading: false,
      analysisError: "",
      error: "",
      statusMessage: "",
      statusToastType: null,
      errorToastType: null,
      resultsProjectId: null,
      resultsAnalysisRunId: null,
      validationErrors: []
    });
  },
  invalidateResults: () => {
    clearStatusTimer();
    set({
      results: {},
      analysisResult: null,
      analysisError: "",
      error: "",
      statusMessage: "",
      statusToastType: null,
      errorToastType: null,
      resultsProjectId: null,
      resultsAnalysisRunId: null,
      validationErrors: []
    });
  },
  clearFeedback: () => {
    clearStatusTimer();
    set({
      analysisError: "",
      error: "",
      errorToastType: null,
      statusMessage: "",
      statusToastType: null
    });
  },
  showError: (message, type = "error") => {
    clearStatusTimer();
    set({
      analysisError: message,
      error: message,
      errorToastType: type,
      statusMessage: "",
      statusToastType: null
    });
  },
  showStatus: (message, type = "info") => {
    set({
      analysisError: "",
      error: "",
      errorToastType: null,
      statusMessage: message,
      statusToastType: type
    });
    scheduleStatusClear(message, type);
  },
  linkResultToProject: (projectId, analysisRunId = null) => {
    set({
      resultsProjectId: projectId,
      resultsAnalysisRunId: analysisRunId
    });
  }
}));
