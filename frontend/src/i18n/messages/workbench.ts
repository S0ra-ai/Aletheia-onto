/**
 * workbench —— 页面：pages/workbench/index.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('workbench.…')`。
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
  'startTaskHint': { zh: '按任务进入，复杂配置会在需要时展开', en: 'Enter by task; the complex configuration unfolds only when it is needed' },
  'demoButton': { zh: '先体验演示', en: 'Try the demo first' },
  'demoHint': { zh: '自动准备样例数据，快速看到一次完整研判', en: 'Sample data is prepared for you, so a full analysis is a few clicks away' },
  'datasourceButton': { zh: '接入自己的系统', en: 'Connect your own system' },
  'datasourceHint': { zh: '从连接数据源开始，系统会提示下一步', en: 'Start by connecting a data source; the platform suggests the next step' },
  'chatButton': { zh: '查看业务研判', en: 'Look at an analysis' },
  'chatHint': { zh: '对已初始化的业务对象提问并查看证据', en: 'Ask an initialised business object questions, and read the evidence' },

  'noActionItems': { zh: '没有待处理事项', en: 'Nothing is waiting' },
  'noActionItemsHint': { zh: '数据源已扫描、映射已审核、对象已配置规则。', en: 'Sources are scanned, mappings are reviewed, and objects carry their rules.' },

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
  'publishedOntologies': { zh: '{count} 个已发布本体', en: '{count} published' },
  'draftOntologies': { zh: '{count} 个草案', en: '{count} drafts' },

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
  'column.status': { zh: '状态', en: 'Status' },
  'column.object': { zh: '对象', en: 'Object' },
  'column.instance': { zh: '实例', en: 'Instance' },
  'column.type': { zh: '类型', en: 'Type' },
  'column.createdAt': { zh: '时间（UTC）', en: 'Time (UTC)' },

  'generatedAt': { zh: '统计生成于 {time}', en: 'Statistics generated at {time}' },
};
