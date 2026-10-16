import axios from 'axios';
import { clearSession, getToken } from '../auth/session';
import { appHref } from '../routing';
import { translateNow } from '../i18n/translate';
import { MESSAGES, type MessageKey } from '../i18n/messages';
import type { AuthUser } from '../auth/session';
import {
  filenameFromDisposition,
  normalizeDataSource,
  normalizePolicy,
  normalizeRole,
  normalizeSourceApi,
  normalizeSourceTable,
  normalizeTool,
  normalizeToolExecution,
  normalizeWorkflow,
  normalizeWorkflowInstance,
} from './normalise';
import type {
  DataSource,
  DataSourceCreate,
  OnboardingRunCreate,
  OnboardingResult,
  SourceApi,
  SourceApiCreate,
  SourceScanResult,
  SourceTable,
  DataSourceReadiness,
  SchemaDriftResult,
  SemanticCoverageResult,
  OperationBindingResult,
  OntologyDraftCreate,
  BulkMappingReviewCreate,
  BusinessRule,
  Ontology,
  PageInfo,
  ToolExecutionReview,
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
  OntologyPublication,
  OntologyReasoningChainResult,
  RuleWordImportResult,
  KnowledgeBase,
  SourceTableRows,
  DataSourceInitializeResult,
  ReasoningChain,
  AgentRole,
  AgentChatPayload,
  AgentChatResult,
  WorkflowDefinition,
  WorkflowInstance,
  WorkflowHistoryItem,
  PermissionRole,
  SemanticMapping,
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

/**
 * Fetch a protected file and hand it to the browser as a download.
 *
 * `window.open(url, '_blank')` is how the four export buttons and the kernel-package button
 * did this, and it cannot work: this platform authenticates with an `Authorization: Bearer`
 * header and deliberately sets no cookie (`SECURITY.md`), so a URL the browser opens on its
 * own carries no credential. Every one of those five buttons opened a tab containing
 * `{"detail":"缺少访问令牌"}`.
 *
 * A download therefore has to be a request *this* module makes -- through the same axios
 * instance as everything else, so it carries the token and goes through the error interceptor
 * that turns a refusal into something readable. The response is a blob, and the browser saves
 * it through a temporary object URL that is revoked either way: revoking only on success leaks
 * the blob for the rest of the session, and never revoking leaks it for the life of the tab.
 */
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  const response = await api.get(url, { responseType: 'blob' });
  const filename = filenameFromDisposition(response.headers?.['content-disposition']) ?? fallbackName;
  const objectUrl = URL.createObjectURL(response.data as Blob);
  try {
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    link.click();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}


/**
 * The page block a list endpoint sends, with the unpaginated case spelled out.
 *
 * Every one of these endpoints returns the whole list when the caller does not ask for a page,
 * and a `pagination` block either way. This is the one place that decides what a missing block
 * means -- an older server, or an endpoint that has not been given one yet -- so a screen never
 * has to.
 */
function pageInfo(payload: unknown): PageInfo {
  const block = (payload as { pagination?: Partial<PageInfo> })?.pagination;
  return {
    limit: block?.limit ?? null,
    offset: block?.offset ?? 0,
    total: block?.total ?? 0,
    hasMore: block?.hasMore ?? false,
  };
}

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
 * The console's own sentence for a refusal the server named, or `''` when it has none.
 *
 * The server sends both: the sentence it wrote (`detail`, Chinese, and what the CLI prints)
 * and a code identifying which refusal it is. When the dictionary knows the code, the console
 * says *its* sentence in the reader's language and the server's is not shown at all -- the
 * point of the code. When it does not, this returns nothing and the caller falls back to
 * `detail`, which is still true and still readable.
 *
 * The facts travel with the code so the sentence can name what it is about. A key that exists
 * but whose placeholders do not match the facts would render a literal brace, so the lookup
 * treats a missing placeholder as a miss and falls back -- the server's sentence, in the wrong
 * language, is better than a broken template.
 */
function codedReason(payload: unknown): string {
  const code = (payload as { code?: unknown })?.code;
  if (typeof code !== 'string' || !code) return '';
  const facts = (payload as { facts?: unknown })?.facts;
  const key = `errors.api.${code}` as MessageKey;
  if (!(key in MESSAGES)) return '';
  const text = translateNow(key, (facts ?? {}) as Record<string, string>);
  // `translateNow` renders `⟦key⟧` for a key it cannot find; this checks the *other* failure,
  // an unfilled placeholder, which is the one a fact-name mismatch produces.
  return /\{\w+\}|⟦/.test(text) ? '' : text;
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
    const payload = error?.response?.data;
    const detail = payload?.detail;
    // The reader's language wins over the server's when the console can name the refusal.
    const named = codedReason(payload);
    if (status === 401) {
      clearSession();
      // Both halves of this used to compare against the *router* path while the address bar
      // holds the mounted one. In production the app lives at `/admin`, so the guard never
      // recognised the login page and the redirect asked the server for `/login` -- which the
      // SPA is not mounted at, and which the auth middleware answers with
      // `{"detail":"缺少访问令牌"}`. Every 401, including the one from the login page itself,
      // ended on a page of raw JSON.
      const loginPath = appHref('login');
      if (!window.location.pathname.startsWith(loginPath)) {
        window.location.assign(loginPath);
      }
      return Promise.reject(new ApiError(named || detail || translateNow('errors.sessionExpired')));
    }
    if (status === 403) {
      // `named` carries the role and the capability it was missing, because the middleware
      // sends them as facts. It falls back to the server's sentence, and then to a generic
      // one, for the 403s that come from something other than this platform's own middleware.
      return Promise.reject(new ApiError(named || detail || translateNow('errors.forbidden')));
    }
    if (named || detail) {
      return Promise.reject(new ApiError(named || detail));
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

  initialize: async (id: number): Promise<DataSourceInitializeResult> => {
    const { data } = await api.post(`/data-sources/${id}/initialize`);
    return data;
  },

  getReasoningChain: async (id: number): Promise<ReasoningChain> => {
    const { data } = await api.get(`/data-sources/${id}/reasoning-chain`);
    return data as ReasoningChain;
  },

  // The counts are per table, not totals: the response is
  // `{dataSourceId, tables: [{table, columns, foreignKeys}]}`. The declared type said three
  // numbers, which nothing renders -- the page refreshes and shows a toast -- so it was
  // wrong without being visible, which is the kind of wrong this file keeps clearing out.
  scan: async (id: number): Promise<SourceScanResult> => {
    const { data } = await api.post(`/data-sources/${id}/scan`);
    return data as SourceScanResult;
  },

  getApis: async (
    id: number,
    options: { limit?: number; offset?: number } = {},
  ): Promise<{ items: SourceApi[]; pagination: PageInfo }> => {
    const params: Record<string, number> = {};
    if (options.limit != null) {
      params.limit = options.limit;
      params.offset = options.offset ?? 0;
    }
    const { data } = await api.get(`/data-sources/${id}/apis`, { params });
    const items = ((data as { apis?: unknown[] }).apis || []).map(normalizeSourceApi);
    return { items, pagination: pageInfo(data) };
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

  /**
   * Download the scaffolded kernel package for a data source.
   *
   * Was `kernelPackageUrl(...)`, a string the page handed to `window.open` -- which carries no
   * token, so the button opened a tab of 401 JSON. See `downloadFile`.
   */
  downloadKernelPackage: async (dataSourceId: number): Promise<void> =>
    downloadFile(`/data-sources/${dataSourceId}/kernel-package/download`, `kernel-package-${dataSourceId}.zip`),
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
  list: async (options: { limit?: number; offset?: number } = {}): Promise<Ontology[]> => {
    const params: Record<string, number> = {};
    if (options.limit != null) {
      params.limit = options.limit;
      params.offset = options.offset ?? 0;
    }
    const { data } = await api.get('/ontologies', { params });
    return (data.items || data.ontologies || []) as Ontology[];
  },

  /** One page of ontology versions, with the count a pager needs. */
  listPage: async (options: { limit: number; offset: number }): Promise<{ items: Ontology[]; pagination: PageInfo }> => {
    const { data } = await api.get('/ontologies', { params: options });
    return { items: (data.items || data.ontologies || []) as Ontology[], pagination: pageInfo(data) };
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

  /**
   * Mappings of one ontology. Paged when `limit` is given, and the whole list when it is not.
   *
   * This is the list with the largest realistic length in the console: a row is written per
   * mapped column, so a legacy schema with hundreds of tables produces thousands of them on the
   * queue that gates publication -- which the page used to load in one piece and hand to antd
   * to paginate in the browser.
   */
  getMappings: async (
    ontologyId: number,
    options: { status?: string; limit?: number; offset?: number } = {},
  ): Promise<{ items: SemanticMapping[]; pagination: PageInfo }> => {
    const params: Record<string, string | number> = {};
    if (options.status) params.status = options.status;
    if (options.limit != null) {
      params.limit = options.limit;
      params.offset = options.offset ?? 0;
    }
    const { data } = await api.get(`/ontologies/${ontologyId}/mappings`, { params });
    return {
      items: (data.items || []) as SemanticMapping[],
      pagination: (data.pagination ?? { limit: null, offset: 0, total: 0, hasMore: false }) as PageInfo,
    };
  },

  /**
   * Bulk-review every pending mapping of an ontology.
   *
   * No `reviewer` argument, for the same reason `publish` has no `publisher`: the server
   * credits the authenticated principal, and its request model declares `status` and `note`
   * only. A `reviewer` sent from here was dropped on the floor while looking like it decided
   * who the audit recorded.
   *
   * `note` is a *reviewer's* note and is persisted into `semantic_mapping.evidence`. The
   * default is empty rather than a canned sentence: a system-generated note written here
   * would be stored in the language the console happened to be in, and no language switch
   * afterwards can reach it -- the provenance is already recorded structurally in
   * `audit_log` (`action`, `count`, `status`).
   */
  reviewMappings: async (ontologyId: number, payload: BulkMappingReviewCreate): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/mappings/review`, payload);
    return data;
  },

  /**
   * Publish a version. No `publisher` argument: the audit credits the authenticated caller,
   * and the server's request model does not declare one -- so a value sent here looked like it
   * decided who was recorded while Pydantic dropped it on the floor.
   */
  publish: async (ontologyId: number): Promise<OntologyPublication> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/publish`, {});
    return data as OntologyPublication;
  },

  /**
   * Derive a new draft version. No `actor` argument: `OntologyDeriveCreate` declares
   * `version` alone and the server credits the authenticated caller, so the `actor` this
   * used to send was dropped without an error.
   */
  derive: async (ontologyId: number, version: string): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/derive`, { version });
    return data;
  },

  getRules: async (
    ontologyId: number,
    options: { limit?: number; offset?: number } = {},
  ): Promise<{ items: BusinessRule[]; pagination: PageInfo }> => {
    const params: Record<string, number> = {};
    if (options.limit != null) {
      params.limit = options.limit;
      params.offset = options.offset ?? 0;
    }
    const { data } = await api.get(`/ontologies/${ontologyId}/rules`, { params });
    return { items: (data.items || []) as BusinessRule[], pagination: pageInfo(data) };
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

  /**
   * Download an ontology in one of the four formats the endpoint takes.
   *
   * `jsonld`/`turtle` are this platform's vocabulary; `owl`/`shacl` are the standard ones.
   * Was `exportUrl(...)` -- see `downloadFile` for why a URL opened by the browser cannot
   * download from an API that authenticates with a header.
   */
  downloadExport: async (
    ontologyId: number,
    format: 'jsonld' | 'turtle' | 'owl' | 'shacl',
  ): Promise<void> =>
    downloadFile(`/ontologies/${ontologyId}/export?format=${format}`, `ontology-${ontologyId}.${format}`),
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
    // Normalised like the rest of this file. `get_available_actions` returns
    // `workflow_transition` rows verbatim -- `action_code`, `to_state` -- and this call was
    // the one place that merely asserted camelCase: every action button rendered
    // 「提交审核 → 」 with no target state, and posting it sent no `actionCode` at all, which
    // the API refuses with 422. A core governance action, unusable, reporting 「转移失败」.
    return (data.actions || []).map((item: any) => ({
      ...item,
      actionCode: item.actionCode ?? item.action_code ?? '',
      toState: item.toState ?? item.to_state ?? '',
      name: item.name ?? item.action_code ?? '',
    }));
  },

  transition: async (workflowId: number, payload: {
    instanceId: string; actionCode: string; actor?: string; reason?: string;
  }): Promise<WorkflowInstance> => {
    const { data } = await api.post(`/workflows/${workflowId}/transitions/run`, payload);
    return normalizeWorkflowInstance(data);
  },

  getInstanceHistory: async (workflowId: number, instanceId: string): Promise<WorkflowHistoryItem[]> => {
    const { data } = await api.get(`/workflows/${workflowId}/instances/${instanceId}/history`);
    // `workflow_history` rows, same spelling problem: the timeline read
    // `h.fromState`/`h.toState`/`h.actor`/`h.createdAt` off snake_case and rendered
    // 「初始 → 」 with an empty actor and time.
    return (data.items || []).map((item: any) => ({
      ...item,
      instanceWorkflowId: item.instanceWorkflowId ?? item.instance_workflow_id ?? 0,
      fromState: item.fromState ?? item.from_state ?? '',
      toState: item.toState ?? item.to_state ?? '',
      actionCode: item.actionCode ?? item.action_code ?? '',
      actor: item.actor ?? '',
      reason: item.reason ?? '',
      metadata: item.metadata ?? '',
      createdAt: item.createdAt ?? item.created_at ?? '',
    }));
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

  /**
   * Review a tool execution that was held for approval. No `reviewer` argument: the server's
   * request model declares `decision` alone and credits the authenticated principal, so the
   * `reviewer` this used to require was dropped -- while reading, at the call site, as though
   * it decided who the audit recorded.
   */
  reviewExecution: async (logId: number, payload: ToolExecutionReview): Promise<ToolExecutionLog> => {
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

  /**
   * Save an archive to the user's disk. Returns when the browser has been handed the file.
   *
   * The page used to do the object-URL dance itself and name the file `${name}.tar.gz` from
   * the list row. That name is the server's to choose -- it is the archive it produced, and it
   * sets `Content-Disposition` saying so -- and the dance is the same one three callers now
   * need, so it lives in `downloadFile`.
   */
  download: async (name: string): Promise<void> =>
    downloadFile(`/admin/backup/download/${encodeURIComponent(name)}`, `${name}.tar.gz`),

  restore: async (name: string): Promise<{ name: string; restoredAt: string; safetyCopy?: string }> => {
    const { data } = await api.post(`/admin/backup/restore/${encodeURIComponent(name)}`);
    return data as { name: string; restoredAt: string; safetyCopy?: string };
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
