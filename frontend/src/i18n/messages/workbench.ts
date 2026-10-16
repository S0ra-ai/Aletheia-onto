/**
 * workbench —— 页面：pages/workbench/index.tsx
 *
 * 两种语言都在这里，页面通过 `t('workbench.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const workbench: Record<string, MessageEntry> = {
  'title': { zh: '工作台', en: 'Workbench' },
  'subtitle': { zh: '平台当前状态与待处理事项', en: 'Where the platform stands, and what is waiting' },

  'refreshed': { zh: '工作台已刷新', en: 'Workbench refreshed' },
  'loadFailed': { zh: '加载工作台失败', en: 'Could not load the workbench' },
  'loadFailedTitle': { zh: '无法加载工作台', en: 'The workbench could not be loaded' },
  'loadFailedHint': { zh: '请确认后端服务可用。', en: 'Check that the backend service is reachable.' },
  'loading': { zh: '正在汇总平台状态...', en: 'Summarising the platform state...' },

  'startTaskTitle': { zh: '开始一个任务', en: 'Start with a task' },
  'startTaskHint': { zh: '按任务进入，复杂配置会在需要时展开', en: 'Pick the task you want to do; the detailed configuration appears only when you need it' },
  'demoButton': { zh: '先体验演示', en: 'Try the demo first' },
  'demoHint': { zh: '自动准备样例数据，快速看到一次完整研判', en: 'Sample data is prepared for you, so a full assessment is a few clicks away' },
  'datasourceButton': { zh: '接入自己的系统', en: 'Connect your own system' },
  'datasourceHint': { zh: '从连接数据源开始，系统会提示下一步', en: 'Start by connecting a data source; the platform suggests the next step' },
  'chatButton': { zh: '查看业务研判', en: 'Ask the model' },
  'chatHint': { zh: '对已初始化的业务对象提问并查看证据', en: 'Ask about the business objects you have set up, and read the evidence behind each answer' },

  'noActionItems': { zh: '没有待处理事项', en: 'Nothing is waiting' },
  'noActionItemsHint': { zh: '数据源已扫描、映射已审核、对象已配置规则。', en: 'Sources have been scanned, mappings have been reviewed, and objects have their rules configured.' },

  'actionItemsTitle': { zh: '待处理事项', en: 'Action items' },
  'blockersTag': { zh: '{count} 项阻断', en: '{count} blockers' },
  'warningsTag': { zh: '{count} 项待处理', en: '{count} pending' },
  'openItem': { zh: '去处理', en: 'Open' },

  'severity.blocker': { zh: '阻断', en: 'Blocker' },
  'severity.warning': { zh: '待处理', en: 'Pending' },
  'severity.info': { zh: '提示', en: 'Info' },

  'countSuffix': { zh: '个', en: 'total' },
  'dataSources': { zh: '数据源', en: 'Data sources' },
  'tables': { zh: '{count} 张表', en: '{count} tables' },
  'unscanned': { zh: '{count} 个未扫描', en: '{count} unscanned' },
  'allScanned': { zh: '全部已扫描', en: 'all scanned' },
  'withBusinessApi': { zh: '{count} 个含业务 API', en: '{count} with business APIs' },

  'businessObjects': { zh: '业务对象', en: 'Business objects' },
  'relations': { zh: '{count} 条关系', en: '{count} relations' },
  'relations.one': { zh: '{count} 条关系', en: '{count} relation' },
  'publishedOntologies': { zh: '{count} 个已发布本体', en: '{count} published' },
  'draftOntologies': { zh: '{count} 个草案', en: '{count} drafts' },
  'draftOntologies.one': { zh: '{count} 个草案', en: '{count} draft' },

  'businessRules': { zh: '业务规则', en: 'Business rules' },
  'blockingRules': { zh: '阻断级 {count}', en: '{count} blocking' },
  'advisoryRules': { zh: '提示级 {count}', en: '{count} advisory' },

  'decisionLog': { zh: '决策留痕', en: 'Decision log' },
  'decisionsBlocked': { zh: '阻断 {count}', en: '{count} blocked' },
  'decisionsReview': { zh: '复核 {count}', en: '{count} in review' },
  'decisionsApproved': { zh: '通过 {count}', en: '{count} approved' },

  'governanceProgress': { zh: '治理进度', en: 'Governance progress' },
  'mappingGate': { zh: '语义映射审核（发布门禁依据此项）', en: 'Semantic mapping review (what the release gate counts)' },
  'pendingMappings': { zh: '待审映射：{count}', en: 'Mappings pending review: {count}' },
  'auditEntries': { zh: '审计条目：{count}', en: 'Audit entries: {count}' },
  'valueMappings': { zh: '值域映射：{count} 已确认', en: 'Value mappings: {count} confirmed' },
  'valueMappingsPending': { zh: '{count} 待确认', en: '{count} unconfirmed' },

  'recentDecisions': { zh: '最近决策', en: 'Recent decisions' },
  'viewAll': { zh: '全部', en: 'All' },
  'noDecisions': { zh: '尚无决策记录', en: 'No decisions recorded' },
  // The workbench is where a new deployment lands, and an empty card with no next step is the
  // first thing its reader sees.
  'noDecisionsHint': {
    zh: '决策来自一次研判：到「业务研判」对某个实例做一次判定，或到「演示中心」一键跑通接入、建模与判定的完整链路。',
    en: 'A decision comes from an assessment: assess an instance under Assessment, or run the whole path -- connect, model, assess -- in one click from the Demo centre.',
  },
  'column.status': { zh: '状态', en: 'Status' },
  'column.object': { zh: '对象', en: 'Object' },
  'column.instance': { zh: '实例', en: 'Instance' },
  'column.type': { zh: '类型', en: 'Type' },
  'column.createdAt': { zh: '时间（UTC）', en: 'Time (UTC)' },

  'generatedAt': { zh: '统计生成于 {time}', en: 'Statistics generated at {time}' },

  // What to do next. The server builds these sentences -- it is the half that knows the
  // counts -- and sends them in Chinese, which meant the first screen a reader sees was
  // English everywhere except the list of things it was telling them to do. Each item already
  // carries a stable `code`, so the console can say the same thing in the reader's language
  // and fall back to the server's sentence for a code it does not know yet.
  'item.no_data_source.title': { zh: '尚未接入任何数据源', en: 'No data source connected yet' },
  'item.no_data_source.detail': {
    zh: '平台的全部能力都从元数据扫描开始，先接入一个业务库。',
    en: 'Everything the platform does starts from a metadata scan. Connect a business database first.',
  },
  'item.unscanned_data_source.title': { zh: '{count} 个数据源尚未扫描元数据', en: '{count} data sources have not been scanned' },
  'item.unscanned_data_source.detail': {
    zh: '未扫描的数据源无法生成本体草案。',
    en: 'An unscanned source cannot produce an ontology draft.',
  },
  'item.unscanned_data_source.title.one': { zh: '{count} 个数据源尚未扫描元数据', en: '{count} data source has not been scanned' },
  'item.no_ontology.title': { zh: '已接入数据源但尚无本体', en: 'No ontology yet, though a source is connected' },
  'item.no_ontology.detail': {
    zh: '生成本体草案后才能配置规则与输出判定。',
    en: 'Rules and verdicts come after the ontology draft exists.',
  },
  'item.pending_mappings.title': { zh: '{count} 条语义映射待审核', en: '{count} semantic mappings await review' },
  'item.pending_mappings.detail': {
    zh: '存在待审映射时发布门禁不会通过。',
    en: 'The release gate does not pass while mappings are pending.',
  },
  'item.pending_mappings.title.one': { zh: '{count} 条语义映射待审核', en: '{count} semantic mapping awaits review' },
  'item.unbound_objects.title': { zh: '{count} 个业务对象未绑定来源表', en: '{count} business objects have no source table' },
  'item.unbound_objects.detail': {
    zh: '未绑定来源表的对象无法解析实例，也无法参与研判。',
    en: 'An object with no source table cannot resolve instances or take part in an assessment.',
  },
  'item.unbound_objects.title.one': { zh: '{count} 个业务对象未绑定来源表', en: '{count} business object has no source table' },
  'item.no_rules.title': { zh: '尚未配置任何业务规则', en: 'No business rules configured' },
  'item.no_rules.detail': {
    zh: '没有规则就没有判定结论，平台只能做元数据浏览。',
    en: 'Without rules there are no verdicts; the platform can only browse metadata.',
  },
  'item.objects_without_rules.title': { zh: '{count} 个业务对象没有任何规则', en: '{count} business objects have no rules' },
  'item.objects_without_rules.detail': {
    zh: '这些对象不会产出判定结论。',
    en: 'These objects will not produce a verdict.',
  },
  'item.objects_without_rules.title.one': { zh: '{count} 个业务对象没有任何规则', en: '{count} business object has no rules' },
  'item.reviewable_transitions.title': {
    zh: '{count} 个实例处于需复核的流转状态',
    en: '{count} instances are waiting for a review before they can move on',
  },
  'item.reviewable_transitions.title.one': {
    zh: '{count} 个实例处于需复核的流转状态',
    en: '{count} instance is waiting for a review before it can move on',
  },
  'item.reviewable_transitions.detail': {
    zh: '这些实例等待人工确认后才能继续流转。',
    en: 'They stay where they are until a person confirms the transition.',
  },
  'item.incorrect_answers_reported.title': { zh: '{count} 条回答被标记为错误', en: '{count} answers were marked incorrect' },
  'item.incorrect_answers_reported.detail': {
    zh: '用户认为判定结论有误，应复核相关规则或知识条目。',
    en: 'Readers judged the verdict wrong. Review the rules or the knowledge entries behind it.',
  },
  'item.incorrect_answers_reported.title.one': { zh: '{count} 条回答被标记为错误', en: '{count} answer was marked incorrect' },
  'item.escalated_conversations.title': { zh: '{count} 个会话已转人工', en: '{count} conversations were escalated' },
  'item.escalated_conversations.detail': {
    zh: '这些会话等待人工接手处理。',
    en: 'They are waiting for a person to take them over.',
  },
  'item.escalated_conversations.title.one': { zh: '{count} 个会话已转人工', en: '{count} conversation was escalated' },
  'item.open_feedback.title': { zh: '{count} 条反馈待处理', en: '{count} feedback items are open' },
  'item.open_feedback.detail': {
    zh: '包含未处理的满意度反馈与纠正建议。',
    en: 'Unresolved satisfaction ratings and correction suggestions.',
  },
  'item.open_feedback.title.one': { zh: '{count} 条反馈待处理', en: '{count} feedback item is open' },
};
