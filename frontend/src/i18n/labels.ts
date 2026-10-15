/**
 * Backend values, as a user reads them.
 *
 * Every map here exists because the UI printed the API's enum verbatim: a Chinese-language
 * console showed `draft`, `blocking`, `pending` and `rejected` in its governance tables, so
 * reading your own dashboard required knowing the backend's vocabulary. The wording already
 * existed — scattered. One page said 「已发布」, another derived its own inline condition,
 * a third rendered the raw value, and `i18n/translations.ts` (since deleted) held a fourth
 * copy that nothing imported.
 *
 * `label()` falls through to the raw value rather than rendering blank or a placeholder: an
 * enum this file has not learned yet should read like today's behaviour, not like a hole in
 * the table. That also means adding a value on the backend degrades to English rather than
 * to nothing.
 */

/** The values `governance.VALID_ONTOLOGY_STATUSES` accepts. */
export const ONTOLOGY_STATUS: Record<string, string> = {
  draft: '草案',
  reviewing: '审核中',
  published: '已发布',
  deprecated: '已废弃',
};

/** The values `governance.VALID_RULE_STATUSES` accepts. */
export const RULE_STATUS: Record<string, string> = {
  draft: '草案',
  published: '已发布',
  disabled: '已停用',
};

/** The values `governance.VALID_MAPPING_STATUSES` accepts. */
export const MAPPING_STATUS: Record<string, string> = {
  pending: '待审核',
  confirmed: '已确认',
  rejected: '已驳回',
};

/** The values `governance.VALID_RULE_SEVERITIES` accepts, ordered by how hard they stop. */
export const RULE_SEVERITY: Record<string, string> = {
  info: '提示',
  warning: '警告',
  blocking: '阻断',
};

/** The values `governance.VALID_RULE_TYPES` accepts. */
export const RULE_TYPE: Record<string, string> = {
  validation: '校验',
  derivation: '派生',
  transition: '流转',
  risk: '风险',
  recommendation: '建议',
  permission: '权限',
};

/** `semantic_kernel` verdicts, and the consistency report's own verdicts. */
export const DECISION_STATUS: Record<string, string> = {
  approved: '通过',
  review: '待复核',
  blocked: '阻断',
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
/** What a preflight tells the caller to do, from `automation.NEXT_ACTIONS`. */
export const NEXT_ACTION: Record<string, string> = {
  allow_automation: '允许自动执行',
  block_and_require_correction: '阻断并要求修正',
  route_to_human_review: '转人工复核',
};

/** What a data source connection test concluded, from `adapters.CONNECTION_STATUSES`. */
export const CONNECTION_STATUS: Record<string, string> = {
  ok: '连接成功',
  not_found: '文件或库不存在',
  driver_missing: '缺少驱动',
  connection_error: '连接失败',
};

/** How one onboarding step ended, from `onboarding.ONBOARDING_STEP_STATUSES`. */
export const ONBOARDING_STEP_STATUS: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  skipped: '已跳过',
};

/** A conversation's state, from `conversations.CONVERSATION_STATUSES`. */
export const CONVERSATION_STATUS: Record<string, string> = {
  active: '进行中',
  escalated: '已转人工',
  resolved: '已解决',
  closed: '已关闭',
};

/** A feedback item's state, from `conversations.FEEDBACK_STATUSES`. */
export const FEEDBACK_STATUS: Record<string, string> = {
  open: '待处理',
  resolved: '已处理',
  dismissed: '已忽略',
};

/** What an execute call did, from `automation.EXECUTION_STATUSES`. */
export const EXECUTION_STATUS: Record<string, string> = {
  executed: '已执行',
  ready_for_execution: '已生成执行计划（未执行）',
  blocked_by_semantic_kernel: '被语义内核阻断',
};

export const CONSISTENCY_STATUS: Record<string, string> = {
  consistent: '一致',
  mixed: '存在分化',
  mixed_with_blockers: '分化且含阻断',
  incomplete: '不完整',
  empty: '无可评估实例',
};

/**
 * Readiness, coverage and operation-binding checks share this vocabulary, which is why they
 * share the maps: the three answer "is this source usable yet" in the same terms, and giving
 * each its own wording would invent a distinction the backend does not make.
 */
export const READINESS_STATUS: Record<string, string> = {
  ready: '就绪',
  review: '需复核',
  blocked: '受阻',
  partial: '部分就绪',
  incomplete: '不完整',
  bound: '已绑定',
  not_modeled: '尚未建模',
  not_configured: '未配置',
  error: '检查失败',
};

/** The categories `events.EVENT_CATEGORIES` accepts, in the same words it uses. */
export const EVENT_CATEGORY: Record<string, string> = {
  lifecycle: '生命周期',
  state_change: '状态变更',
  attribute_change: '属性变更',
  interaction: '业务交互',
  external: '外部事件',
};

/**
 * Release-gate severity, which is a different scale from rule severity: a gate is
 * `blocker` or `warning`, a rule is `blocking` or `warning`. They share one word and not the
 * other, so putting gates in `RULE_SEVERITY` would translate half of them and print the rest
 * raw -- the kind of gap that reads as a styling inconsistency rather than a missing entry.
 */
export const GATE_SEVERITY: Record<string, string> = {
  blocker: '阻断',
  warning: '警告',
};

/** Structural drift between the modelled object and the live source. */
export const DRIFT_STATUS: Record<string, string> = {
  no_drift: '无漂移',
  drift_detected: '检测到漂移',
  error: '检查失败',
  skipped: '已跳过',
};

/**
 * The word for a value, or the value itself when this file has not learned it.
 *
 * A function rather than direct indexing at each call site so the fallback is decided once:
 * `LABEL[value]` silently yields `undefined`, which React renders as nothing at all.
 */
export const label = (map: Record<string, string>, value: unknown): string => {
  const key = String(value ?? '');
  return map[key] ?? key;
};

/** The relation kinds `relations.RELATION_KINDS` infers, in the same words it uses. */
export const RELATION_KIND: Record<string, string> = {
  composition: '组成',
  aggregation: '聚合',
  association: '关联',
};
