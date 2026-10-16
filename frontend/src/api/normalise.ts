/**
 * The wire, mapped onto the shape the screens use.
 *
 * This file exists because the boundary kept being the place the bugs were. Four times a
 * screen read a field the endpoint did not send -- `dict(row)` payloads of `snake_case`
 * against TypeScript types declaring `camelCase` -- and four times the symptom was an antd
 * column that drew nothing for every row, on the review queues and permission tables that
 * answer "what has been reviewed" and "who may do what". None of it failed anything: the
 * types checked out, the linter saw valid strings, and the tables were empty.
 *
 * It was a block inside `api/index.ts`, which is also where the axios instance lives -- so the
 * defect and its cause were in one file with the second half unreachable from a test. Pulled
 * out, the mapping is a pure function from a payload to an object, and `normalise.test.ts`
 * holds it to the field names it consumes for real.
 *
 * **These normalisers deliberately do not fall back to a default for the fields a screen
 * reads.** `?? ''` on a field the endpoint stopped sending produces an empty column, not an
 * error, which is exactly the defect class this file was extracted to make testable. The
 * defaults below are for fields the API legitimately omits, and the test names which.
 */

import type {
  DataSource,
  SourceApi,
  SourceTable,
  PermissionPolicy,
  PermissionRole,
  ToolDefinition,
  ToolExecutionLog,
  WorkflowDefinition,
  WorkflowInstance,
  WorkflowState,
  WorkflowTransition,
} from '../types';


export const normalizeDataSource = (item: any): DataSource => ({
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

export const normalizeSourceApi = (item: any): SourceApi => ({
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
export const normalizeWorkflowState = (item: any): WorkflowState => ({
  ...item,
  workflowId: item.workflowId ?? item.workflow_id,
  isTerminal: item.isTerminal ?? item.is_terminal ?? 0,
  sortOrder: item.sortOrder ?? item.sort_order ?? 0,
});

export const normalizeWorkflowTransition = (item: any): WorkflowTransition => ({
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

export const normalizeWorkflow = (item: any): WorkflowDefinition => ({
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

export const normalizeWorkflowInstance = (item: any): WorkflowInstance => ({
  ...item,
  workflowId: item.workflowId ?? item.workflow_id,
  objectCode: item.objectCode ?? item.object_code ?? '',
  instanceId: item.instanceId ?? item.instance_id ?? '',
  currentState: item.currentState ?? item.current_state ?? '',
});

export const normalizeToolExecution = (item: any): ToolExecutionLog => ({
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

export const normalizePolicy = (item: any): PermissionPolicy => ({
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

export const normalizeRole = (item: any): PermissionRole => ({
  ...item,
  isSystem: item.isSystem ?? item.is_system ?? 0,
  createdAt: item.createdAt ?? item.created_at ?? '',
});

export const normalizeTool = (item: any): ToolDefinition => ({
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

export const normalizeSourceTable = (item: any): SourceTable => ({
  id: item.id,
  tableName: item.tableName ?? item.table_name,
  rowCount: item.rowCount ?? item.row_count,
  primaryKey: item.primaryKey ?? item.primary_key,
  scannedAt: item.scannedAt ?? item.scanned_at,
});

/**
 * The filename the server asked for, from a `Content-Disposition` header.
 *
 * Read from the response rather than passed in by the caller, because the server is the one
 * that knows what it produced -- an ontology export's name carries the ontology and its
 * version, and a caller that reconstructed it would be guessing at a format it does not own.
 * `filename*=UTF-8''...` is the encoded form, which a name containing Chinese arrives as.
 */
export function filenameFromDisposition(header: unknown): string | null {
  if (typeof header !== 'string') return null;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      return encoded[1].trim();
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}
