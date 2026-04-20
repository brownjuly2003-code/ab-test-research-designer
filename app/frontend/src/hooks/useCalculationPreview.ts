import { useCallback, useEffect, useRef, useState } from "react";

import { requestCalculation } from "../lib/api";
import {
  buildCalculationPayload,
  parseTrafficSplit,
  type CalculationResponse,
  type FullPayload
} from "../lib/experiment";

type PreviewState = {
  result: CalculationResponse | null;
  isLoading: boolean;
  error: string | null;
};

const emptyPreviewState: PreviewState = {
  result: null,
  isLoading: false,
  error: null
};

export function useCalculationPreview(draft: FullPayload, enabled: boolean): PreviewState {
  const [state, setState] = useState<PreviewState>(emptyPreviewState);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const compute = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState((current) => ({
      ...current,
      isLoading: true,
      error: null
    }));

    try {
      const result = await requestCalculation(buildCalculationPayload(draft), {
        signal: controller.signal
      });

      setState({
        result,
        isLoading: false,
        error: null
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }

      setState({
        result: null,
        isLoading: false,
        error: "Preview unavailable"
      });
    }
  }, [draft]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    if (!enabled || !canCompute(draft)) {
      abortRef.current?.abort();
      setState((current) => (
        current.result || current.isLoading || current.error ? emptyPreviewState : current
      ));
      return;
    }

    timerRef.current = setTimeout(() => {
      void compute();
    }, 300);

    return () => {
      abortRef.current?.abort();
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [compute, draft, enabled]);

  return state;
}

function canCompute(draft: FullPayload): boolean {
  const variantsCount = Number(draft.setup.variants_count);
  const trafficSplit = parseTrafficSplit(draft.setup.traffic_split);
  const expectedDailyTraffic = Number(draft.setup.expected_daily_traffic);
  const audienceShareInTest = Number(draft.setup.audience_share_in_test);
  const baselineValue = Number(draft.metrics.baseline_value);
  const mdePct = Number(draft.metrics.mde_pct);
  const alpha = Number(draft.metrics.alpha);
  const power = Number(draft.metrics.power);
  const analysisMode = draft.constraints.analysis_mode ?? "frequentist";
  const desiredPrecision = Number(draft.constraints.desired_precision);

  if (!Number.isInteger(variantsCount) || variantsCount < 2) {
    return false;
  }
  if (trafficSplit.length !== variantsCount) {
    return false;
  }
  if (!(expectedDailyTraffic > 0)) {
    return false;
  }
  if (!(audienceShareInTest > 0 && audienceShareInTest <= 1)) {
    return false;
  }
  if (!(mdePct > 0)) {
    return false;
  }
  if (analysisMode === "bayesian" && !(desiredPrecision > 0)) {
    return false;
  }
  if (analysisMode !== "bayesian") {
    if (!(alpha > 0 && alpha < 1)) {
      return false;
    }
    if (!(power > 0 && power < 1)) {
      return false;
    }
  }

  if (draft.metrics.metric_type === "binary") {
    return baselineValue > 0 && baselineValue < 1;
  }

  if (draft.metrics.metric_type === "continuous") {
    const stdDev = Number(draft.metrics.std_dev);
    if (!(baselineValue > 0 && stdDev > 0)) {
      return false;
    }

    if (!draft.metrics.cuped_enabled) {
      return true;
    }

    const cupedPreExperimentStd = Number(draft.metrics.cuped_pre_experiment_std);
    const cupedCorrelation = Number(draft.metrics.cuped_correlation);
    return cupedPreExperimentStd > 0 && cupedCorrelation > -1 && cupedCorrelation < 1;
  }

  return false;
}
