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
