/**
 * governance —— 页面：pages/governance/index.tsx、AuditReportPanel.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('governance.…')`。
 */
import type { MessageEntry } from './shell';

export const governance: Record<string, MessageEntry> = {
  'title': { zh: '治理审计', en: 'Governance audit' },
  'refresh': { zh: '刷新', en: 'Refresh' },
  'loadFailed': { zh: '获取审计数据失败', en: 'Could not load the audit data' },

  'tabDecisions': { zh: '决策记录 ({count})', en: 'Decision records ({count})' },
  'tabAudit': { zh: '审计日志 ({count})', en: 'Audit log ({count})' },
  'tabInvocations': { zh: '模型调用记录 ({count})', en: 'Model invocations ({count})' },
  'tabReport': { zh: '审计报表', en: 'Audit report' },

  'column.actor': { zh: '操作者', en: 'Actor' },
  'column.action': { zh: '操作', en: 'Action' },
  'column.targetType': { zh: '目标类型', en: 'Target type' },
  'column.targetId': { zh: '目标ID', en: 'Target ID' },
  'column.detail': { zh: '详情', en: 'Detail' },
  'column.time': { zh: '时间（UTC）', en: 'Time (UTC)' },
  'column.provider': { zh: '提供商', en: 'Provider' },
  'column.model': { zh: '模型', en: 'Model' },
  'column.purpose': { zh: '用途', en: 'Purpose' },
  'column.promptTokens': { zh: '提示词Token', en: 'Prompt tokens' },
  'column.completionTokens': { zh: '完成Token', en: 'Completion tokens' },
  'column.totalTokens': { zh: '总Token', en: 'Total tokens' },
  'column.status': { zh: '状态', en: 'Status' },
  'column.decisionId': { zh: '决策编号', en: 'Decision ID' },
  'column.blockedDecisionId': { zh: '判定编号', en: 'Decision ID' },
  'column.type': { zh: '类型', en: 'Type' },
  'column.object': { zh: '业务对象', en: 'Business object' },
  'column.instanceId': { zh: '实例ID', en: 'Instance ID' },
  'column.operationCode': { zh: '操作码', en: 'Operation code' },
  'column.recommendation': { zh: '建议', en: 'Recommendation' },
  'column.code': { zh: '编码', en: 'Code' },
  'column.name': { zh: '名称', en: 'Name' },
  'column.severity': { zh: '严重级', en: 'Severity' },
  'column.evaluations': { zh: '求值次数', en: 'Evaluations' },

  'reportRange': { zh: '审计区间', en: 'Audit period' },
  'allOntologies': { zh: '全部本体', en: 'All ontologies' },
  'ontologyScope': { zh: '本体 #{id}', en: 'Ontology #{id}' },
  'generateButton': { zh: '生成报表', en: 'Generate report' },
  'generateFailed': { zh: '生成审计报表失败', en: 'Could not generate the audit report' },
  'generateFailedTitle': { zh: '生成失败', en: 'Generation failed' },
  'rangePolicyLead': {
    zh: '不提供「全部时间」：覆盖范围不明的报表会被当作对某个区间的陈述，',
    en: 'There is no "all time" option: a report whose coverage is unclear is read as a statement about some period, and ',
  },
  'rangePolicyStrong': { zh: '挂错区间的发现就是错的发现', en: 'a finding attached to the wrong period is a wrong finding' },
  'rangePolicyTail': { zh: '。区间为半开区间，起点闭、终点开。', en: '. The range is half-open: the start is included, the end is not.' },

  'reportPeriod': { zh: '报表区间：{start} → {end}', en: 'Report period: {start} → {end}' },
  'reportScope': { zh: '作用范围：{scope} · {boundary}', en: 'Scope: {scope} · {boundary}' },
  'noFindings': { zh: '本期没有需要立刻跟进的发现', en: 'No findings need follow-up right now' },
  'noFindingsDetail': {
    zh: '这不等于「一切正常」，只等于以下几类没有触发：从未求值的已发布规则、被覆盖的发布门禁、无解释链的求值、失败的模型调用。',
    en: 'This is not the same as everything being fine: it only means none of these fired -- published rules that were never evaluated, overridden release gates, evaluations without an explanation chain, and failed model calls.',
  },

  'statDecisions': { zh: '判定总数', en: 'Total decisions' },
  'statEvaluations': { zh: '规则求值', en: 'Rule evaluations' },
  'modelFailedSuffix': { zh: '（模型失败 {count}）', en: ' ({count} model failures)' },
  'statReviewable': { zh: '可复核比例', en: 'Reviewable share' },
  'ratioNoEvaluations': { zh: '本期没有规则求值，比例无从谈起', en: 'No rule evaluations this period, so there is no share to speak of' },
  'ratioDetail': { zh: '{withTrace} / {evaluations} 次求值带解释链', en: '{withTrace} of {evaluations} evaluations carry an explanation chain' },
  'statNeverTriggered': { zh: '从未求值的已发布规则', en: 'Published rules never evaluated' },

  'rulesCard': { zh: '规则触发情况', en: 'Rule firing' },
  'neverTriggered': { zh: '从未求值（{count}）', en: 'Never evaluated ({count})' },
  'triggered': { zh: '已求值（{count}）', en: 'Evaluated ({count})' },
  'rulesAllEvaluated': { zh: '本期所有已发布规则都参与过求值', en: 'Every published rule was evaluated this period' },
  'rulesNoneEvaluated': { zh: '本期没有规则参与过求值', en: 'No rule was evaluated this period' },

  'forcedCard': { zh: '覆盖发布门禁的发布', en: 'Publications that overrode a release gate' },
  'forcedNote': { zh: '覆盖门禁可以是正当的业务例外，但它不该需要审计去翻找', en: 'Overriding a gate can be a legitimate business exception, but it should not take an audit to find one' },
  'blockedCard': { zh: '被阻断的判定', en: 'Blocked decisions' },
  'blockedNote': { zh: '逐条列出而不是只给计数：一屏「40 条被阻断」回答不了「其中有没有被冤枉的」。', en: 'Listed one by one rather than only as a count: a screen reading "40 blocked" cannot answer "was any of them wrongly blocked?"' },

  'eventsCard': { zh: '治理事件（{count}）', en: 'Governance events ({count})' },
  'eventsEmpty': { zh: '本期没有发布、派生、门禁覆盖或配额调整', en: 'No publications, derivations, gate overrides or quota adjustments this period' },
  'byStatusCard': { zh: '按状态统计判定', en: 'Decisions by status' },
  'decisionsEmpty': { zh: '本期没有判定', en: 'No decisions this period' },
  'actorsCard': { zh: '操作者活动', en: 'Actor activity' },
  'eventsNone': { zh: '本期没有审计事件', en: 'No audit events this period' },
};
