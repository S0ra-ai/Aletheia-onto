// 数据源相关类型
export interface DataSource {
  id: number;
  name: string;
  sourceType: string;
  connectionUri: string;
  apiBaseUrl: string;
  apiHeadersConfigured: boolean;
  apiHeaderNames: string[];
  domain: string;
  systemCategory: string;
  capabilities: string[];
  createdAt?: string;
}

export interface DataSourceCreate {
  name: string;
  sourceType?: string;
  connectionUri: string;
  apiBaseUrl?: string;
  apiHeaders?: Record<string, string>;
  domain?: string;
  systemCategory?: string;
  capabilities?: string[];
}

export interface OnboardingRunCreate extends DataSourceCreate {
  blueprintId?: string;
  ontologyName?: string;
  generateOntology?: boolean;
  openApiUrl?: string;
  openApiSpec?: Record<string, unknown>;
}

export interface OnboardingStep {
  code: string;
  status: string;
  message: string;
  detail: Record<string, unknown>;
}

export interface OnboardingResult {
  dataSource: DataSource;
  connection: { reachable: boolean; status: string; message: string };
  scan?: unknown;
  ontology?: OntologyDetail | null;
  readiness: DataSourceReadiness;
  steps: OnboardingStep[];
  status: string;
}

export interface SourceApi {
  id: number;
  dataSourceId: number;
  operationCode: string;
  name: string;
  method: string;
  path: string;
  semanticAction: string;
  requestSchema: Record<string, unknown>;
  responseSchema: Record<string, unknown>;
}

export interface SourceApiCreate {
  operationCode: string;
  name: string;
  method: string;
  path: string;
  semanticAction?: string;
  requestSchema?: Record<string, unknown>;
  responseSchema?: Record<string, unknown>;
}

export interface SourceTable {
  id: number;
  tableName: string;
  rowCount: number;
  primaryKey: string;
  scannedAt: string;
}

export interface ReadinessCheck {
  code: string;
  name: string;
  passed: boolean;
  evidence: string;
  remediation: string;
  weight: number;
}

export interface DataSourceReadiness {
  dataSourceId: number;
  name: string;
  domain: string;
  score: number;
  status: 'ready' | 'partial' | 'blocked';
  summary: {
    tables: number;
    columns: number;
    foreignKeys: number;
    apis: number;
    ontologies: number;
    confirmedMappings: number;
    pendingMappings: number;
  };
  checks: ReadinessCheck[];
  gaps: ReadinessCheck[];
  nextActions: string[];
}

export interface SchemaDriftSummary {
  addedTables: number;
  removedTables: number;
  changedTables: number;
  addedColumns: number;
  removedColumns: number;
  changedColumns: number;
  impactedObjects: number;
  impactedMappings: number;
  impactedRules: number;
}

export interface SchemaDriftColumn {
  columnName: string;
  dataType: string;
  nullable: boolean;
  isPrimaryKey: boolean;
  ordinal: number;
}

export interface SchemaDriftColumnChange {
  columnName: string;
  changes: Record<string, { old: unknown; new: unknown }>;
  old: SchemaDriftColumn;
  new: SchemaDriftColumn;
}

export interface SchemaDriftTableChange {
  tableName: string;
  primaryKeyChanged: boolean;
  oldPrimaryKey?: string | null;
  newPrimaryKey?: string | null;
  rowCountChanged: boolean;
  oldRowCount: number;
  newRowCount: number;
  addedColumns: SchemaDriftColumn[];
  removedColumns: SchemaDriftColumn[];
  changedColumns: SchemaDriftColumnChange[];
}

export interface SchemaDriftImpactItem {
  id: number;
  ontologyId: number;
  code?: string;
  name?: string;
  sourceTable?: string;
  mappingType?: string;
  sourceRef?: string;
  targetRef?: string;
  scopeObjectCode?: string;
  status?: string;
  impactReason: string;
}

export interface SchemaDriftResult {
  dataSourceId: number;
  status: 'not_scanned' | 'no_drift' | 'drift_detected';
  summary: SchemaDriftSummary;
  addedTables: Array<{
    tableName: string;
    rowCount: number;
    primaryKey?: string | null;
    columns: SchemaDriftColumn[];
  }>;
  removedTables: Array<{
    tableName: string;
    rowCount: number;
    primaryKey?: string | null;
    columns: SchemaDriftColumn[];
  }>;
  changedTables: SchemaDriftTableChange[];
  impacts: {
    objects: SchemaDriftImpactItem[];
    mappings: SchemaDriftImpactItem[];
    rules: SchemaDriftImpactItem[];
  };
  nextActions: string[];
}

export interface SemanticCoverageSummary {
  businessObjects: number;
  fullyCoveredObjects: number;
  partialObjects: number;
  blockedObjects: number;
  attributes: number;
  confirmedMappings: number;
  pendingMappings: number;
  rules: number;
  operations: number;
  semanticOperations: number;
  executableOperations: number;
}

export interface SemanticCoverageOperation {
  operationCode: string;
  name: string;
  method: string;
  path: string;
  semanticAction: string;
  objectCode: string;
  automationReady: boolean;
}

export interface SemanticCoverageObject {
  ontologyId: number;
  ontologyName: string;
  ontologyVersion: string;
  ontologyStatus: string;
  objectId: number;
  objectCode: string;
  objectName: string;
  sourceTable: string;
  primaryKey?: string | null;
  attributeCount: number;
  confirmedMappings: number;
  pendingMappings: number;
  rejectedMappings: number;
  ruleCount: number;
  operationCount: number;
  automationReady: boolean;
  status: 'ready' | 'partial' | 'blocked';
  gaps: string[];
  operations: SemanticCoverageOperation[];
}

export interface SemanticCoverageResult {
  dataSourceId: number;
  name: string;
  domain: string;
  status: 'not_modeled' | 'ready' | 'partial' | 'blocked';
  score: number;
  summary: SemanticCoverageSummary;
  objects: SemanticCoverageObject[];
  operations: SemanticCoverageOperation[];
  nextActions: string[];
}

export interface OperationBindingItem {
  operationCode: string;
  name: string;
  method: string;
  path: string;
  semanticAction: string;
  objectCode: string;
  actionCode: string;
  status: 'ready' | 'bound' | 'incomplete' | 'unbound' | 'invalid';
  automationReady: boolean;
  gaps: string[];
}

export interface OperationBindingResult {
  dataSourceId: number;
  name: string;
  status: 'ready' | 'partial' | 'blocked';
  summary: {
    operations: number;
    boundOperations: number;
    readyOperations: number;
    unboundOperations: number;
    invalidActions: number;
    blockedOperations: number;
  };
  items: OperationBindingItem[];
  nextActions: string[];
}

// 元数据相关类型
export interface ScanResult {
  tables: number;
  columns: number;
  foreignKeys: number;
}

// 本体相关类型
export interface Ontology {
  id: number;
  name: string;
  domain?: string;
  dataSourceId?: number;
  version: string;
  status: string;
  createdAt?: string;
  publishedAt?: string | null;
  /** Number of modelled business objects; distinguishes a real ontology from an empty one. */
  objectCount?: number;
}

export interface OntologyDraftCreate {
  dataSourceId: number;
  name?: string;
  domain?: string;
  blueprintId?: string;
}

export interface IndustryBlueprint {
  id: string;
  name: string;
  domain: string;
  description: string;
  objectHints: Record<string, string>;
  attributeHints: Record<string, string>;
  rules: Array<{
    code: string;
    name: string;
    rule_type: string;
    scope_object_code: string;
    expression: string;
    severity: string;
    natural_language: string;
  }>;
  tableKeywords: string[];
  capabilityTags: string[];
}

export interface BusinessObject {
  id: number;
  ontologyId: number;
  code: string;
  name: string;
  description: string;
  sourceTable: string;
}

export interface BusinessAttribute {
  id: number;
  objectId: number;
  code: string;
  name: string;
  dataType: string;
  sourceColumn: string;
  description: string;
}

export interface BusinessRelation {
  id: number;
  sourceObjectId: number;
  targetObjectId: number;
  type: string;
  name: string;
  sourceForeignKey: string;
}

export interface OntologyDetail {
  ontology: Ontology;
  objects: BusinessObject[];
  attributes: BusinessAttribute[];
  relations: BusinessRelation[];
  mappings: SemanticMapping[];
  rules: BusinessRule[];
}

export interface ReleaseReadinessGate {
  code: string;
  name: string;
  passed: boolean;
  severity: 'blocker' | 'warning';
  evidence: string;
  remediation: string;
}

export interface ReleaseReadinessResult {
  ontologyId: number;
  name: string;
  version: string;
  status: 'ready' | 'review' | 'blocked';
  summary: {
    objects: number;
    dataSources: number;
    confirmedMappings: number;
    pendingMappings: number;
    rejectedMappings: number;
    publishedRules: number;
    passedGates: number;
    totalGates: number;
    blockers: number;
    warnings: number;
  };
  gates: ReleaseReadinessGate[];
  dataSources: Array<{
    dataSourceId: number;
    readiness: DataSourceReadiness;
    coverage: SemanticCoverageResult;
    schemaDrift: SchemaDriftResult | { status: 'error'; error: string };
  }>;
  nextActions: string[];
}

// 语义映射相关类型
export interface SemanticMapping {
  id: number;
  ontologyId: number;
  mappingType: string;
  sourceRef?: string;
  targetRef?: string;
  sourceTable: string;
  sourceColumn?: string;
  targetObjectCode: string;
  targetAttributeCode?: string;
  confidence: number;
  status: string;
  evidence?: string;
  reviewer?: string;
  reviewedAt?: string | null;
}

// 业务规则相关类型
export interface BusinessRule {
  id: number;
  ontologyId?: number;
  code: string;
  name: string;
  ruleType: string;
  scopeObjectCode: string;
  expression: string;
  severity: string;
  naturalLanguage: string;
  status: string;
  priority?: number;
  category?: string;
  effectiveStart?: string;
  effectiveEnd?: string;
  dependsOn?: string[];
}

// 语义服务相关类型
export interface InstanceExplainResult {
  objectCode: string;
  instanceId: string;
  attributes: Record<string, unknown>;
  relations: Record<string, unknown>[];
  explanation: string;
}

export interface InstanceAssessResult {
  objectCode: string;
  instanceId: string;
  decision: 'approved' | 'review' | 'blocked';
  rulesHit: RuleHit[];
  explanation: string;
}

export interface DecisionConsistencyItem {
  instanceId: string;
  decision: 'approved' | 'review' | 'blocked';
  recommendation: string;
  decisionId: string;
  failedRules: string[];
  failedRuleCount: number;
}

export interface DecisionConsistencyResult {
  ontologyId: number;
  objectCode: string;
  sampleSize: number;
  assessed: number;
  errorCount: number;
  status: 'consistent' | 'mixed' | 'mixed_with_blockers' | 'incomplete' | 'empty';
  summary: {
    approved: number;
    review: number;
    blocked: number;
    errors: number;
    uniqueDecisionStatuses: number;
  };
  ruleFailures: Array<{
    ruleCode: string;
    failures: number;
  }>;
  items: DecisionConsistencyItem[];
  errors: Array<{
    instanceId: string;
    error: string;
  }>;
  nextActions: string[];
}

export interface RuleHit {
  ruleCode: string;
  ruleName: string;
  passed: boolean;
  message: string;
}

export interface OperationPreflightResult {
  operationCode: string;
  instanceId: string;
  decision: 'approved' | 'review' | 'blocked';
  rulesHit: RuleHit[];
  explanation: string;
  recommendation: string;
}

export interface OperationExecuteResult {
  operationCode: string;
  instanceId: string;
  decision: 'approved' | 'review' | 'blocked';
  executed: boolean;
  status: string;
  message: string;
  recommendation: string;
  execution?: {
    method: string;
    path: string;
    semanticAction: string;
    payload: Record<string, unknown>;
    dryRun: boolean;
    remote?: unknown;
  } | null;
  rulesHit: RuleHit[];
}

export interface NaturalLanguageQueryPayload {
  question: string;
  ontologyId?: number;
  dataSourceId?: number;
  objectCode?: string;
  instanceId?: string;
  history?: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
  useModel?: boolean;
}

export interface NaturalLanguageQueryResult {
  question: string;
  intent: 'compliance_assessment' | 'explain_instance' | 'operation_preflight' | 'decision_consistency' | 'unknown';
  answer: string;
  confidence: number;
  resolved: {
    ontologyId: number;
    dataSourceId?: number | null;
    objectCode: string;
    instanceId?: string | null;
    operationCode?: string | null;
  };
  evidence: Record<string, unknown>;
  nextActions: string[];
  model?: {
    configured: boolean;
    usedForUnderstanding: boolean;
    usedForSummary: boolean;
    name: string;
    fallbackReason?: string;
  };
}

export interface OntologyReasoningChain {
  summary: string;
  reasoningSteps: string[];
  proposedObjects: Array<Record<string, unknown>>;
  proposedRelations: Array<Record<string, unknown>>;
  proposedRules: Array<Record<string, unknown>>;
  buildPlan: string[];
  questionsForUser: string[];
}

export interface OntologyReasoningChainResult {
  provider: string;
  model: string;
  usedRemoteModel: boolean;
  remoteError?: string;
  chain: OntologyReasoningChain;
}

export interface RuleWordImportResult {
  ontologyId: number;
  file: {
    name: string;
    size: number;
    md5: string;
  };
  rules: Array<{
    code: string;
    name: string;
    ruleType: string;
    scopeObjectCode: string;
    expression: string;
    severity: string;
    naturalLanguage: string;
    status: string;
  }>;
  warnings: string[];
  applied: boolean;
  imported: unknown[];
  errors: Array<{
    code: string;
    error: string;
  }>;
  importedCount: number;
  errorCount: number;
}

export interface KnowledgeBase {
  dataSourceId: number;
  name: string;
  sourceType: 'sqlite' | 'mysql' | 'postgresql';
  domain: string;
  ontologyId: number;
  ontologyName: string;
  version: string;
  status: string;
  objects: Array<{ code: string; name: string }>;
  objectCodes: string[];
}

export interface SourceTableRows {
  dataSourceId: number;
  tableName: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  page: { limit: number; offset: number; total: number; hasMore: boolean };
}

export interface ReasoningChain extends KnowledgeBase {
  initialized: boolean;
  relations: Array<{ code: string; name: string; relationType: string; sourceObject: string; targetObject: string }>;
  rules: Array<{ code: string; name: string; ruleType: string; scopeObjectCode: string; expression: string; severity: string; naturalLanguage: string; status: string }>;
  steps: Array<{ type: string; label: string }>;
}

export interface DecisionRecordItem {
  id: number;
  decisionId: string;
  decisionType: string;
  ontologyId?: number;
  objectCode: string;
  instanceId: string;
  operationCode: string;
  status: string;
  recommendation: string;
  inputRef: Record<string, unknown>;
  ruleResults: unknown[];
  evidence: Record<string, unknown>;
  actor: string;
  createdAt: string;
}

// 治理审计相关类型
export interface AuditLogItem {
  actor: string;
  action: string;
  targetType: string;
  targetId: string;
  detail: string;
  createdAt: string;
}

export interface ModelInvocationItem {
  provider: string;
  model: string;
  purpose: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  status: string;
  error?: string;
  createdAt: string;
}

// 演示相关类型
export interface DemoBootstrapResult {
  dataSource: DataSource;
  scan: ScanResult;
  ontology: Ontology;
}

// 通用响应类型
export interface ApiResponse<T> {
  data: T;
  message?: string;
}

// 模型状态
export interface ModelStatus {
  configured: boolean;
  provider: string;
  model: string;
}

// 模型配置
export interface ModelConfig {
  configured: boolean;
  apiKey: string;
  hasApiKey: boolean;
  model: string;
  baseUrl: string;
  httpReferer: string;
  appTitle: string;
  serviceTier: string;
  timeoutSeconds: number;
  /** Custom endpoint compatibility. */
  authStyle: string;
  authHeader: string;
  extraHeaders: Record<string, string>;
  sendProviderExtras: boolean;
  authStyleOptions: string[];
  /** The URL that will actually be called, after path resolution. */
  resolvedEndpoint: string;
  source?: string;
}

// 模型配置更新
export interface ModelConfigUpdate {
  apiKey?: string;
  model?: string;
  baseUrl?: string;
  httpReferer?: string;
  appTitle?: string;
  serviceTier?: string;
  timeoutSeconds?: number;
  authStyle?: string;
  authHeader?: string;
  extraHeaders?: Record<string, string>;
  sendProviderExtras?: boolean;
}

// 智能体类型
export interface AgentRole {
  id: string;
  name: string;
  description: string;
  avatar: string;
  /** Business domain this role was derived from; empty for the generic role. */
  domain?: string;
  /** Data source the derived role is scoped to, when applicable. */
  dataSourceId?: number | null;
  /** 'derived' from an onboarded domain, 'custom' if persisted, else 'generic'. */
  source?: string;
}

export interface AgentChatPayload {
  message: string;
  /** Omit to let the platform choose a role from the onboarded domains. */
  roleId?: string;
  dataSourceId?: number;
  objectCode?: string;
  history?: Array<{ role: 'user' | 'assistant'; content: string }>;
  sessionId?: string;
}

export interface AgentChatResult {
  answer: string;
  intent: string;
  confidence: number;
  resolved: {
    dataSourceId?: number | null;
    objectCode?: string | null;
  };
  evidence: Record<string, unknown>;
  nextActions: string[];
  model?: {
    configured: boolean;
    usedForUnderstanding: boolean;
    usedForSummary: boolean;
    name: string;
    error?: string;
  };
  toolCalls: Array<{
    tool: string;
    args: Record<string, unknown>;
    result?: Record<string, unknown>;
    error?: string;
    authBlocked?: boolean;
  }>;
  roleId: string;
}

// 工作流相关类型
export interface WorkflowState {
  id: number;
  workflowId: number;
  code: string;
  name: string;
  description: string;
  isTerminal: number;
  color: string;
  sortOrder: number;
}

export interface WorkflowTransition {
  id: number;
  workflowId: number;
  fromState: string;
  toState: string;
  actionCode: string;
  name: string;
  guardExpression: string;
  requiresReview: number;
  reviewRole: string;
  sortOrder: number;
}

export interface WorkflowDefinition {
  id: number;
  ontologyId: number;
  objectCode: string;
  name: string;
  description: string;
  initialState: string;
  status: string;
  createdAt: string;
  states?: WorkflowState[];
  transitions?: WorkflowTransition[];
}

export interface WorkflowInstance {
  id: number;
  workflowId: number;
  objectCode: string;
  instanceId: string;
  currentState: string;
  stateEnteredAt: string;
  updatedAt: string;
  workflowName?: string;
  stateInfo?: WorkflowState;
}

export interface WorkflowHistoryItem {
  id: number;
  instanceWorkflowId: number;
  fromState: string;
  toState: string;
  actionCode: string;
  actor: string;
  reason: string;
  metadata: string;
  createdAt: string;
}

// 权限相关类型
export interface PermissionRole {
  id: number;
  code: string;
  name: string;
  description: string;
  isSystem: number;
  createdAt: string;
}

export interface PermissionPolicy {
  id: number;
  roleId: number;
  objectCode: string;
  canRead: number;
  canWrite: number;
  canExecute: number;
  canDelete: number;
  filterExpression: string;
  description: string;
  roleCode?: string;
  roleName?: string;
}

// 工具相关类型
export interface ToolDefinition {
  id: number;
  code: string;
  name: string;
  description: string;
  toolType: string;
  inputSchema: string;
  riskLevel: string;
  requiresReview: number;
  status: string;
  createdAt: string;
}

export interface ToolAuthorization {
  id: number;
  roleId: number;
  toolId: number;
  allowed: number;
  maxCallsPerHour: number;
}

export interface ToolExecutionLog {
  id: number;
  toolId: number | null;
  toolCode: string;
  agentRole: string;
  objectCode: string;
  instanceId: string;
  inputArgs: string;
  resultSummary: string;
  status: string;
  error: string;
  durationMs: number;
  requiresReview: number;
  reviewedBy: string | null;
  reviewedAt: string | null;
  reviewDecision: string | null;
  createdAt: string;
}

// -- 工作台 --

export interface WorkbenchActionItem {
  code: string;
  severity: 'blocker' | 'warning' | 'info';
  title: string;
  detail: string;
  count: number;
  route: string;
}

export interface WorkbenchDecisionEntry {
  decisionId: string;
  decisionType: string;
  objectCode: string;
  instanceId: string;
  status: string;
  actor: string;
  createdAt: string;
}

export interface Workbench {
  generatedAt: string;
  dataSources: {
    total: number;
    scanned: number;
    unscanned: number;
    withBusinessApi: number;
    tables: number;
    columns: number;
  };
  ontologies: {
    total: number;
    draft: number;
    published: number;
    byStatus: Record<string, number>;
    objects: number;
    attributes: number;
    relations: number;
    unboundObjects: number;
  };
  governance: {
    pendingMappings: number;
    confirmedMappings: number;
    rejectedMappings: number;
    mappingsByStatus: Record<string, number>;
    reviewableTransitions: number;
    auditEntries: number;
  };
  rules: {
    total: number;
    blocking: number;
    warning: number;
    info: number;
    bySeverity: Record<string, number>;
    byStatus: Record<string, number>;
    objectsWithoutRules: number;
  };
  decisions: {
    total: number;
    byStatus: Record<string, number>;
    blocked: number;
    review: number;
    approved: number;
    recent: WorkbenchDecisionEntry[];
  };
  knowledge: {
    valueMappings: number;
    confirmedValueMappings: number;
    pendingValueMappings: number;
  };
  actionItems: WorkbenchActionItem[];
  summary: {
    blockers: number;
    warnings: number;
    totalActionItems: number;
  };
}

// -- 知识图谱预览 --

export interface OntologyGraphNode {
  id: string;
  code: string;
  name: string;
  description: string;
  sourceTable: string;
  attributeCount: number;
  ruleCount: number;
  degree: number;
  unbound: boolean;
  unmapped: boolean;
}

export interface OntologyGraphEdge {
  id: number;
  code: string;
  name: string;
  source: string;
  target: string;
  relationType: string;
  foreignKey: string;
}

export interface OntologyGraph {
  ontology: {
    id: number;
    name: string;
    domain: string;
    version: string;
    status: string;
  };
  nodes: OntologyGraphNode[];
  edges: OntologyGraphEdge[];
  stats: {
    nodeCount: number;
    edgeCount: number;
    isolatedObjects: string[];
    objectsWithoutRules: string[];
    unmappedObjects: string[];
  };
  notes: {
    relationTypes: string[];
    limitation: string;
  };
}

// -- 文档知识层 --

export interface KnowledgeDocument {
  id: number;
  title: string;
  sourceName: string;
  chunkCount: number;
  confirmedCount: number;
  pendingCount: number;
  status: string;
  uploadedBy: string;
  createdAt: string;
}

export interface KnowledgeEntry {
  id: number;
  documentId: number;
  ordinal: number;
  citation: string;
  heading: string;
  content: string;
  /** Anchor: which business object this passage explains. */
  objectCode: string;
  /** Anchor: which rule this passage is the textual authority for. */
  ruleCode: string;
  status: string;
  reviewer: string;
}

export interface KnowledgeEntryList {
  items: KnowledgeEntry[];
  retrievalBackends: string[];
  embeddingModels: string[];
}

export interface KnowledgeIngestResult {
  documentId: number;
  title: string;
  chunkCount: number;
  status: string;
  warnings: string[];
  citations: string[];
  note: string;
}
