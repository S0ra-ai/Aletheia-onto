/**
 * feedback —— 页面：pages/feedback/FeedbackConsole.tsx
 *
 * 两种语言都在这里，页面通过 `t('feedback.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const feedback: Record<string, MessageEntry> = {
  'title': { zh: '反馈闭环', en: 'Feedback loop' },
  'subtitle': { zh: '用户对判定结论的评价、纠正建议与转人工队列', en: 'Ratings of decisions, suggested corrections, and the human-review queue' },

  'loadFailed': { zh: '加载反馈失败', en: 'Could not load feedback' },
  'actionFailed': { zh: '操作失败', en: 'Could not complete the action' },
  'resolveDone': { zh: '已标记为已处理', en: 'Marked as resolved' },
  'dismissDone': { zh: '已忽略', en: 'Dismissed' },

  'allRatings': { zh: '全部评价', en: 'All ratings' },
  'allStatuses': { zh: '全部状态', en: 'All statuses' },
  'rating.incorrect': { zh: '结论错误', en: 'Wrong conclusion' },
  'rating.unhelpful': { zh: '没有帮助', en: 'Unhelpful' },
  'rating.helpful': { zh: '有帮助', en: 'Helpful' },

  'statIncorrect': { zh: '标记为错误', en: 'Flagged as wrong' },
  'statIncorrectHint': { zh: '最强的复核信号', en: 'The strongest review signal' },
  'statCorrections': { zh: '纠正建议', en: 'Suggested corrections' },
  'statCorrectionsHint': { zh: '需人工判断是否入规则', en: 'A person decides whether it becomes a rule' },

  'correctionsAlertTitle': { zh: '纠正建议不会自动生效', en: 'A correction does not take effect on its own' },
  'correctionsAlertBody': {
    zh: '用户提交的纠正是一方主张，不是新规则。若确认应当调整判定，请在业务规则或文档知识库中走正常的治理与发布流程。',
    en: 'A submitted correction is one user\'s claim, not a new rule. If the decision really should change, take it through the usual governance and publication path in Business rules or the knowledge base.',
  },

  'escalationQueue': { zh: '转人工队列', en: 'Human-review queue' },
  'column.conversation': { zh: '会话', en: 'Conversation' },
  'column.assignee': { zh: '指派给', en: 'Assigned to' },
  'column.reason': { zh: '原因', en: 'Reason' },
  'view': { zh: '查看', en: 'View' },

  'itemsTitle': { zh: '反馈条目（{count}）', en: 'Feedback items ({count})' },
  'noItems': { zh: '没有符合条件的反馈', en: 'No feedback matches these filters' },
  'commentLabel': { zh: '用户评论：', en: 'User comment: ' },
  'correctionLabel': { zh: '纠正建议：', en: 'Suggested correction: ' },
  'decisionLabel': { zh: '关联决策：', en: 'Linked decision: ' },
  'decisionHint': { zh: '可在治理与留痕中查看该判定的规则与证据链', en: 'The rules and evidence behind this decision can be read under Governance' },
  'noNote': { zh: '该反馈没有附加说明。', en: 'This feedback has no attached note.' },

  'column.rating': { zh: '评价', en: 'Rating' },
  'column.correction': { zh: '纠正', en: 'Correction' },
  'hasCorrection': { zh: '有', en: 'Yes' },
  'column.decision': { zh: '关联决策', en: 'Linked decision' },
  'decisionTooltip': { zh: '反馈已关联到具体判定，可回溯规则与证据', en: 'This feedback is linked to a specific decision, so its rules and evidence can be traced' },
  'column.actor': { zh: '提交人', en: 'Submitted by' },
  'anonymous': { zh: '匿名', en: 'Anonymous' },
  'column.status': { zh: '状态', en: 'Status' },
  'column.createdAt': { zh: '时间（UTC）', en: 'Time (UTC)' },

  'resolve': { zh: '已处理', en: 'Resolve' },
  'dismiss': { zh: '忽略', en: 'Dismiss' },
};
