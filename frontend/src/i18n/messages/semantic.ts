/**
 * semantic —— 页面：pages/semantic/index.tsx
 *
 * 两种语言都在这里，页面通过 `t('semantic.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const semantic: Record<string, MessageEntry> = {
  'title': { zh: '语义服务', en: 'Semantic service' },
  'subtitle': { zh: '提供实例解释、风险研判和操作预检能力', en: 'Instance explanation, risk assessment and operation preflight.' },

  'tab.natural': { zh: '自然语言交互', en: 'Natural language' },
  'tab.explain': { zh: '实例解释', en: 'Instance explanation' },
  'tab.assess': { zh: '风险研判', en: 'Risk assessment' },
  'tab.consistency': { zh: '决策一致性', en: 'Decision consistency' },
  'tab.preflight': { zh: '操作预检', en: 'Operation preflight' },

  'queryFailed': { zh: '自然语言语义问答失败', en: 'The natural-language query failed' },
  'explainFailed': { zh: '语义解释失败', en: 'The explanation failed' },
  'assessFailed': { zh: '语义研判失败', en: 'The assessment failed' },
  'consistencyFailed': { zh: '决策一致性评估失败', en: 'The consistency assessment failed' },
  'preflightFailed': { zh: '操作预检失败', en: 'The preflight check failed' },
  'invalidPayload': { zh: '请求载荷不是合法 JSON', en: 'The request payload is not valid JSON' },
  'executeFailed': { zh: '操作执行失败', en: 'The operation failed' },

  'ontologyId': { zh: '本体ID', en: 'Ontology ID' },
  'dataSourceId': { zh: '数据源ID', en: 'Data source ID' },
  'objectCode': { zh: '业务对象编码', en: 'Business object code' },
  'instanceId': { zh: '实例ID', en: 'Instance ID' },
  'operationCode': { zh: '操作码', en: 'Operation code' },
  'businessObject': { zh: '业务对象', en: 'Business object' },
  'decision': { zh: '决策', en: 'Decision' },
  'status': { zh: '状态', en: 'Status' },

  'optional': { zh: '可选', en: 'Optional' },
  'idPlaceholder': { zh: '例如：1', en: 'e.g. 1' },
  'ontologyIdOptionalPlaceholder': { zh: '可选，默认为1', en: 'Optional, defaults to 1' },
  'objectCodePlaceholder': { zh: '留空则自动识别', en: 'Auto-detected if left blank' },
  'objectCodeOptionalPlaceholder': { zh: '可选，例如：contract', en: 'Optional, e.g. contract' },
  'operationCodePlaceholder': { zh: '例如：submit_contract', en: 'e.g. submit_contract' },

  'question': { zh: '业务问题', en: 'Business question' },
  'questionPlaceholder': {
    zh: '例如：合同 1 是否合规？HT-2026-003 能提交审批吗？合同整体决策是否一致？',
    en: 'e.g. Is contract 1 compliant? Can HT-2026-003 be submitted for approval? Is the overall decision for the contract consistent?',
  },
  'askButton': { zh: '询问本体系统', en: 'Ask the ontology system' },

  'answerTitle': { zh: '本体系统回答', en: 'Answer from the ontology system' },
  'intent': { zh: '识别意图', en: 'Detected intent' },
  'confidence': { zh: '置信度', en: 'Confidence' },
  'nextActions': { zh: '建议动作', en: 'Suggested actions' },
  'evidence': { zh: '语义证据', en: 'Semantic evidence' },

  'explainButton': { zh: '解释', en: 'Explain' },
  'explainResultTitle': { zh: '解释结果', en: 'Explanation result' },
  'attributes': { zh: '属性', en: 'Attributes' },
  'attributeColumn': { zh: '属性', en: 'Attribute' },
  'codeColumn': { zh: '编码', en: 'Code' },
  'sourceColumn': { zh: '来源', en: 'Source' },
  'valueColumn': { zh: '值', en: 'Value' },
  'emptyValue': { zh: '空值', en: 'No value' },
  // The explanation paragraph, composed from the codes the server sends beside each sentence
  // (`explanationParts`). The server's paragraph is the fallback for a code this build does
  // not know -- a sentence in the wrong language beats a ⟦key⟧ in any language.
  'part.explain_mapped_to_source': {
    zh: '{object}实例 {instance} 已映射到传统表 {table}。',
    en: '{object} instance {instance} is mapped to the legacy table {table}.',
  },
  'part.explain_as_of': {
    zh: '本次解释针对 {asOf} 这一刻，历史覆盖的字段以当时取值为准。',
    en: 'This explanation is as of {asOf}; fields with history are read as they stood then.',
  },
  'part.explain_derived_attributes': {
    zh: '其中 {count} 个属性由表达式算出而非直接读取：{attributes}。',
    en: '{count} of the attributes are computed from expressions rather than read directly: {attributes}.',
  },
  'part.explain_derived_attributes.one': {
    zh: '其中 {count} 个属性由表达式算出而非直接读取：{attributes}。',
    en: '{count} attribute is computed from an expression rather than read directly: {attributes}.',
  },
  'part.explain_declared_units': {
    zh: '{count} 个属性带声明单位，比较时会先换算。',
    en: '{count} attributes carry a declared unit and are converted before comparison.',
  },
  'part.explain_declared_units.one': {
    zh: '{count} 个属性带声明单位，比较时会先换算。',
    en: '{count} attribute carries a declared unit and is converted before comparison.',
  },
  'part.explain_aggregates': {
    zh: '另有 {count} 个跨对象聚合值可供规则引用：{names}。',
    en: 'Rules can also read {count} cross-object aggregates: {names}.',
  },
  'part.explain_aggregates.one': {
    zh: '另有 {count} 个跨对象聚合值可供规则引用：{names}。',
    en: 'Rules can also read {count} cross-object aggregate: {names}.',
  },
  'part.explain_aggregate_truncated': {
    zh: '其中部分聚合已达到取数上限，结果为部分数据。',
    en: 'Some of those aggregates hit the row limit, so the result is partial.',
  },
  // The kernel's recommendation, on the decisions table and the assessment panels.
  'recommendation.recommendation_blocked_unevaluable': {
    zh: '存在阻断级规则未通过，且部分规则无法求值（可能由结构漂移导致）。应暂停自动化操作，先修复规则表达式或来源字段映射。',
    en: 'A blocking rule failed, and some rules could not be evaluated at all (schema drift can do that). Pause automation and fix the rule expressions or the source-field mappings first.',
  },
  'recommendation.recommendation_blocked': {
    zh: '存在阻断级规则未通过，应暂停自动化操作并要求业务人员复核。',
    en: 'A blocking rule failed. Pause automation and have a business user review it.',
  },
  'recommendation.recommendation_review_unevaluable': {
    zh: '部分规则无法在当前数据结构上求值，已按未通过处理，应人工复核规则表达式与来源字段后再恢复自动化。',
    en: 'Some rules cannot be evaluated against the current structure and were treated as failed. Review the rule expressions and source fields before restoring automation.',
  },
  'recommendation.recommendation_review': {
    zh: '存在风险或警告，应进入人工复核或触发后续治理流程。',
    en: 'There are warnings or risks. Send it for human review, or trigger the governance flow.',
  },
  'recommendation.recommendation_approved': {
    zh: '未发现阻断或风险规则，允许进入后续自动化流程。',
    en: 'No blocking or risk rules fired; automation may proceed.',
  },
  // The consistency report's advice.
  'advice.consistency_no_instances': {
    zh: '没有可评估实例，请检查来源表数据或显式传入实例 ID。',
    en: 'There are no instances to assess. Check the source table, or pass instance ids explicitly.',
  },
  'advice.consistency_all_passed': {
    zh: '样本决策全部通过，可继续扩大批量验证范围。',
    en: 'Every verdict in the sample passed. The batch can be widened.',
  },
  'advice.consistency_not_all_passed': {
    zh: '样本决策结果一致但未全部通过，应确认该业务对象当前规则阈值是否符合预期。',
    en: 'The verdicts agree but not all passed. Confirm the rule thresholds for this object are the ones you mean.',
  },
  'advice.consistency_errors_first': {
    zh: '先处理批量评估中的实例读取或规则执行错误。',
    en: 'Deal with the instance-read or rule-execution errors in the batch first.',
  },
  'advice.consistency_top_failing_rule': {
    zh: '优先复核失败次数最高的规则：{rule}。',
    en: 'Review the rule that failed most often first: {rule}.',
  },
  'advice.consistency_blocked': {
    zh: '存在阻断级决策，自动化执行前必须完成规则或数据治理。',
    en: 'There are blocking verdicts. Rule or data governance has to happen before anything is automated.',
  },
  'advice.consistency_mixed': {
    zh: '决策结果存在分化，建议扩大样本并复核规则分层。',
    en: 'The verdicts are divided. Widen the sample and review how the rules are layered.',
  },
  'explanation': { zh: '解释', en: 'Explanation' },
  'objectsHint': {
    zh: '在「对象浏览」中点击任一实例的「解释」，可以看到同一份解释加上事件历史与取值沿革。',
    en: 'In "Business objects", clicking "Explain" on any instance shows the same explanation plus event history and value history.',
  },

  'assessButton': { zh: '研判', en: 'Assess' },
  'assessResultTitle': { zh: '研判结果', en: 'Assessment result' },
  'rulesHit': { zh: '命中的规则', en: 'Matched rules' },
  'rulePassed': { zh: '通过', en: 'Passed' },
  'ruleFailed': { zh: '未通过', en: 'Not passed' },
  'ruleSeparator': { zh: '：', en: ': ' },

  'sampleLimit': { zh: '抽样上限', en: 'Sample limit' },
  'sampleLimitPlaceholder': { zh: '默认 50，最大 200', en: 'Default 50, maximum 200' },
  'instanceIds': { zh: '指定实例ID', en: 'Specific instance IDs' },
  'instanceIdsPlaceholder': {
    zh: '可选。多个实例可用逗号、空格或换行分隔，例如：1,2,3',
    en: 'Optional. Separate multiple instances with commas, spaces or newlines, e.g. 1,2,3',
  },
  'batchAssessButton': { zh: '批量评估', en: 'Batch assess' },
  'consistencyResultTitle': { zh: '一致性评估结果', en: 'Consistency assessment result' },
  'sampleSize': { zh: '样本数', en: 'Sample size' },
  'assessed': { zh: '已评估', en: 'Assessed' },
  'summaryApproved': { zh: '通过', en: 'Approved' },
  'summaryReview': { zh: '复核', en: 'In review' },
  'summaryBlocked': { zh: '阻断', en: 'Blocked' },
  'summaryErrors': { zh: '错误', en: 'Errors' },
  'governanceAdvice': { zh: '治理建议', en: 'Governance advice' },
  'ruleFailureDistribution': { zh: '规则失败分布', en: 'Rule failure distribution' },
  'assessmentErrors': { zh: '评估错误', en: 'Assessment errors' },
  'failedRuleCount': { zh: '失败规则数', en: 'Failed rule count' },
  'failedRules': { zh: '失败规则', en: 'Failed rules' },
  'decisionId': { zh: '决策ID', en: 'Decision ID' },
  'listSeparator': { zh: '；', en: '; ' },

  'preflightButton': { zh: '预检', en: 'Preflight' },
  'executeButton': { zh: '执行', en: 'Execute' },
  'actor': { zh: '操作者', en: 'Actor' },
  'actorPlaceholder': { zh: '例如：业务控制台', en: 'e.g. business console' },
  'payloadJson': { zh: '执行载荷 JSON', en: 'Execution payload JSON' },
  'payloadPlaceholder': { zh: '例如：{"comment":"自动提交"}', en: 'e.g. {"comment":"auto submit"}' },
  'dryRun': { zh: '仅生成执行计划', en: 'Generate the plan only' },
  'preflightResultTitle': { zh: '预检结果', en: 'Preflight result' },
  'recommendation': { zh: '建议', en: 'Recommendation' },
  'none': { zh: '无', en: 'None' },
  'executeResultTitle': { zh: '执行结果', en: 'Execution result' },
  'executionPlan': { zh: '执行计划', en: 'Execution plan' },
};
