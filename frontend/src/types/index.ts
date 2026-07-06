// 数据源相关类型
export interface DataSource {
  id: number;
  name: string;
  sourceType: string;
  connectionUri: string;
  domain: string;
  systemCategory: string;
  capabilities: string[];
  createdAt?: string;
}

export interface DataSourceCreate {
  name: string;
  sourceType?: string;
  connectionUri: string;
  domain?: string;
  systemCategory?: string;
  capabilities?: string[];
}

export interface OnboardingRunCreate extends DataSourceCreate {
  blueprintId?: string;
  ontologyName?: string;
  generateOntology?: boolean;
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
  ontologyId: number;
  code: string;
  name: string;
  description: string;
  expression: string;
  severity: string;
  enabled: boolean;
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
}
