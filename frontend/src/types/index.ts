// 数据源相关类型
/** What a scan reports: one entry per table, not three totals. */
/**
 * What `POST /data-sources/{id}/initialize` reports back.
 *
 * `scan` was in the payload and not in this type, so the screen that could have said
 * 「已初始化：4 张表」 said 「已初始化」 instead -- a declared shape that omits a field is a
 * field nobody reads.
 */
export interface DataSourceInitializeResult {
  status: string;
  scan?: { tables: number };
  reasoningChain: ReasoningChain;
}

export interface SourceScanResult {
  dataSourceId: number;
  tables: { table: string; columns: number; foreignKeys: number }[];
  /**
   * What the scan found that the draft derived from this source does not model.
   *
   * The scan keeps that draft (a re-scan used to discard it, which destroyed rules and
   * workflows), so a source that gained a table now keeps a model that has never seen it.
   * Reported here because 「扫描完成」 is otherwise indistinguishable from 「扫描完成，而且模型仍然对得上」.
   */
  modelledOntologyId?: number | null;
  modelledTables?: string[];
  unmodelledTables?: string[];
}

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

/**
 * A declared kind of thing that happens to instances of one object.
 *
 * Declared rather than free-form: an event stream of arbitrary strings can be stored but
 * not reasoned about, and «驳回» / «拒绝» / «rejected» would become three unrelated facts.
 * Recording an event with an undeclared code is refused, which is why this screen has to
 * exist before the instance timeline can be populated from the UI at all.
 */
export interface EventTypeDeclaration {
  code: string;
  name: string;
  objectCode: string;
  category: string;
  categoryLabel: string;
  /** Field names the payload is expected to carry. Advisory, and reported on when absent. */
  payloadFields: string[];
  description: string;
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
  /**
   * What regenerating this draft removed. Present only when it rebuilt an existing draft:
   * a draft is rebuilt from the current scan, so hand-written rules, mappings, relations,
   * workflows and knowledge documents attached to it go with it. The screen has to say so,
   * because the alternative is a success message and a silent loss.
   */
  discarded?: Record<string, number>;
  discardedSummary?: string;
}

/**
 * What `POST /ontologies/{id}/publish` answers with.
 *
 * The summary of the version that is now published -- `_ontology_publication_summary` in the
 * backend. Declared because the screen reads `name` and `version` from it, and an undeclared
 * shape is a shape nobody can rely on.
 */
export interface OntologyPublication {
  id: number;
  name: string;
  domain: string;
  version: string;
  status: string;
  publishedAt?: string | null;
  mappingCounts?: Record<string, number>;
}

export interface ReleaseReadinessGate {
  /**
   * The facts this gate is about, sent beside its Chinese wording so the console can say the
   * sentence in the reader's language: `{objects: 4}` for "4 business objects identified",
   * `status` for the vocabularies it quotes. See `ontology.gate.*` in the dictionary.
   */
  status?: string;
  numbers?: Record<string, number>;
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

/**
 * One declared attribute of an instance, with the value a rule would see.
 *
 * `value` is not the raw stored cell: units wrap it, a value mapping lets it compare equal
 * to its business state name, and for an as-of explanation recorded history replaces it.
 * `derived` attributes have no `sourceColumn` at all -- they are computed from an
 * expression, and the expression is the explanation.
 */
export interface InstanceExplainAttribute {
  attributeCode: string;
  attributeName: string;
  /** Empty for a derived attribute: there is no column behind a computed value. */
  sourceColumn: string;
  unit: string;
  unitName: string;
  derived: boolean;
  derivedExpression: string;
  value: unknown;
  /** Why a derived attribute could not be computed. Empty when it could. */
  error?: string;
  /** The business state a mapped legacy code corresponds to, when a mapping applies. */
  stateName?: string;
  /** True when recorded history supplied this value rather than the live row. */
  fromHistory?: boolean;
}

/**
 * One event in an instance's history, as `/explain` embeds it.
 *
 * `eventName` and `categoryLabel` are resolved server-side: an event whose type was never
 * declared still appears, named by its code, rather than being dropped.
 */
export interface InstanceTimelineEntry {
  eventCode: string;
  eventName: string;
  category: string;
  categoryLabel: string;
  actor: string;
  occurredAt: string;
}

/**
 * One cross-object aggregate, as the explanation carries it.
 *
 * `truncated` means the aggregate hit its row cap, so the value is a partial answer and any
 * rule that compared it reached a verdict on partial data. That is worth surfacing rather
 * than leaving in a field nobody reads.
 */
export interface InstanceExplainAggregate {
  name: string;
  definition: string;
  value: unknown;
  rowCount: number;
  truncated: boolean;
  /** Why the aggregate could not be computed. Empty when it could. */
  error: string;
}

/**
 * `GET /semantic/objects/{code}/instances/{id}/explain`.
 *
 * Every field here was read off a live response. It previously declared
 * `attributes: Record<string, unknown>` and a `relations` array that the endpoint does not
 * send -- and a type that describes a blob produces a renderer that treats it as one: the
 * instance page printed the whole thing through `JSON.stringify`, discarding the attribute
 * names, the source column of each value, and the source binding the explanation exists to
 * establish. A vague type is not a neutral placeholder.
 */
export interface InstanceExplainResult {
  ontology: { id: number; name: string; version: string };
  object: { code: string; name: string };
  objectCode: string;
  instanceId: string;
  source: { table: string; primaryKey: string; instanceId: string };
  /** The instant this explanation is about. Empty for the present. */
  asOf: string;
  attributes: InstanceExplainAttribute[];
  /**
   * Cross-object aggregates a rule can read by name.
   *
   * Separate from `attributes` because an aggregate is a query over other rows, not a value
   * of this one: it has a row count and a truncation flag, and no declared attribute to hang
   * them on. It has nowhere else to appear at all -- unlike a derived attribute, there is no
   * row in the model's attribute list for it, so a verdict citing one used to cite a name
   * the explanation never mentioned.
   */
  aggregates: InstanceExplainAggregate[];
  /** Declared ancestors, nearest first, so an explanation can say which type's rules apply. */
  ancestors: string[];
  timeline: InstanceTimelineEntry[];
  explanation: string;
}

/** `GET /ontologies/{o}/objects/{c}/instances/{i}/events` -- the full history, not the excerpt. */
export interface InstanceEvent {
  id: number;
  eventCode: string;
  eventName: string;
  category: string;
  categoryLabel: string;
  actor: string;
  payload: Record<string, unknown>;
  /** Set when the payload does not match the declared fields; empty when it does. */
  payloadWarning: string;
  occurredAt: string;
  recordedAt: string;
  correlationId: string;
}

export interface InstanceEventsResult {
  items: InstanceEvent[];
  total: number;
  truncated: boolean;
}

/**
 * One recorded attribute value over a period. `validTo: null` means it is still current --
 * the endpoint has already closed the previous version, so this is a fact rather than an
 * inference the reader has to make.
 */
export interface InstanceAttributeVersion {
  versionId: number;
  attributeCode: string;
  value: unknown;
  valueType: string;
  validFrom: string;
  validTo: string | null;
  recordedAt: string;
  actor: string;
  source: string;
  openEnded: boolean;
}

export interface InstanceVersionsResult {
  objectCode: string;
  instanceId: string;
  versions: InstanceAttributeVersion[];
  coverage: Record<string, { earliest: string; latestFrom: string; openEnded: boolean; versionCount: number }>;
  truncated: boolean;
}

export interface SemanticObjectAttribute {
  code: string;
  name: string;
  dataType: string;
  required: boolean;
  sourceColumn: string;
}

export interface SemanticObjectInstanceItem {
  instanceId: string;
  record: Record<string, unknown>;
  tables: string[];
}

export interface SemanticObjectInstancesResult {
  ontology: {
    id: number;
    name: string;
    domain?: string;
    version: string;
    status: string;
  };
  object: {
    id?: number;
    code: string;
    name: string;
    description?: string;
    sourceTable: string;
    sourceType?: string;
    dataSourceId?: number;
    resolver?: Record<string, unknown>;
  };
  attributes: SemanticObjectAttribute[];
  items: SemanticObjectInstanceItem[];
  // Whether the policy carried a row filter. Distinguishes "every row was judged against
  // it" from "this was a capability check only" without re-reading the policy table.
  rowFilterApplied?: boolean;
  // Set only when an empty page is the answer to "the filter could not be evaluated",
  // which is a misconfiguration rather than an absence of data.
  rowFilterError?: string;
  pagination: { limit: number; offset: number; total: number; hasMore: boolean };
}

export interface SemanticObjectInstanceResult {
  ontology: SemanticObjectInstancesResult['ontology'];
  object: SemanticObjectInstancesResult['object'];
  instanceId: string;
  record: Record<string, unknown>;
  tables: string[];
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
  /** The sentence the verdict carried. What a reader wants under 建议. */
  recommendation: string;
  /** The machine's instruction: `allow_automation` and friends. Kept for integrators. */
  nextAction: string;
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
//
// 这两张表的字段名是 snake_case，因为 `/governance/audit-log` 与
// `/governance/model-invocations` 直接返回 `dict(row)`——列名即字段名。
// 它们此前被声明成 camelCase，而 TypeScript 对此照单全收：
// `record.createdAt` 通过类型检查、能被自动补全、运行时是 `undefined`。
// 错误的类型声明不是中立的，它会给真实存在的 bug 盖章放行——
// 这两处正是如此，rowKey 因此对每一行都算出 `undefined-<action>`。
export interface AuditLogItem {
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  created_at: string;
}

export interface ModelInvocationItem {
  provider: string;
  model: string;
  purpose: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  status: string;
  error?: string;
  created_at: string;
}

// 演示相关类型
export interface DemoBootstrapResult {
  dataSource: DataSource;
  scan: ScanResult;
  /**
   * The draft summary the scenario produced: the ontology's own row (`id`, `name`, …) with the
   * objects, attributes, relations, mappings and rules it created alongside it.
   *
   * `discardedSummary` is present only when the run rebuilt a draft that already existed --
   * which is what pressing the button a second time does. A rebuild clears the rules,
   * mappings and workflows attached to the old draft, so the screen has to say so.
   */
  ontology: Ontology & { discarded?: Record<string, number>; discardedSummary?: string };
  /**
   * The verdict the scenario produced, so the success panel can say what happened rather
   * than only what was created. It is the point of the demo: the sample system is modelled
   * and then assessed once, which is what makes the workbench show a decision instead of
   * zero.
   */
  decision: string;
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
  provider: string;
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
  provider?: string;
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
  /** Set when the exchange was persisted; needed to attach feedback. */
  sessionId?: string;
  conversationId?: number;
  messageId?: number;
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

// -- 会话与反馈 --

export interface AnswerFeedback {
  id: number;
  messageId: number;
  conversationId: number;
  rating: 'helpful' | 'unhelpful' | 'incorrect';
  comment: string;
  correction: string;
  decisionId: string;
  objectCode: string;
  ruleCode: string;
  status: string;
  actor: string;
  resolvedBy: string;
  resolvedAt: string;
  createdAt: string;
}

export interface ConversationMessage {
  id: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  intent: string;
  confidence: number | null;
  /** Links the answer to the verdict it produced, so feedback is attributable. */
  decisionId: string;
  citations: Array<{ citation: string; documentTitle: string; ruleCode: string }>;
  actor: string;
  createdAt: string;
  feedback: AnswerFeedback[];
}

export interface Conversation {
  id: number;
  sessionId: string;
  title: string;
  roleId: string;
  dataSourceId: number | null;
  ontologyId: number | null;
  objectCode: string;
  status: 'active' | 'escalated' | 'resolved' | 'closed';
  actor: string;
  escalatedTo: string;
  escalationReason: string;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
  messages?: ConversationMessage[];
}

export interface FeedbackSummary {
  total: number;
  byRating: Record<string, number>;
  helpful: number;
  unhelpful: number;
  incorrect: number;
  openItems: number;
  corrections: number;
  escalatedConversations: number;
  conversations: number;
}

/** One provisioned tenant, as `GET /tenants` reports it. */
export interface TenantSummary {
  tenant: string;
  schema: string;
}

/** `GET /tenants`. Multi-tenancy is opt-in, so `items` is empty on a single-tenant deployment. */
export interface TenantList {
  items: TenantSummary[];
  isolationModel: string;
  dbType: string;
}

/** `GET /tenants/{tenant}/statistics` -- row counts, for verifying isolation after provisioning. */
export interface TenantStatistics {
  tenant: string;
  schema: string;
  tables: Record<string, number>;
  totalRows: number;
}

/** One limitable resource: what it counts, and where. */
export interface QuotaResource {
  resource: string;
  table: string;
  description: string;
}

export interface QuotaState {
  table: string;
  description: string;
  current: number;
  /** `null` means unlimited, which is why it is not a large number. */
  limit: number | null;
  remaining: number | null;
  exceeded: boolean;
}

/** `GET /tenants/{tenant}/quotas` -- declared limits and usage, which only mean something together. */
export interface TenantQuotas {
  tenant: string;
  resources: Record<string, QuotaState>;
  note: string;
}

/** One provider group → platform role mapping, from `GET /auth/sso/mappings`. */
export interface SsoGroupMapping {
  providerGroup: string;
  roleCode: string;
  note: string;
}

/**
 * `GET /auth/sso` — the effective SSO state, never the secret.
 *
 * `mappedGroups` is part of it because SSO that verifies correctly and maps nothing rejects
 * every login, which is otherwise indistinguishable from a signature problem.
 */
export interface SsoStatus {
  enabled: boolean;
  issuer: string;
  audience: string;
  algorithm: string;
  groupClaim: string;
  usernameClaim: string;
  mappedGroups: number;
  mappings: SsoGroupMapping[];
  note: string;
}

/** One thing an auditor should look at, stated by the report rather than left to be noticed. */
export interface AuditFinding {
  severity: string;
  /**
   * Which finding this is, so the console can say it in the reader's language.
   *
   * The sentence is composed here rather than quoted: `finding` and `action` arrive in
   * Chinese, and a bilingual console cannot translate a finished sentence -- it needs the
   * code and the number. `count` and `ratio` are what the sentence is about; `ratio` is a
   * fraction (0.42), not a percentage.
   */
  code?: string;
  count?: number;
  ratio?: number;
  finding: string;
  action: string;
}

/** What a report section answers, so the caller knows what it asked for. */
export interface AuditReportSection {
  section: string;
  name: string;
  answers: string;
}

/** A published rule and how many times it was evaluated in the period. */
export interface AuditRuleEntry {
  code: string;
  name: string;
  severity: string;
  ontologyId: number | null;
  evaluations: number;
}

/** One audit_log row, as `dict(row)` sends it. */
export interface AuditEvent {
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  created_at: string;
}

/** One blocked decision, listed in full rather than counted. */
export interface AuditBlockedDecision {
  decision_id: string;
  decision_type: string;
  object_code: string;
  instance_id: string;
  status: string;
  actor: string;
  created_at: string;
}

/**
 * `GET /governance/audit-report` -- a period, not "everything".
 *
 * `period.boundary` is part of the payload because the interval is half-open: a finding
 * attached to the wrong period is a wrong finding.
 *
 * Every shape here was read off a live response, not inferred from the section names.
 * Two of them were wrong when guessed -- `byActor` is actor → action → count, and
 * `coverage` counts *rule evaluations* rather than decisions. A guessed type annotates
 * the mistake as correct and the compiler endorses it.
 */
export interface AuditReport {
  period: { start: string; end: string; boundary: string };
  ontologyId: number | null;
  decisions: { total: number; byStatus: Record<string, number>; blocked: AuditBlockedDecision[] };
  rules: { triggered: AuditRuleEntry[]; neverTriggered: AuditRuleEntry[]; note: string };
  /** Actor → action → count. Not actor → count. */
  actors: { byActor: Record<string, Record<string, number>> };
  governance: { events: AuditEvent[]; forcedPublications: AuditEvent[] };
  model: { total: number; byPurpose: Record<string, number>; failed: number };
  /** One assess call writes one decision and N evaluations; this counts the evaluations. */
  coverage: { evaluations: number; withTrace: number; ratio: number | null };
  findings: AuditFinding[];
}
