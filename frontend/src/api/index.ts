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
  InstanceAssessResult,
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
  WorkflowInstance,
  WorkflowHistoryItem,
  PermissionRole,
  PermissionPolicy,
  ToolDefinition,
  ToolExecutionLog,
  ToolAuthorization,
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
      return Promise.reject(new Error(detail || '登录已失效，请重新登录。'));
    }
    if (status === 403) {
      const capability = error?.response?.data?.requiredCapability;
      return Promise.reject(
        new Error(detail || `当前角色无权执行该操作${capability ? `（需要 ${capability}）` : ''}。`),
      );
    }
    if (detail) {
      return Promise.reject(new Error(detail));
    }
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

  exportUrl: (ontologyId: number, format: 'jsonld' | 'turtle'): string => `/api/ontologies/${ontologyId}/export?format=${format}`,
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

  explain: async (objectCode: string, instanceId: string, ontologyId?: number): Promise<InstanceExplainResult> => {
    const params = ontologyId ? { ontologyId } : {};
    const { data } = await api.get(`/semantic/objects/${objectCode}/instances/${instanceId}/explain`, { params });
    return data as InstanceExplainResult;
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
      recommendation: data.nextAction ?? data.decision?.recommendation ?? '',
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
    return (data.items || []) as WorkflowDefinition[];
  },

  get: async (id: number): Promise<WorkflowDefinition> => {
    const { data } = await api.get(`/workflows/${id}`);
    return data as WorkflowDefinition;
  },

  getByObject: async (ontologyId: number, objectCode: string): Promise<WorkflowDefinition> => {
    const { data } = await api.get(`/workflows/by-object/${ontologyId}/${objectCode}`);
    return data as WorkflowDefinition;
  },

  create: async (payload: {
    ontologyId: number; objectCode: string; name: string;
    description?: string; initialState?: string;
  }): Promise<WorkflowDefinition> => {
    const { data } = await api.post('/workflows', payload);
    return data as WorkflowDefinition;
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
    return data as WorkflowInstance;
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
    return (data.roles || []) as PermissionRole[];
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
    return (data.policies || []) as PermissionPolicy[];
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
    return (data.tools || []) as ToolDefinition[];
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
    return (data.items || []) as ToolExecutionLog[];
  },

  reviewExecution: async (logId: number, payload: {
    reviewer: string; decision: string;
  }): Promise<ToolExecutionLog> => {
    const { data } = await api.post(`/tools/logs/${logId}/review`, payload);
    return data as ToolExecutionLog;
  },
};

export default api;
