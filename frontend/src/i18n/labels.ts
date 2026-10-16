/**
 * Backend values, as a user reads them -- in both languages.
 *
 * Every map here exists because the UI printed the API's enum verbatim: a console showed
 * `draft`, `blocking`, `pending` and `rejected` in its governance tables, so reading your own
 * dashboard required knowing the backend's vocabulary. The wording already existed --
 * scattered. One page said 「已发布」, another derived its own inline condition, a third
 * rendered the raw value, and `i18n/translations.ts` (since deleted) held a fourth copy that
 * nothing imported.
 *
 * `label()` falls through to the raw value rather than rendering blank or a placeholder: an
 * enum this file has not learned yet should read like today's behaviour, not like a hole in
 * the table. That also means a value added on the backend degrades to the raw spelling rather
 * than to nothing.
 *
 * The maps became `{ zh, en }` when the console learned English. Until then every status chip
 * in the application stayed Chinese in English mode -- the one place a reader looks to see
 * what state something is in.
 */

import type { Locale } from './messages';

export interface LabelEntry {
  zh: string;
  en: string;
}

export type LabelMap = Record<string, LabelEntry>;

/** The values `governance.VALID_ONTOLOGY_STATUSES` accepts. */
export const ONTOLOGY_STATUS: LabelMap = {
  draft: { zh: '草案', en: 'Draft' },
  reviewing: { zh: '审核中', en: 'In review' },
  published: { zh: '已发布', en: 'Published' },
  deprecated: { zh: '已废弃', en: 'Deprecated' },
};

/** The values `governance.VALID_RULE_STATUSES` accepts. */
export const RULE_STATUS: LabelMap = {
  draft: { zh: '草案', en: 'Draft' },
  published: { zh: '已发布', en: 'Published' },
  disabled: { zh: '已停用', en: 'Disabled' },
};

/** The values `governance.VALID_MAPPING_STATUSES` accepts. */
export const MAPPING_STATUS: LabelMap = {
  pending: { zh: '待审核', en: 'Pending review' },
  confirmed: { zh: '已确认', en: 'Confirmed' },
  rejected: { zh: '已驳回', en: 'Rejected' },
};

/** The values `governance.VALID_RULE_SEVERITIES` accepts, ordered by how hard they stop. */
export const RULE_SEVERITY: LabelMap = {
  info: { zh: '提示', en: 'Info' },
  warning: { zh: '警告', en: 'Warning' },
  blocking: { zh: '阻断', en: 'Blocking' },
};

/** The values `governance.VALID_RULE_TYPES` accepts. */
export const RULE_TYPE: LabelMap = {
  validation: { zh: '校验', en: 'Validation' },
  derivation: { zh: '派生', en: 'Derivation' },
  transition: { zh: '流转', en: 'Transition' },
  risk: { zh: '风险', en: 'Risk' },
  recommendation: { zh: '建议', en: 'Recommendation' },
  permission: { zh: '权限', en: 'Permission' },
};

/** `semantic_kernel` verdicts, and the consistency report's own verdicts. */
export const DECISION_STATUS: LabelMap = {
  approved: { zh: '通过', en: 'Approved' },
  review: { zh: '待复核', en: 'Needs review' },
  blocked: { zh: '阻断', en: 'Blocked' },
};

/**
 * How divided a batch of verdicts is, from `semantic_kernel.CONSISTENCY_STATUSES`.
 *
 * A different vocabulary from `DECISION_STATUS`, which is why it is a different map: one
 * describes a single verdict, the other describes a sample. They were merged, and the
 * merged map was wrong in both directions -- it carried `inconsistent`, which no code
 * produces, and lacked `mixed_with_blockers`, so a divided sample printed the raw English
 * enum inside a Chinese console.
 */
export const CONSISTENCY_STATUS: LabelMap = {
  consistent: { zh: '一致', en: 'Consistent' },
  mixed: { zh: '存在分化', en: 'Mixed' },
  mixed_with_blockers: { zh: '分化且含阻断', en: 'Mixed, with blockers' },
  incomplete: { zh: '不完整', en: 'Incomplete' },
  empty: { zh: '无可评估实例', en: 'No instances to assess' },
};

/** What a preflight tells the caller to do, from `automation.NEXT_ACTIONS`. */
export const NEXT_ACTION: LabelMap = {
  allow_automation: { zh: '允许自动执行', en: 'Allow automation' },
  block_and_require_correction: { zh: '阻断并要求修正', en: 'Block and require a correction' },
  route_to_human_review: { zh: '转人工复核', en: 'Route to human review' },
};

/** What a data source connection test concluded, from `adapters.CONNECTION_STATUSES`. */
export const CONNECTION_STATUS: LabelMap = {
  ok: { zh: '连接成功', en: 'Connected' },
  not_found: { zh: '文件或库不存在', en: 'File or database not found' },
  driver_missing: { zh: '缺少驱动', en: 'Driver not installed' },
  connection_error: { zh: '连接失败', en: 'Connection failed' },
};

/** How one onboarding step ended, from `onboarding.ONBOARDING_STEP_STATUSES`. */
export const ONBOARDING_STEP_STATUS: LabelMap = {
  completed: { zh: '已完成', en: 'Completed' },
  failed: { zh: '失败', en: 'Failed' },
  skipped: { zh: '已跳过', en: 'Skipped' },
};

/** A conversation's state, from `conversations.CONVERSATION_STATUSES`. */
export const CONVERSATION_STATUS: LabelMap = {
  active: { zh: '进行中', en: 'Active' },
  escalated: { zh: '已转人工', en: 'Escalated' },
  resolved: { zh: '已解决', en: 'Resolved' },
  closed: { zh: '已关闭', en: 'Closed' },
};

/** A feedback item's state, from `conversations.FEEDBACK_STATUSES`. */
export const FEEDBACK_STATUS: LabelMap = {
  open: { zh: '待处理', en: 'Open' },
  resolved: { zh: '已处理', en: 'Resolved' },
  dismissed: { zh: '已忽略', en: 'Dismissed' },
};

/** What an execute call did, from `automation.EXECUTION_STATUSES`. */
export const EXECUTION_STATUS: LabelMap = {
  executed: { zh: '已执行', en: 'Executed' },
  ready_for_execution: { zh: '已生成执行计划（未执行）', en: 'Plan prepared, not executed' },
  blocked_by_semantic_kernel: { zh: '被语义内核阻断', en: 'Blocked by the semantic kernel' },
};

/**
 * How a call to the outside world ended: a model invocation, or an agent's tool execution.
 *
 * One map for both because both write the same two words (`agent.py` sets `success`/`error`
 * on the tool ledger, `record_model_invocation` the same on the invocation ledger), and they
 * sit two tabs apart on the governance screen. Two maps would be two chances for the two tabs
 * to name the same outcome differently.
 */
export const CALL_STATUS: LabelMap = {
  success: { zh: '成功', en: 'Succeeded' },
  error: { zh: '失败', en: 'Failed' },
};

/**
 * What kind of decision a `decision_record` is, from `decisions.record_decision`'s callers.
 *
 * Not the verdict: the verdict is `DECISION_STATUS`, and this column sits next to it. The
 * three values are the three things the platform records a decision about.
 */
export const DECISION_TYPE: LabelMap = {
  instance_assessment: { zh: '实例判定', en: 'Instance assessment' },
  operation_preflight: { zh: '操作预检', en: 'Operation preflight' },
  operation_execution: { zh: '操作执行', en: 'Operation execution' },
};

/**
 * Readiness, coverage and operation-binding checks share this vocabulary, which is why they
 * share the maps: the three answer "is this source usable yet" in the same terms, and giving
 * each its own wording would invent a distinction the backend does not make.
 */
export const READINESS_STATUS: LabelMap = {
  ready: { zh: '就绪', en: 'Ready' },
  review: { zh: '需复核', en: 'Needs review' },
  blocked: { zh: '受阻', en: 'Blocked' },
  partial: { zh: '部分就绪', en: 'Partly ready' },
  incomplete: { zh: '不完整', en: 'Incomplete' },
  bound: { zh: '已绑定', en: 'Bound' },
  not_modeled: { zh: '尚未建模', en: 'Not modelled yet' },
  not_configured: { zh: '未配置', en: 'Not configured' },
  error: { zh: '检查失败', en: 'Check failed' },
};

/** The categories `events.EVENT_CATEGORIES` accepts, in the same words it uses. */
export const EVENT_CATEGORY: LabelMap = {
  lifecycle: { zh: '生命周期', en: 'Lifecycle' },
  state_change: { zh: '状态变更', en: 'State change' },
  attribute_change: { zh: '属性变更', en: 'Attribute change' },
  interaction: { zh: '业务交互', en: 'Business interaction' },
  external: { zh: '外部事件', en: 'External event' },
};

/**
 * Release-gate severity, which is a different scale from rule severity: a gate is
 * `blocker` or `warning`, a rule is `blocking` or `warning`. They share one word and not the
 * other, so putting gates in `RULE_SEVERITY` would translate half of them and print the rest
 * raw -- the kind of gap that reads as a styling inconsistency rather than a missing entry.
 */
export const GATE_SEVERITY: LabelMap = {
  blocker: { zh: '阻断', en: 'Blocker' },
  warning: { zh: '警告', en: 'Warning' },
};

/** Structural drift between the modelled object and the live source. */
export const DRIFT_STATUS: LabelMap = {
  no_drift: { zh: '无漂移', en: 'No drift' },
  drift_detected: { zh: '检测到漂移', en: 'Drift detected' },
  error: { zh: '检查失败', en: 'Check failed' },
  skipped: { zh: '已跳过', en: 'Skipped' },
};

/** The relation kinds `relations.RELATION_KINDS` infers, in the same words it uses. */
export const RELATION_KIND: LabelMap = {
  composition: { zh: '组成', en: 'Composition' },
  aggregation: { zh: '聚合', en: 'Aggregation' },
  association: { zh: '关联', en: 'Association' },
};

/**
 * What a `semantic_mapping` row connects, which is the first column of the mapping list.
 *
 * `table_to_object` and `column_to_attribute` are the structural mappings a scan produces;
 * `value_to_state` comes from the value-domain mappings; the rest are extension points. The
 * screen printed these raw, so the first column of the review queue -- the one that says what
 * kind of claim you are confirming -- read `column_to_attribute` in both languages.
 *
 * An unknown value falls through to itself rather than to a placeholder: extensions define
 * their own, and showing the raw name is how the person who wrote one recognises it.
 */
export const MAPPING_TYPE: LabelMap = {
  table_to_object: { zh: '表 → 业务对象', en: 'Table → business object' },
  column_to_attribute: { zh: '列 → 业务属性', en: 'Column → attribute' },
  value_to_state: { zh: '取值 → 语义状态', en: 'Value → semantic state' },
  aggregation: { zh: '聚合定义', en: 'Aggregate definition' },
};

/**
 * The word for a value, or the value itself when this file has not learned it.
 *
 * A function rather than direct indexing at each call site so the fallback is decided once:
 * `MAP[value]` silently yields `undefined`, which React renders as nothing at all. The locale
 * is a parameter rather than a module-level setting: this file is imported by screens, and a
 * hidden global is how two languages end up on one page.
 */
export const labelIn = (map: LabelMap, value: unknown, locale: Locale): string => {
  const key = String(value ?? '');
  const entry = map[key];
  if (!entry) return key;
  return entry[locale] ?? entry.zh;
};
