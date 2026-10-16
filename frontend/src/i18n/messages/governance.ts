/**
 * governance —— 页面：pages/governance/index.tsx、AuditReportPanel.tsx
 *
 * 两种语言都在这里，页面通过 `t('governance.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
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
  // The server sends this string too, and the CLI prints it. The console says its own: a
  // sentence that describes the interval is about the reader's language, not about the data.
  'rangeBoundary': { zh: '半开区间 [start, end)', en: 'half-open interval [start, end)' },

  // What each section of the report answers, keyed by the section's stable `section` field.
  // The server sends the Chinese wording as well, and it is the fallback for a key this build
  // does not know -- a sentence in the wrong language beats a ⟦key⟧ in any language.
  'section.decisions': {
    zh: '按结论与严重级聚合，回答「这段时间阻断了多少、为什么」',
    en: 'Counts by verdict and severity: how much was blocked in this period, and why',
  },
  'section.rules': {
    zh: '含从未触发的已发布规则——那是控制失效还是死规则',
    en: 'Includes published rules that never fired — a broken control, or a rule that is simply dead',
  },
  'section.actors': {
    zh: '谁在这段时间改了什么，按操作者与动作聚合',
    en: 'Who changed what in this period, by actor and action',
  },
  'section.governance': {
    zh: '发布、派生、覆盖门禁、配额调整',
    en: 'Publications, derivations, gate overrides, quota changes',
  },
  'section.model': {
    zh: '哪些结论涉及模型，以及调用是否失败',
    en: 'Which conclusions involved a model, and whether those calls failed',
  },
  'section.coverage': {
    zh: '每次规则求值是否都带解释链——缺失意味着结论无法复核',
    en: 'Whether every rule evaluation carries its explanation chain — a gap means the verdict cannot be re-examined',
  },
  'rulesNote': {
    zh: '从未触发的已发布规则要么是死规则，要么在静默地匹配不到任何实例——后者意味着组织以为存在的控制并未运行。',
    en: 'A published rule that never fired is either dead, or silently matching no instance at all — and the second means a control the organisation believes in is not running.',
  },

  // The findings, composed from the `code` and the number the server sends beside it. The
  // server's own Chinese sentence is the fallback, and its `action` line is where the
  // instruction lives -- both are kept for the CLI.
  'finding.rules_never_triggered.finding': {
    zh: '{count} 条已发布规则在本期内从未参与求值',
    en: '{count} published rules never took part in an evaluation this period',
  },
  'finding.rules_never_triggered.finding.one': {
    zh: '{count} 条已发布规则在本期内从未参与求值',
    en: '{count} published rule never took part in an evaluation this period',
  },
  'finding.rules_never_triggered.action': {
    zh: '确认是死规则（应下线）还是匹配失效（是控制缺口）。',
    en: 'Establish whether it is dead (and should be retired) or matching nothing (which is a gap in the control).',
  },
  'finding.forced_publications.finding': {
    zh: '本期存在 {count} 次覆盖发布门禁的发布',
    en: '{count} publications overrode the release gate this period',
  },
  'finding.forced_publications.finding.one': {
    zh: '本期存在 {count} 次覆盖发布门禁的发布',
    en: '{count} publication overrode the release gate this period',
  },
  'finding.forced_publications.action': {
    zh: '逐条复核覆盖理由与当时未通过的门禁项。',
    en: 'Review each override against the gate items that were failing at the time.',
  },
  'finding.trace_gap.finding': {
    zh: '仅 {ratio} 的规则求值带有解释链',
    en: 'Only {ratio} of rule evaluations carry an explanation chain',
  },
  'finding.trace_gap.action': {
    zh: '无解释链的求值无法复核，等同于本期该部分不可审计。',
    en: 'An evaluation with no chain cannot be re-examined, which makes that part of the period unauditable.',
  },
  'finding.model_failures.finding': {
    zh: '本期有 {count} 次模型调用失败',
    en: '{count} model calls failed this period',
  },
  'finding.model_failures.finding.one': {
    zh: '本期有 {count} 次模型调用失败',
    en: '{count} model call failed this period',
  },
  'finding.model_failures.action': {
    zh: '模型不可用时平台回退本地启发式，相关答案的产生路径与其他期不同。',
    en: 'When the model is unavailable the platform falls back to local heuristics, so those answers were produced by a different path than the rest of the period.',
  },
  'noFindings': { zh: '本期没有需要立刻跟进的发现', en: 'No findings this period need immediate follow-up' },
  'noFindingsDetail': {
    zh: '这不等于「一切正常」，只等于以下几类没有触发：从未求值的已发布规则、被覆盖的发布门禁、无解释链的求值、失败的模型调用。',
    en: 'This does not mean everything is fine. It means only that none of the following fired: published rules that were never evaluated, overridden release gates, evaluations without an explanation chain, and failed model calls.',
  },

  'statDecisions': { zh: '判定总数', en: 'Total decisions' },
  'statEvaluations': { zh: '规则求值', en: 'Rule evaluations' },
  'modelFailedSuffix': { zh: '（模型失败 {count}）', en: ' ({count} model failures)' },
  'statReviewable': { zh: '可复核比例', en: 'Reviewable share' },
  'ratioNoEvaluations': { zh: '本期没有规则求值，比例无从谈起', en: 'No rules were evaluated this period, so there is no share to speak of' },
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
  'blockedNote': { zh: '逐条列出而不是只给计数：一屏「40 条被阻断」回答不了「其中有没有被冤枉的」。', en: 'The decisions are listed one by one rather than only as a count: a screen reading "40 blocked" cannot answer whether any of them was wrongly blocked.' },

  'eventsCard': { zh: '治理事件（{count}）', en: 'Governance events ({count})' },
  'eventsEmpty': { zh: '本期没有发布、派生、门禁覆盖或配额调整', en: 'No publications, derivations, gate overrides or quota adjustments this period' },
  'byStatusCard': { zh: '按状态统计判定', en: 'Decisions by status' },
  'decisionsEmpty': { zh: '本期没有判定', en: 'No decisions this period' },
  'actorsCard': { zh: '操作者活动', en: 'Actor activity' },
  'eventsNone': { zh: '本期没有审计事件', en: 'No audit events this period' },
};
