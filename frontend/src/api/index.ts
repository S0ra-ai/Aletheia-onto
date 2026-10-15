import axios from 'axios';
import { clearSession, getToken } from '../auth/session';
import type { AuthUser } from '../auth/session';
import type {
  DataSource,
  DataSourceCreate,
  OnboardingRunCreate,
  OnboardingResult,
  SourceApi,
  SourceApiCreate,
  SourceTable,
  DataSourceReadiness,
  SchemaDriftResult,
  SemanticCoverageResult,
  OperationBindingResult,
  OntologyDraftCreate,
  OntologyDetail,
  ReleaseReadinessResult,
  DemoBootstrapResult,
  InstanceExplainResult,
  EventTypeDeclaration,
  InstanceEventsResult,
  InstanceVersionsResult,
  InstanceAssessResult,
  SemanticObjectInstancesResult,
  SemanticObjectInstanceResult,
  DecisionConsistencyResult,
  OperationPreflightResult,
  OperationExecuteResult,
  NaturalLanguageQueryPayload,
  NaturalLanguageQueryResult,
  DecisionRecordItem,
  AuditLogItem,
  ModelInvocationItem,
  ModelStatus,
  ModelConfig,
  ModelConfigUpdate,
  IndustryBlueprint,
  OntologyReasoningChainResult,
  RuleWordImportResult,
  KnowledgeBase,
  SourceTableRows,
  ReasoningChain,
  AgentRole,
  AgentChatPayload,
  AgentChatResult,
  WorkflowDefinition,
  WorkflowState,
  WorkflowTransition,
  WorkflowInstance,
  WorkflowHistoryItem,
  PermissionRole,
  PermissionPolicy,
  ToolDefinition,
  ToolExecutionLog,
  ToolAuthorization,
  Workbench,
  OntologyGraph,
  KnowledgeDocument,
  KnowledgeEntry,
  KnowledgeEntryList,
  KnowledgeIngestResult,
  Conversation,
  AnswerFeedback,
  FeedbackSummary,
  QuotaResource,
  TenantList,
  TenantSummary,
  TenantQuotas,
  TenantStatistics,
  SsoGroupMapping,
  SsoStatus,
  AuditReport,
  AuditReportSection,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 90000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach the bearer token to every request, and surface auth failures in one
// place instead of at each call site.
/**
 * An error whose message was written for the user, not for a developer.
 *
 * The server sends a curated reason in `detail`; the interceptor below puts it on the
 * Error. Callers cannot tell that apart from a rejection axios produced itself --
 * `Network Error`, `timeout of 10000ms exceeded`, `Request failed with status code 500` --
 * by looking at the message, and those are English internals rather than something to show
 * a user. A marker type makes the distinction exact instead of a guess about wording.
 */
export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * The message to show a user for a failed request.
 *
 * Prefers the server's curated reason, falling back to the caller's own sentence about
 * what it was trying to do. Every caller used to show only its own generic sentence,
 * discarding the one message actually written for the user: a permission failure explained
 * as "获取数据源列表失败" tells them nothing they can act on.
 */
export function requestErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.message ? error.message : fallback;
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const detail = error?.response?.data?.detail;
    if (status === 401) {
      clearSession();
      if (!window.location.pathname.startsWith('/login')) {
        window.location.assign('/login');
      }
      return Promise.reject(new ApiError(detail || '登录已失效，请重新登录。'));
    }
    if (status === 403) {
      const capability = error?.response?.data?.requiredCapability;
      return Promise.reject(
        new ApiError(detail || `当前角色无权执行该操作${capability ? `（需要 ${capability}）` : ''}。`),
      );
    }
    if (detail) {
      return Promise.reject(new ApiError(detail));
    }
    // Rejected as-is: there is no curated message, and the caller's fallback is the better
    // thing to show than axios's own wording.
    return Promise.reject(error);
  },
);

export const authApi = {
  login: async (username: string, password: string): Promise<{ token: string; user: AuthUser }> => {
    const { data } = await api.post('/auth/login', { username, password });
    return { token: data.token, user: data.user as AuthUser };
  },
  logout: async (): Promise<void> => {
    try {
      await api.post('/auth/logout');
    } finally {
      clearSession();
    }
  },
  me: async (): Promise<AuthUser> => {
    const { data } = await api.get('/auth/me');
    return data as AuthUser;
  },
  changePassword: async (currentPassword: string, newPassword: string): Promise<{ message: string }> => {
    const { data } = await api.post('/auth/change-password', { currentPassword, newPassword });
    return data;
  },
  listUsers: async (): Promise<{ items: unknown[]; roles: string[] }> => {
    const { data } = await api.get('/auth/users');
    return data;
  },
  createUser: async (payload: {
    username: string;
    password: string;
    roleCode: string;
    displayName?: string;
  }): Promise<unknown> => {
    const { data } = await api.post('/auth/users', payload);
    return data;
  },
  setUserStatus: async (username: string, status: 'active' | 'disabled'): Promise<unknown> => {
    const { data } = await api.patch(`/auth/users/${encodeURIComponent(username)}/status`, { status });
    return data;
  },
};

const normalizeDataSource = (item: any): DataSource => ({
  id: item.id,
  name: item.name,
  sourceType: item.sourceType ?? item.source_type,
  connectionUri: item.connectionUri ?? item.connection_uri,
  apiBaseUrl: item.apiBaseUrl ?? item.api_base_url ?? '',
  apiHeadersConfigured: item.apiHeadersConfigured ?? item.api_headers_configured ?? false,
  apiHeaderNames: item.apiHeaderNames ?? item.api_header_names ?? [],
  domain: item.domain ?? '',
  systemCategory: item.systemCategory ?? item.system_category ?? 'database',
  capabilities: item.capabilities ?? [],
  createdAt: item.createdAt ?? item.created_at,
});

const normalizeSourceApi = (item: any): SourceApi => ({
  id: item.id,
  dataSourceId: item.dataSourceId ?? item.data_source_id,
  operationCode: item.operationCode ?? item.operation_code,
  name: item.name,
  method: item.method,
  path: item.path,
  semanticAction: item.semanticAction ?? item.semantic_action ?? '',
  requestSchema: item.requestSchema ?? item.request_schema ?? {},
  responseSchema: item.responseSchema ?? item.response_schema ?? {},
});

/**
 * Permission and tool rows, mapped from the wire to the shape the screens use.
 *
 * These three endpoints send snake_case (`role_code`, `can_read`, `tool_type`,
 * `risk_level`) while their TypeScript types declared camelCase. The types therefore
 * checked out, autocompleted, and described fields that were `undefined` at runtime --
 * and antd draws nothing for a missing `dataIndex`, so the permission policy table
 * rendered twenty rows of blank cells on the screen that answers "who may do what".
 *
 * Normalised here rather than at each call site: the boundary between the wire and the
 * application is this file's job, and the alternative -- correcting one page at a time --
 * is how the same defect arrived three times.
 */
/**
 * A workflow definition, mapped from the wire to the shape the screens use.
 *
 * `/workflows` sends `object_code`, `ontology_id`, `initial_state`; the definition type
 * declared camelCase, so the list table's 业务对象 / 本体 / 初始状态 columns were blank for
 * every row. Nothing failed -- an antd column whose `dataIndex` does not exist draws
 * nothing -- and it stayed invisible while no workflow existed, because the check that
 * would have caught it reads rendered rows.
 */
const normalizeWorkflowState = (item: any): WorkflowState => ({
  ...item,
  workflowId: item.workflowId ?? item.workflow_id,
  isTerminal: item.isTerminal ?? item.is_terminal ?? 0,
  sortOrder: item.sortOrder ?? item.sort_order ?? 0,
});

const normalizeWorkflowTransition = (item: any): WorkflowTransition => ({
  ...item,
  workflowId: item.workflowId ?? item.workflow_id,
  actionCode: item.actionCode ?? item.action_code ?? '',
  fromState: item.fromState ?? item.from_state ?? '',
  toState: item.toState ?? item.to_state ?? '',
  guardExpression: item.guardExpression ?? item.guard_expression ?? '',
  requiresReview: item.requiresReview ?? item.requires_review ?? 0,
  reviewRole: item.reviewRole ?? item.review_role ?? '',
  sortOrder: item.sortOrder ?? item.sort_order ?? 0,
});

const normalizeWorkflow = (item: any): WorkflowDefinition => ({
  ...item,
  ontologyId: item.ontologyId ?? item.ontology_id,
  objectCode: item.objectCode ?? item.object_code ?? '',
  initialState: item.initialState ?? item.initial_state ?? '',
  createdAt: item.createdAt ?? item.created_at ?? '',
  // The nested rows go through their own normalisers. Spreading `...item` and passing
  // `item.states` through left them in wire spelling, so the transition table's 动作 / 来源 /
  // 目标 / 需审核 columns were blank while the definition above them was translated.
  states: (item.states || []).map(normalizeWorkflowState),
  transitions: (item.transitions || []).map(normalizeWorkflowTransition),
});

const normalizeWorkflowInstance = (item: any): WorkflowInstance => ({
  ...item,
  workflowId: item.workflowId ?? item.workflow_id,
  objectCode: item.objectCode ?? item.object_code ?? '',
  instanceId: item.instanceId ?? item.instance_id ?? '',
  currentState: item.currentState ?? item.current_state ?? '',
});

const normalizeToolExecution = (item: any): ToolExecutionLog => ({
  ...item,
  toolId: item.toolId ?? item.tool_id,
  toolCode: item.toolCode ?? item.tool_code ?? '',
  agentRole: item.agentRole ?? item.agent_role ?? '',
  objectCode: item.objectCode ?? item.object_code ?? '',
  instanceId: item.instanceId ?? item.instance_id ?? '',
  inputArgs: item.inputArgs ?? item.input_args ?? '',
  resultSummary: item.resultSummary ?? item.result_summary ?? '',
  durationMs: item.durationMs ?? item.duration_ms ?? 0,
  requiresReview: item.requiresReview ?? item.requires_review ?? 0,
  reviewedBy: item.reviewedBy ?? item.reviewed_by ?? null,
  reviewedAt: item.reviewedAt ?? item.reviewed_at ?? null,
  reviewDecision: item.reviewDecision ?? item.review_decision ?? '',
  createdAt: item.createdAt ?? item.created_at ?? '',
});

const normalizePolicy = (item: any): PermissionPolicy => ({
  id: item.id,
  roleId: item.roleId ?? item.role_id,
  roleCode: item.roleCode ?? item.role_code ?? '',
  roleName: item.roleName ?? item.role_name ?? '',
  objectCode: item.objectCode ?? item.object_code ?? '',
  canRead: item.canRead ?? item.can_read ?? 0,
  canWrite: item.canWrite ?? item.can_write ?? 0,
  canExecute: item.canExecute ?? item.can_execute ?? 0,
  canDelete: item.canDelete ?? item.can_delete ?? 0,
  filterExpression: item.filterExpression ?? item.filter_expression ?? '',
  description: item.description ?? '',
});

const normalizeRole = (item: any): PermissionRole => ({
  ...item,
  isSystem: item.isSystem ?? item.is_system ?? 0,
  createdAt: item.createdAt ?? item.created_at ?? '',
});

const normalizeTool = (item: any): ToolDefinition => ({
  id: item.id,
  code: item.code,
  name: item.name,
  description: item.description ?? '',
  toolType: item.toolType ?? item.tool_type ?? '',
  inputSchema: item.inputSchema ?? item.input_schema ?? '',
  riskLevel: item.riskLevel ?? item.risk_level ?? '',
  requiresReview: item.requiresReview ?? item.requires_review ?? 0,
  status: item.status ?? '',
  createdAt: item.createdAt ?? item.created_at ?? '',
});

const normalizeSourceTable = (item: any): SourceTable => ({
  id: item.id,
  tableName: item.tableName ?? item.table_name,
  rowCount: item.rowCount ?? item.row_count,
  primaryKey: item.primaryKey ?? item.primary_key,
  scannedAt: item.scannedAt ?? item.scanned_at,
});

// 数据源 API
export const dataSourceApi = {
  list: async (): Promise<DataSource[]> => {
    const { data } = await api.get('/data-sources');
    const items = (data as { dataSources?: unknown[]; data_sources?: unknown[] }).dataSources
      || (data as { data_sources?: unknown[] }).data_sources
      || [];
    return items.map(normalizeDataSource);
  },

  create: async (payload: DataSourceCreate): Promise<DataSource> => {
    const { data } = await api.post('/data-sources', payload);
    return normalizeDataSource(data);
  },

  testConnection: async (payload: { sourceType: string; connectionUri: string }): Promise<{ reachable: boolean; status: string; message: string; sourceType: string }> => {
    const { data } = await api.post('/data-sources/test-connection', payload);
    return data;
  },

  testRegisteredConnection: async (id: number): Promise<{ reachable: boolean; status: string; message: string; sourceType: string }> => {
    const { data } = await api.post(`/data-sources/${id}/test-connection`);
    return data;
  },

  testApiGateway: async (id: number): Promise<{ configured: boolean; reachable: boolean; status: string; statusCode: number | null; message: string; apiBaseUrl: string }> => {
    const { data } = await api.post(`/data-sources/${id}/test-api-gateway`);
    return data;
  },

  getTables: async (id: number): Promise<SourceTable[]> => {
    const { data } = await api.get(`/data-sources/${id}/tables`);
    return ((data as { tables: unknown[] }).tables || []).map(normalizeSourceTable);
  },

  browseTable: async (id: number, tableName: string, limit = 50, offset = 0): Promise<SourceTableRows> => {
    const { data } = await api.get(`/data-sources/${id}/tables/${encodeURIComponent(tableName)}/rows`, { params: { limit, offset } });
    return data as SourceTableRows;
  },

  initialize: async (id: number): Promise<{ status: string; reasoningChain: ReasoningChain }> => {
    const { data } = await api.post(`/data-sources/${id}/initialize`);
    return data;
  },

  getReasoningChain: async (id: number): Promise<ReasoningChain> => {
    const { data } = await api.get(`/data-sources/${id}/reasoning-chain`);
    return data as ReasoningChain;
  },

  scan: async (id: number): Promise<{ tables: number; columns: number; foreignKeys: number }> => {
    const { data } = await api.post(`/data-sources/${id}/scan`);
    return data as { tables: number; columns: number; foreignKeys: number };
  },

  getApis: async (id: number): Promise<SourceApi[]> => {
    const { data } = await api.get(`/data-sources/${id}/apis`);
    return ((data as { apis: unknown[] }).apis || []).map(normalizeSourceApi);
  },

  getReadiness: async (id: number): Promise<DataSourceReadiness> => {
    const { data } = await api.get(`/data-sources/${id}/readiness`);
    return data as DataSourceReadiness;
  },

  getSchemaDrift: async (id: number): Promise<SchemaDriftResult> => {
    const { data } = await api.get(`/data-sources/${id}/schema-drift`);
    return data as SchemaDriftResult;
  },

  getSemanticCoverage: async (id: number): Promise<SemanticCoverageResult> => {
    const { data } = await api.get(`/data-sources/${id}/semantic-coverage`);
    return data as SemanticCoverageResult;
  },

  getOperationBindings: async (id: number): Promise<OperationBindingResult> => {
    const { data } = await api.get(`/data-sources/${id}/operation-bindings`);
    return data as OperationBindingResult;
  },

  createApi: async (dataSourceId: number, payload: SourceApiCreate): Promise<SourceApi> => {
    const { data } = await api.post(`/data-sources/${dataSourceId}/apis`, payload);
    return normalizeSourceApi(data);
  },

  importOpenApi: async (dataSourceId: number, spec: Record<string, unknown>): Promise<{ imported: SourceApi[]; skipped: unknown[]; count: number }> => {
    const { data } = await api.post(`/data-sources/${dataSourceId}/apis/import-openapi`, { spec });
    return {
      imported: (data.imported || []).map(normalizeSourceApi),
      skipped: data.skipped || [],
      count: data.count || 0,
    };
  },

  importOpenApiUrl: async (dataSourceId: number, url: string): Promise<{ imported: SourceApi[]; skipped: unknown[]; count: number; sourceUrl?: string }> => {
    const { data } = await api.post(`/data-sources/${dataSourceId}/apis/import-openapi-url`, { url });
    return {
      imported: (data.imported || []).map(normalizeSourceApi),
      skipped: data.skipped || [],
      count: data.count || 0,
      sourceUrl: data.sourceUrl,
    };
  },

  kernelPackageUrl: (dataSourceId: number): string => `/api/data-sources/${dataSourceId}/kernel-package/download`,
};

export const knowledgeBaseApi = {
  list: async (): Promise<KnowledgeBase[]> => {
    const { data } = await api.get('/knowledge-bases');
    return (data.items || []) as KnowledgeBase[];
  },
};

export const onboardingApi = {
  run: async (payload: OnboardingRunCreate): Promise<OnboardingResult> => {
    const { data } = await api.post('/onboarding/run', payload);
    return {
      ...data,
      dataSource: normalizeDataSource(data.dataSource),
    } as OnboardingResult;
  },
};

// 本体 API
export const ontologyApi = {
  list: async (): Promise<any[]> => {
    const { data } = await api.get('/ontologies');
    return (data.items || data.ontologies || []) as any[];
  },

  get: async (id: number): Promise<OntologyDetail> => {
    const { data } = await api.get(`/ontologies/${id}`);
    return data as OntologyDetail;
  },

  getReleaseReadiness: async (id: number): Promise<ReleaseReadinessResult> => {
    const { data } = await api.get(`/ontologies/${id}/release-readiness`);
    return data as ReleaseReadinessResult;
  },

  createDraft: async (payload: OntologyDraftCreate): Promise<OntologyDetail> => {
    const { data } = await api.post('/ontologies/draft', payload);
    return data as OntologyDetail;
  },

  getMappings: async (ontologyId: number, status?: string): Promise<any[]> => {
    const { data } = await api.get(`/ontologies/${ontologyId}/mappings`, { params: status ? { status } : {} });
    return data.items || [];
  },

  reviewMappings: async (ontologyId: number, payload: { status: string; reviewer?: string; note?: string }): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/mappings/review`, payload);
    return data;
  },

  publish: async (ontologyId: number, publisher = 'system'): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/publish`, { publisher });
    return data;
  },

  derive: async (ontologyId: number, version: string, actor = 'system'): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/derive`, { version, actor });
    return data;
  },

  getRules: async (ontologyId: number): Promise<any[]> => {
    const { data } = await api.get(`/ontologies/${ontologyId}/rules`);
    return data.items || [];
  },

  importRulesFromWord: async (ontologyId: number, file: File, apply = true): Promise<RuleWordImportResult> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('apply', String(apply));
    const { data } = await api.post(`/ontologies/${ontologyId}/rules/import-word`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 90000,
    });
    return data as RuleWordImportResult;
  },

  createRule: async (ontologyId: number, payload: {
    code: string; name: string; ruleType: string; scopeObjectCode: string;
    expression: string; severity: string; naturalLanguage: string; status?: string;
  }): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/rules`, payload);
    return data;
  },

  getRule: async (ontologyId: number, ruleId: number): Promise<any> => {
    const { data } = await api.get(`/ontologies/${ontologyId}/rules/${ruleId}`);
    return data;
  },

  updateRule: async (ontologyId: number, ruleId: number, payload: {
    code: string; name: string; ruleType: string; scopeObjectCode: string;
    expression: string; severity: string; naturalLanguage: string; status?: string;
  }): Promise<any> => {
    const { data } = await api.put(`/ontologies/${ontologyId}/rules/${ruleId}`, payload);
    return data;
  },

  deleteRule: async (ontologyId: number, ruleId: number): Promise<any> => {
    const { data } = await api.delete(`/ontologies/${ontologyId}/rules/${ruleId}`);
    return data;
  },

  toggleRuleStatus: async (ontologyId: number, ruleId: number, status: string): Promise<any> => {
    const { data } = await api.patch(`/ontologies/${ontologyId}/rules/${ruleId}/status`, null, { params: { status } });
    return data;
  },

  /**
   * The kinds of event declared for an object.
   *
   * Reading this is what makes "no history yet" actionable: an instance with no events has
   * either never had anything happen to it or a producer whose event codes were never
   * declared, and only the declared list tells the two apart.
   */
  eventTypes: async (ontologyId: number, objectCode?: string): Promise<EventTypeDeclaration[]> => {
    const params = objectCode ? { objectCode } : {};
    const { data } = await api.get(`/ontologies/${ontologyId}/event-types`, { params });
    return ((data as { items?: EventTypeDeclaration[] }).items || []) as EventTypeDeclaration[];
  },

  declareEventType: async (
    ontologyId: number,
    objectCode: string,
    payload: { code: string; name: string; category: string; payloadFields?: string[]; description?: string },
  ): Promise<unknown> => {
    const { data } = await api.put(`/ontologies/${ontologyId}/objects/${objectCode}/event-types`, payload);
    return data;
  },

  /** `jsonld`/`turtle` are this platform's vocabulary; `owl`/`shacl` are the standard ones. */
  exportUrl: (
    ontologyId: number,
    format: 'jsonld' | 'turtle' | 'owl' | 'shacl',
  ): string => `/api/ontologies/${ontologyId}/export?format=${format}`,
};

export const industryBlueprintApi = {
  list: async (): Promise<IndustryBlueprint[]> => {
    const { data } = await api.get('/industry-blueprints');
    return (data.items || []) as IndustryBlueprint[];
  },

  upsert: async (payload: IndustryBlueprint): Promise<IndustryBlueprint> => {
    const { data } = await api.post('/industry-blueprints', payload);
    return data as IndustryBlueprint;
  },
};

// 语义服务 API
export const semanticApi = {
  query: async (payload: NaturalLanguageQueryPayload): Promise<NaturalLanguageQueryResult> => {
    const { data } = await api.post('/semantic/natural-language/query', payload);
    return data as NaturalLanguageQueryResult;
  },

  /** `asOf` explains the instance as of a past instant, for checking an older verdict. */
  explain: async (
    objectCode: string,
    instanceId: string,
    ontologyId?: number,
    asOf?: string,
  ): Promise<InstanceExplainResult> => {
    const params: Record<string, string | number> = {};
    if (ontologyId) params.ontologyId = ontologyId;
    if (asOf) params.asOf = asOf;
    const { data } = await api.get(`/semantic/objects/${objectCode}/instances/${instanceId}/explain`, { params });
    return data as InstanceExplainResult;
  },

  listInstances: async (
    objectCode: string,
    ontologyId: number,
    limit?: number,
    offset?: number,
  ): Promise<SemanticObjectInstancesResult> => {
    const { data } = await api.get(`/semantic/objects/${encodeURIComponent(objectCode)}/instances`, {
      params: { ontologyId, limit, offset },
    });
    return data as SemanticObjectInstancesResult;
  },

  getInstance: async (
    objectCode: string,
    instanceId: string,
    ontologyId: number,
  ): Promise<SemanticObjectInstanceResult> => {
    const { data } = await api.get(
      `/semantic/objects/${encodeURIComponent(objectCode)}/instances/${encodeURIComponent(instanceId)}`,
      { params: { ontologyId } },
    );
    return data as SemanticObjectInstanceResult;
  },

  assess: async (objectCode: string, instanceId: string, ontologyId?: number): Promise<InstanceAssessResult> => {
    const params = ontologyId ? { ontologyId } : {};
    const { data } = await api.post(`/semantic/objects/${objectCode}/instances/${instanceId}/assess`, {}, { params });
    return {
      objectCode: data.semanticKernel?.objectCode ?? objectCode,
      instanceId: data.semanticKernel?.instanceId ?? instanceId,
      decision: (data.decision?.status ?? 'review') as 'approved' | 'review' | 'blocked',
      rulesHit: (data.ruleResults || []).map((rule: any) => ({
        ruleCode: rule.ruleCode,
        ruleName: rule.ruleName,
        passed: rule.passed,
        message: rule.explanation,
      })),
      explanation: data.decision?.recommendation ?? '',
    };
  },

  consistency: async (
    objectCode: string,
    payload: { ontologyId: number; instanceIds?: string[]; limit?: number }
  ): Promise<DecisionConsistencyResult> => {
    const { data } = await api.post(`/semantic/objects/${objectCode}/consistency`, payload);
    return data as DecisionConsistencyResult;
  },

  /**
   * An instance's full event history.
   *
   * Separate from the `timeline` inside `explain`, which is capped at twenty entries
   * because an explanation is read interactively. The two are not the same list, and a
   * screen that showed the excerpt while claiming to show the history would be wrong in a
   * way only a long-lived instance would reveal.
   */
  instanceEvents: async (
    ontologyId: number,
    objectCode: string,
    instanceId: string,
  ): Promise<InstanceEventsResult> => {
    const { data } = await api.get(
      `/ontologies/${ontologyId}/objects/${encodeURIComponent(objectCode)}/instances/${encodeURIComponent(instanceId)}/events`,
    );
    return data as InstanceEventsResult;
  },

  /** Which value an attribute held, and when. Recorded, never derived. */
  instanceVersions: async (
    ontologyId: number,
    objectCode: string,
    instanceId: string,
  ): Promise<InstanceVersionsResult> => {
    const { data } = await api.get(
      `/ontologies/${ontologyId}/objects/${encodeURIComponent(objectCode)}/instances/${encodeURIComponent(instanceId)}/versions`,
    );
    return data as InstanceVersionsResult;
  },

  /**
   * Append one event to an instance's history.
   *
   * An undeclared code is refused by the server: accepting it would let «驳回», «拒绝» and
   * «rejected» become three unrelated facts and history would stop being queryable. The
   * drawer therefore offers only codes that were declared.
   */
  recordInstanceEvent: async (
    ontologyId: number,
    objectCode: string,
    instanceId: string,
    payload: { eventCode: string; payload?: Record<string, unknown>; occurredAt?: string },
  ): Promise<unknown> => {
    const { data } = await api.post(
      `/ontologies/${ontologyId}/objects/${encodeURIComponent(objectCode)}/instances/${encodeURIComponent(instanceId)}/events`,
      payload,
    );
    return data;
  },
};

// 智能体 API
export const agentApi = {
  roles: async (): Promise<AgentRole[]> => {
    const { data } = await api.get('/agent/roles');
    return (data.roles || []) as AgentRole[];
  },

  chat: async (payload: AgentChatPayload): Promise<AgentChatResult> => {
    const { data } = await api.post('/agent/chat', payload);
    return data as AgentChatResult;
  },
};

// 自动化 API
export const automationApi = {
  preflight: async (
    operationCode: string,
    payload: {
      ontologyId: number;
      dataSourceId: number;
      instanceId: string;
      objectCode?: string;
    }
  ): Promise<OperationPreflightResult> => {
    const { data } = await api.post(`/automation/operations/${operationCode}/preflight`, payload);
    return {
      operationCode: data.operation?.operationCode ?? operationCode,
      instanceId: data.target?.instanceId ?? payload.instanceId,
      decision: (data.decision?.status ?? 'review') as 'approved' | 'review' | 'blocked',
      rulesHit: (data.ruleResults || []).map((rule: any) => ({
        ruleCode: rule.ruleCode,
        ruleName: rule.ruleName,
        passed: rule.passed,
        message: rule.explanation,
      })),
      explanation: data.decision?.recommendation ?? '',
      // The sentence, not the code. It preferred `nextAction` -- an internal identifier --
      // over the recommendation the same payload carries, so the 建议 alert read
      // `allow_automation` while a Chinese sentence sat unused beside it.
      recommendation: data.decision?.recommendation ?? '',
      nextAction: data.nextAction ?? '',
    };
  },

  execute: async (
    operationCode: string,
    payload: {
      ontologyId: number;
      dataSourceId: number;
      instanceId: string;
      objectCode?: string;
      payload?: Record<string, unknown>;
      actor?: string;
      dryRun?: boolean;
    }
  ): Promise<OperationExecuteResult> => {
    const { data } = await api.post(`/automation/operations/${operationCode}/execute`, payload);
    return {
      operationCode: data.preflight?.operation?.operationCode ?? operationCode,
      instanceId: data.preflight?.target?.instanceId ?? payload.instanceId,
      decision: (data.preflight?.decision?.status ?? 'review') as 'approved' | 'review' | 'blocked',
      executed: Boolean(data.executed),
      status: data.status,
      message: data.message,
      recommendation: data.preflight?.nextAction ?? data.preflight?.decision?.recommendation ?? '',
      execution: data.execution ?? null,
      rulesHit: (data.preflight?.ruleResults || []).map((rule: any) => ({
        ruleCode: rule.ruleCode,
        ruleName: rule.ruleName,
        passed: rule.passed,
        message: rule.explanation,
      })),
    };
  },
};

// 演示 API
export const demoApi = {
  bootstrapContract: async (): Promise<DemoBootstrapResult> => {
    const { data } = await api.post('/demo/bootstrap');
    return data as DemoBootstrapResult;
  },

  bootstrapEquipment: async (): Promise<DemoBootstrapResult> => {
    const { data } = await api.post('/demo/bootstrap/equipment');
    return data as DemoBootstrapResult;
  },
};

// 治理审计 API
export const governanceApi = {
  getAuditLog: async (limit?: number): Promise<AuditLogItem[]> => {
    const params = limit ? { limit } : {};
    const { data } = await api.get('/governance/audit-log', { params });
    return (data as { items: AuditLogItem[] }).items || [];
  },

  getModelInvocations: async (limit?: number): Promise<ModelInvocationItem[]> => {
    const params = limit ? { limit } : {};
    const { data } = await api.get('/governance/model-invocations', { params });
    return (data as { items: ModelInvocationItem[] }).items || [];
  },

  getDecisions: async (limit?: number): Promise<DecisionRecordItem[]> => {
    const params = limit ? { limit } : {};
    const { data } = await api.get('/governance/decisions', { params });
    return (data as { items: DecisionRecordItem[] }).items || [];
  },
};

// 模型 API
export const modelApi = {
  getStatus: async (): Promise<ModelStatus> => {
    const { data } = await api.get('/model/status');
    return data as ModelStatus;
  },

  getConfig: async (): Promise<ModelConfig> => {
    const { data } = await api.get('/model/config');
    return data as ModelConfig;
  },

  updateConfig: async (config: ModelConfigUpdate): Promise<{ success: boolean; message: string }> => {
    const { data } = await api.post('/model/config', config);
    return data as { success: boolean; message: string };
  },

  resetConfig: async (): Promise<{ success: boolean; message: string }> => {
    const { data } = await api.delete('/model/config');
    return data as { success: boolean; message: string };
  },

  testConfig: async (): Promise<{ success: boolean; message: string; model?: string; status: ModelStatus }> => {
    const { data } = await api.get('/model/config/test');
    return data as { success: boolean; message: string; model?: string; status: ModelStatus };
  },
};

// AI 建议 API
export const aiApi = {
  getOntologySuggestions: async (dataSourceId: number): Promise<unknown> => {
    const { data } = await api.post(`/ai/data-sources/${dataSourceId}/ontology-suggestions`);
    return data;
  },

  getBlueprintDraft: async (dataSourceId: number): Promise<{ blueprint: IndustryBlueprint; usedRemoteModel: boolean; provider: string; model: string; remoteError?: string }> => {
    const { data } = await api.post(`/ai/data-sources/${dataSourceId}/blueprint-draft`);
    return data as { blueprint: IndustryBlueprint; usedRemoteModel: boolean; provider: string; model: string; remoteError?: string };
  },

  getOntologyReasoningChain: async (dataSourceId: number): Promise<OntologyReasoningChainResult> => {
    const { data } = await api.post(`/ai/data-sources/${dataSourceId}/ontology-reasoning-chain`);
    return data as OntologyReasoningChainResult;
  },
};

// 工作流 API
export const workflowApi = {
  list: async (ontologyId?: number): Promise<WorkflowDefinition[]> => {
    const params = ontologyId ? { ontologyId } : {};
    const { data } = await api.get('/workflows', { params });
    return ((data.items || []) as unknown[]).map(normalizeWorkflow);
  },

  get: async (id: number): Promise<WorkflowDefinition> => {
    const { data } = await api.get(`/workflows/${id}`);
    return normalizeWorkflow(data);
  },

  getByObject: async (ontologyId: number, objectCode: string): Promise<WorkflowDefinition> => {
    const { data } = await api.get(`/workflows/by-object/${ontologyId}/${objectCode}`);
    return normalizeWorkflow(data);
  },

  create: async (payload: {
    ontologyId: number; objectCode: string; name: string;
    description?: string; initialState?: string;
  }): Promise<WorkflowDefinition> => {
    const { data } = await api.post('/workflows', payload);
    return normalizeWorkflow(data);
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/workflows/${id}`);
  },

  enterInstance: async (workflowId: number, payload: {
    objectCode: string; instanceId: string;
  }): Promise<WorkflowInstance> => {
    const { data } = await api.post(`/workflows/${workflowId}/enter`, payload);
    return data as WorkflowInstance;
  },

  getInstanceState: async (workflowId: number, instanceId: string): Promise<WorkflowInstance> => {
    const { data } = await api.get(`/workflows/${workflowId}/instances/${instanceId}`);
    return normalizeWorkflowInstance(data);
  },

  getAvailableActions: async (workflowId: number, instanceId: string): Promise<Array<{
    actionCode: string; name: string; toState: string;
  }>> => {
    const { data } = await api.get(`/workflows/${workflowId}/instances/${instanceId}/actions`);
    return (data.actions || []) as Array<{ actionCode: string; name: string; toState: string }>;
  },

  transition: async (workflowId: number, payload: {
    instanceId: string; actionCode: string; actor?: string; reason?: string;
  }): Promise<WorkflowInstance> => {
    const { data } = await api.post(`/workflows/${workflowId}/transitions/run`, payload);
    return data as WorkflowInstance;
  },

  getInstanceHistory: async (workflowId: number, instanceId: string): Promise<WorkflowHistoryItem[]> => {
    const { data } = await api.get(`/workflows/${workflowId}/instances/${instanceId}/history`);
    return (data.items || []) as WorkflowHistoryItem[];
  },
};

// 权限 API
export const permissionApi = {
  getRoles: async (): Promise<PermissionRole[]> => {
    const { data } = await api.get('/permissions/roles');
    return ((data.roles || []) as unknown[]).map(normalizeRole);
  },

  createRole: async (payload: {
    code: string; name: string; description?: string; isSystem?: boolean;
  }): Promise<PermissionRole> => {
    const { data } = await api.post('/permissions/roles', payload);
    return data as PermissionRole;
  },

  getPolicies: async (roleId?: number): Promise<PermissionPolicy[]> => {
    const params = roleId ? { roleId } : {};
    const { data } = await api.get('/permissions/policies', { params });
    return ((data.policies || []) as unknown[]).map(normalizePolicy);
  },

  upsertPolicy: async (payload: {
    roleId: number; objectCode: string; canRead?: boolean; canWrite?: boolean;
    canExecute?: boolean; canDelete?: boolean; filterExpression?: string; description?: string;
  }): Promise<PermissionPolicy> => {
    const { data } = await api.post('/permissions/policies', payload);
    return data as PermissionPolicy;
  },

  check: async (payload: {
    roleCode: string; objectCode: string; operation?: string;
  }): Promise<{ allowed: boolean; reason?: string }> => {
    const { data } = await api.post('/permissions/check', payload);
    return data as { allowed: boolean; reason?: string };
  },
};

// 工具管理 API
export const toolApi = {
  list: async (): Promise<ToolDefinition[]> => {
    const { data } = await api.get('/tools');
    return ((data.tools || []) as unknown[]).map(normalizeTool);
  },

  register: async (payload: {
    code: string; name: string; description?: string; toolType?: string;
    inputSchema?: Record<string, unknown>; riskLevel?: string; requiresReview?: boolean;
  }): Promise<ToolDefinition> => {
    const { data } = await api.post('/tools', payload);
    return data as ToolDefinition;
  },

  authorize: async (payload: {
    roleId: number; toolId: number; allowed?: boolean; maxCallsPerHour?: number;
  }): Promise<ToolAuthorization> => {
    const { data } = await api.post('/tools/authorize', payload);
    return data as ToolAuthorization;
  },

  checkAuth: async (payload: {
    roleCode: string; toolCode: string;
  }): Promise<{ allowed: boolean; reason?: string; riskLevel?: string }> => {
    const { data } = await api.post('/tools/check-auth', payload);
    return data as { allowed: boolean; reason?: string; riskLevel?: string };
  },

  getPendingReviews: async (limit?: number): Promise<ToolExecutionLog[]> => {
    const params = limit ? { limit } : {};
    const { data } = await api.get('/tools/pending-reviews', { params });
    return ((data.items || []) as unknown[]).map(normalizeToolExecution);
  },

  reviewExecution: async (logId: number, payload: {
    reviewer: string; decision: string;
  }): Promise<ToolExecutionLog> => {
    const { data } = await api.post(`/tools/logs/${logId}/review`, payload);
    return data as ToolExecutionLog;
  },
};

// 工作台 API
export const workbenchApi = {
  get: async (decisionLimit = 8): Promise<Workbench> => {
    const { data } = await api.get('/workbench', { params: { decisionLimit } });
    return data as Workbench;
  },
};

// 知识图谱 API
export const graphApi = {
  getOntologyGraph: async (ontologyId: number): Promise<OntologyGraph> => {
    const { data } = await api.get(`/ontologies/${ontologyId}/graph`);
    return data as OntologyGraph;
  },
};

// 文档知识层 API
export const knowledgeApi = {
  listDocuments: async (ontologyId: number): Promise<KnowledgeDocument[]> => {
    const { data } = await api.get(`/ontologies/${ontologyId}/knowledge/documents`);
    return (data.items || []) as KnowledgeDocument[];
  },

  listEntries: async (
    ontologyId: number,
    params: { documentId?: number; status?: string; limit?: number } = {},
  ): Promise<KnowledgeEntryList> => {
    const { data } = await api.get(`/ontologies/${ontologyId}/knowledge/entries`, { params });
    return data as KnowledgeEntryList;
  },

  upload: async (
    ontologyId: number,
    file: File,
    meta: { title?: string; objectCode?: string; ruleCode?: string } = {},
  ): Promise<KnowledgeIngestResult> => {
    const form = new FormData();
    form.append('file', file);
    if (meta.title) form.append('title', meta.title);
    if (meta.objectCode) form.append('objectCode', meta.objectCode);
    if (meta.ruleCode) form.append('ruleCode', meta.ruleCode);
    const { data } = await api.post(`/ontologies/${ontologyId}/knowledge/documents`, form);
    return data as KnowledgeIngestResult;
  },

  review: async (
    entryId: number,
    payload: { status: string; objectCode?: string; ruleCode?: string },
  ): Promise<KnowledgeEntry> => {
    const { data } = await api.post(`/knowledge/entries/${entryId}/review`, payload);
    return data as KnowledgeEntry;
  },
};

// 会话与反馈 API
export const conversationApi = {
  list: async (params: { status?: string; limit?: number } = {}): Promise<Conversation[]> => {
    const { data } = await api.get('/conversations', { params });
    return (data.items || []) as Conversation[];
  },

  get: async (sessionId: string): Promise<Conversation> => {
    const { data } = await api.get(`/conversations/${encodeURIComponent(sessionId)}`);
    return data as Conversation;
  },

  escalate: async (sessionId: string, payload: { assignee?: string; reason?: string }) => {
    const { data } = await api.post(`/conversations/${encodeURIComponent(sessionId)}/escalate`, payload);
    return data;
  },

  setStatus: async (sessionId: string, status: string) => {
    const { data } = await api.patch(`/conversations/${encodeURIComponent(sessionId)}/status`, { status });
    return data;
  },

  submitFeedback: async (
    messageId: number,
    payload: { rating: string; comment?: string; correction?: string; objectCode?: string; ruleCode?: string },
  ) => {
    const { data } = await api.post(`/conversations/messages/${messageId}/feedback`, payload);
    return data;
  },
};

export const feedbackApi = {
  list: async (params: { status?: string; rating?: string; limit?: number } = {}): Promise<{
    items: AnswerFeedback[];
    summary: FeedbackSummary;
  }> => {
    const { data } = await api.get('/feedback', { params });
    return data as { items: AnswerFeedback[]; summary: FeedbackSummary };
  },

  resolve: async (feedbackId: number, resolution = 'resolved') => {
    const { data } = await api.post(`/feedback/${feedbackId}/resolve`, { resolution });
    return data;
  },
};

// 平台备份 API
export interface BackupItem {
  name: string;
  path: string;
  size: number;
  created_at: string;
}

export const backupApi = {
  list: async (): Promise<BackupItem[]> => {
    const { data } = await api.get('/admin/backup/list');
    return ((data as { backups?: unknown[] }).backups || []) as BackupItem[];
  },

  create: async (): Promise<BackupItem> => {
    const { data } = await api.post('/admin/backup/create');
    return data as BackupItem;
  },

  download: async (name: string): Promise<Blob> => {
    const { data } = await api.get(`/admin/backup/download/${encodeURIComponent(name)}`, {
      responseType: 'blob',
    });
    return data as Blob;
  },

  restore: async (name: string): Promise<{ name: string; restoredAt: string }> => {
    const { data } = await api.post(`/admin/backup/restore/${encodeURIComponent(name)}`);
    return data as { name: string; restoredAt: string };
  },
};

export default api;

export const tenancyApi = {
  // Multi-tenancy is opt-in, so an empty list on a single-tenant deployment is the expected
  // answer rather than a failure -- the backend says so explicitly and this passes it through.
  list: async (): Promise<TenantList> => {
    const { data } = await api.get('/tenants');
    return data as TenantList;
  },

  create: async (tenant: string): Promise<TenantSummary> => {
    const { data } = await api.post('/tenants', { tenant });
    return data as TenantSummary;
  },

  statistics: async (tenant: string): Promise<TenantStatistics> => {
    const { data } = await api.get(`/tenants/${encodeURIComponent(tenant)}/statistics`);
    return data as TenantStatistics;
  },

  quotas: async (tenant: string): Promise<TenantQuotas> => {
    const { data } = await api.get(`/tenants/${encodeURIComponent(tenant)}/quotas`);
    return data as TenantQuotas;
  },

  quotaResources: async (): Promise<QuotaResource[]> => {
    const { data } = await api.get('/quota-resources');
    return ((data as { items?: QuotaResource[] }).items || []) as QuotaResource[];
  },

  setQuota: async (tenant: string, resource: string, limit: number, note = ''): Promise<unknown> => {
    const { data } = await api.put(`/tenants/${encodeURIComponent(tenant)}/quotas`, { resource, limit, note });
    return data;
  },
};

export const ssoApi = {
  status: async (): Promise<SsoStatus> => {
    const { data } = await api.get('/auth/sso');
    return data as SsoStatus;
  },

  listMappings: async (): Promise<SsoGroupMapping[]> => {
    const { data } = await api.get('/auth/sso/mappings');
    return ((data as { items?: SsoGroupMapping[] }).items || []) as SsoGroupMapping[];
  },

  // The platform decides what a group grants; the provider only asserts who the user is.
  declare: async (providerGroup: string, roleCode: string, note = ''): Promise<unknown> => {
    const { data } = await api.put('/auth/sso/mappings', { providerGroup, roleCode, note });
    return data;
  },

  remove: async (providerGroup: string): Promise<unknown> => {
    const { data } = await api.delete(`/auth/sso/mappings/${encodeURIComponent(providerGroup)}`);
    return data;
  },
};

export const auditApi = {
  /** What the report can answer, named by the audit question rather than by the table. */
  sections: async (): Promise<AuditReportSection[]> => {
    const { data } = await api.get('/governance/audit-report/sections');
    return ((data as { items?: AuditReportSection[] }).items || []) as AuditReportSection[];
  },

  /**
   * One report over one period. Both ends are required and there is no default window:
   * a report over "everything" invites the reader to treat it as a statement about a period
   * it does not describe.
   */
  report: async (start: string, end: string, ontologyId?: number): Promise<AuditReport> => {
    const params: Record<string, string | number> = { start, end };
    if (ontologyId) params.ontologyId = ontologyId;
    const { data } = await api.get('/governance/audit-report', { params });
    return data as AuditReport;
  },
};
