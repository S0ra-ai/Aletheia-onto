/**
 * semantic —— 页面：pages/semantic/index.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('semantic.…')`。
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
