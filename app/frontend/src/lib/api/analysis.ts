/**
 * Stateless analysis / calculation / export compute client.
 */

import {
  buildApiPayload,
  type AnalysisResponsePayload,
  type CalculationRequestPayload,
  type CalculationResponse,
  type ExportFormat,
  type FullPayload,
  type ReportResponse
} from "../experiment";
import type {
  ExportResponse,
  HypothesisIdeationRequest,
  HypothesisIdeationResponse,
  SensitivityRequest,
  SensitivityResponse,
  SrmCheckRequest,
  SrmCheckResponse
} from "../generated/api-contract";
import { apiJsonRequest, buildLlmHeaders, type RequestOptions } from "./client";

export type AnalysisResponse = AnalysisResponsePayload;

export type {
  HypothesisCandidate,
  HypothesisIdeationRequest,
  HypothesisIdeationResponse
} from "../generated/api-contract";

export type { SensitivityRequest, SensitivityResponse, SrmCheckRequest, SrmCheckResponse };

export async function requestAnalysis(
  form: FullPayload,
  options: RequestOptions = {}
): Promise<AnalysisResponse> {
  return apiJsonRequest<AnalysisResponse>("/api/v1/analyze", {
    method: "POST",
    body: buildApiPayload(form),
    headers: buildLlmHeaders("/api/v1/analyze"),
    signal: options.signal,
    errorFallback: "Analysis request failed"
  });
}

export async function requestCalculation(
  payload: CalculationRequestPayload,
  options: RequestOptions = {}
): Promise<CalculationResponse> {
  return apiJsonRequest<CalculationResponse>("/api/v1/calculate", {
    method: "POST",
    body: payload,
    signal: options.signal,
    errorFallback: "Calculation request failed"
  });
}

export async function requestHypotheses(
  payload: HypothesisIdeationRequest,
  options: RequestOptions = {}
): Promise<HypothesisIdeationResponse> {
  return apiJsonRequest<HypothesisIdeationResponse>("/api/v1/hypotheses/generate", {
    method: "POST",
    body: payload,
    headers: buildLlmHeaders("/api/v1/hypotheses/generate"),
    signal: options.signal,
    errorFallback: "Hypothesis generation failed"
  });
}

export async function requestSensitivity(
  payload: SensitivityRequest,
  options: RequestOptions = {}
): Promise<SensitivityResponse> {
  return apiJsonRequest<SensitivityResponse>("/api/v1/sensitivity", {
    method: "POST",
    body: payload,
    signal: options.signal,
    errorFallback: "Sensitivity request failed"
  });
}

export async function requestSrmCheck(
  payload: SrmCheckRequest,
  options: RequestOptions = {}
): Promise<SrmCheckResponse> {
  return apiJsonRequest<SrmCheckResponse>("/api/v1/srm-check", {
    method: "POST",
    body: payload,
    signal: options.signal,
    errorFallback: "SRM check request failed"
  });
}

export async function exportReportRequest(report: ReportResponse, format: ExportFormat): Promise<string> {
  const data = await apiJsonRequest<ExportResponse>(`/api/v1/export/${format}`, {
    method: "POST",
    body: report,
    errorFallback: "Export failed"
  });

  return String(data.content ?? "");
}
