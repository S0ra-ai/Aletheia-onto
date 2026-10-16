/**
 * chat —— 页面：pages/chat/OntologyChat.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('chat.…')`。
 */
import type { MessageEntry } from './shell';

export const chat: Record<string, MessageEntry> = {
  'title': { zh: '智能体对话', en: 'Agent chat' },
  'subtitle': { zh: '选择角色和数据源，像与业务专家对话一样提问；回答基于真实数据和已确认的业务规则。', en: 'Choose a role and a data source, then ask the way you would ask a domain expert; the answers rest on real data and confirmed business rules.' },
  'dataSourcePlaceholder': { zh: '数据源', en: 'Data source' },
  'objectPlaceholder': { zh: '业务对象', en: 'Business object' },
  'clearButton': { zh: '清空', en: 'Clear' },
  'askPlaceholder': { zh: '向{role}提问...', en: 'Ask {role}...' },
  'agentFallback': { zh: '智能体', en: 'Agent' },
  'advisorFallback': { zh: '业务顾问', en: 'your business advisor' },

  'noKnowledgeTitle': { zh: '暂无可问答的数据源', en: 'No data source to ask about yet' },
  'noKnowledgeHint': { zh: '请先在数据源管理中完成连接测试和知识库初始化。', en: 'Run a connection test and initialise a knowledge base under Data sources first.' },

  'welcomeIntro': { zh: '你好，我是{roleName}。{roleDescription}', en: 'Hello, I am {roleName}. {roleDescription}' },
  'welcomeReady': { zh: '\n\n数据源与业务对象已选定，直接提问即可。', en: '\n\nA data source and a business object are selected, so you can ask right away.' },
  'welcomeSelectFirst': { zh: '\n\n请先选择已初始化的数据源和业务对象，然后向我提问。', en: '\n\nChoose an initialised data source and a business object first, then ask your question.' },

  'promptAllSources': { zh: '查看所有已接入的数据源', en: 'Show every connected data source' },
  'promptObjects': { zh: '当前知识库有哪些业务对象？', en: 'Which business objects does this knowledge base contain?' },
  'promptCompliance': { zh: '{name}整体是否合规？', en: 'Is {name} compliant overall?' },
  'promptRules': { zh: '查看{name}的业务规则', en: 'Show the business rules for {name}' },
  'promptConsistency': { zh: '{name}决策是否一致？', en: 'Are the decisions about {name} consistent?' },
  'promptRelations': { zh: '{name}有哪些关联关系？', en: 'What relationships does {name} have?' },

  'feedbackGiven': { zh: '已反馈：', en: 'Feedback: ' },
  'feedbackHelpful': { zh: '有帮助', en: 'Helpful' },
  'feedbackUnhelpful': { zh: '没帮助', en: 'Not helpful' },
  'feedbackUnhelpfulRecorded': { zh: '没有帮助', en: 'Not helpful' },
  'feedbackIncorrect': { zh: '结论错误', en: 'Wrong conclusion' },
  'feedbackRecordedIncorrect': { zh: '已记录：该结论被标记为错误，将进入复核队列', en: 'Recorded: the conclusion was marked wrong and enters the review queue' },
  'feedbackThanks': { zh: '感谢反馈', en: 'Thanks for the feedback' },
  'feedbackFailed': { zh: '提交反馈失败', en: 'Could not submit the feedback' },

  'requestFailed': { zh: '对话失败，请检查模型配置或数据源本体是否已生成', en: 'The conversation failed. Check the model configuration and whether the data source ontology has been generated.' },
  'assistantUnavailable': { zh: '我暂时无法完成这次语义研判。请确认已接入数据源并生成本体，或在模型配置中测试 OpenRouter 连接。', en: 'I cannot complete this analysis right now. Check that a data source is connected and an ontology has been generated, or test the OpenRouter connection under Model configuration.' },
  'dataSourceTag': { zh: '数据源 #{id}', en: 'Data source #{id}' },
  'modelUnderstanding': { zh: '模型理解', en: 'Model understanding' },
  'toolCalls': { zh: '工具调用 x{count}', en: 'Tool calls x{count}' },
  'analysing': { zh: '正在分析问题、调用本体内核并整理回答...', en: 'Analysing the question, calling the ontology kernel, and drafting the answer...' },

  'enterHint': { zh: 'Enter 发送，Shift + Enter 换行', en: 'Enter to send, Shift + Enter for a new line' },
  'sendButton': { zh: '发送', en: 'Send' },
};
