/**
 * Stable facade for the frontend API client.
 * Domain modules live alongside this file; callers keep importing from `lib/api`.
 */

export type {
  LlmProvider,
  LlmSessionConfig,
  RequestOptions
} from "./client";
export {
  clearAdminSessionToken,
  clearApiSessionToken,
  clearLlmSessionConfig,
  getLlmSessionConfig,
  hasAdminSessionToken,
  hasApiSessionToken,
  setAdminSessionToken,
  setApiSessionToken,
  setLlmSessionProvider,
  setLlmSessionToken
} from "./client";

export type {
  AnalysisResponse,
  HypothesisCandidate,
  HypothesisIdeationRequest,
  HypothesisIdeationResponse,
  SensitivityRequest,
  SensitivityResponse,
  SrmCheckRequest,
  SrmCheckResponse
} from "./analysis";
export {
  exportReportRequest,
  requestAnalysis,
  requestCalculation,
  requestHypotheses,
  requestSensitivity,
  requestSrmCheck
} from "./analysis";

export type {
  ArchiveProjectResponse,
  CompareMultipleProjectsRequestOptions,
  DeleteProjectResponse,
  ProjectHistoryRequestOptions,
  ProjectListRequestOptions,
  ProjectRecordResponse,
  ProjectRevisionRequestOptions,
  SaveProjectResponse
} from "./projects";
export {
  archiveProjectRequest,
  compareMultipleProjectsRequest,
  compareProjectsRequest,
  deleteProjectRequest,
  downloadProjectReportDataRequest,
  downloadProjectReportPdfRequest,
  exportComparisonRequest,
  listProjectsRequest,
  loadProjectHistoryRequest,
  loadProjectRequest,
  loadProjectRevisionsRequest,
  recordProjectAnalysisRequest,
  recordProjectExportRequest,
  restoreProjectRequest,
  saveProjectRequest
} from "./projects";

export type {
  ApiKeyCreateRequest,
  ApiKeyCreateResponse,
  ApiKeyDeleteResponse,
  ApiKeyListResponse,
  ApiKeyRecord,
  ApiKeyScope
} from "./keys";
export {
  createApiKeyRequest,
  deleteApiKeyRequest,
  listApiKeysRequest,
  revokeApiKeyRequest
} from "./keys";

export type {
  SlackStatusResponse,
  WebhookCreateRequest,
  WebhookDeleteResponse,
  WebhookDeliveryListResponse,
  WebhookDeliveryRecord,
  WebhookDeliveryStatus,
  WebhookFormat,
  WebhookListResponse,
  WebhookScope,
  WebhookSubscriptionRecord,
  WebhookTestResponse
} from "./webhooks";
export {
  createWebhookRequest,
  deleteWebhookRequest,
  listWebhookDeliveriesRequest,
  listWebhooksRequest,
  requestSlackStatus,
  slackInstallUrl,
  testWebhookRequest
} from "./webhooks";

export type {
  AuditLogRequestOptions,
  DiagnosticsResponse
} from "./system";
export {
  deleteTemplateRequest,
  exportAuditLogRequest,
  listAuditLogRequest,
  listTemplatesRequest,
  requestDiagnostics,
  requestHealth,
  useTemplateRequest
} from "./system";

export type {
  WorkspaceExportResponse,
  WorkspaceImportSummary,
  WorkspaceValidationSummary
} from "./workspace";
export {
  exportWorkspaceRequest,
  importWorkspaceRequest,
  validateWorkspaceRequest
} from "./workspace";

// Generated domain types that were re-exported from the former monolithic api.ts
export type {
  BanditRegretPoint,
  BanditSimulationRequest,
  BanditSimulationResponse,
  DecisionReadoutResponse,
  DecisionReason,
  ExperimentAssignmentRequest,
  ExperimentAssignmentResponse,
  LiveArmStat,
  LiveComparison,
  LiveCupedArmStat,
  LiveCupedBlock,
  LiveCupedComparison,
  LiveEventTimingBlock,
  LiveExclusionBlock,
  LiveGuardrailArmStat,
  LiveGuardrailBlock,
  LiveGuardrailComparison,
  LiveGuardrailMetricResult,
  LiveHoldoutArmStat,
  LiveHoldoutBlock,
  LiveIdentityResolutionBlock,
  LiveSequentialBlock,
  LiveSrmBlock,
  LiveStatsResponse,
  LiveStratifiedBlock,
  LiveStratifiedComparison,
  LiveStratumEffect,
  MetricPValue,
  MultipleTestingMetricResult,
  MultipleTestingRequest,
  MultipleTestingResponse
} from "../generated/api-contract";
