/**
 * knowledge —— 页面：pages/knowledge/KnowledgeBase.tsx
 *
 * 两种语言都在这里，页面通过 `t('knowledge.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const knowledge: Record<string, MessageEntry> = {
  'title': { zh: '文档知识库', en: 'Knowledge base' },
  'subtitle': { zh: '制度与合同条款，锚定到业务对象或规则后可作为判定依据被引用', en: 'Policy and contract clauses; once anchored to a business object or rule, they can be cited as the basis for a decision.' },

  'refresh': { zh: '刷新', en: 'Refresh' },
  'uploadButton': { zh: '上传文档', en: 'Upload document' },
  'ontologyPlaceholder': { zh: '选择本体', en: 'Select an ontology' },

  'confirmedOnly': { zh: '条目须经确认才会被检索', en: 'Entries are searchable only after confirmation' },
  'confirmedOnlyDetail': {
    zh: '切分结果默认为待审核状态。确认时必须指定它解释的业务对象或它作为依据的规则——未锚定的文本无法回答「这段话凭什么支持这个结论」，因此不能作为判定依据。',
    en: 'Split results start as pending review. Confirming requires the business object this passage explains or the rule it supports: unanchored text cannot answer "what makes this passage support that conclusion", so it cannot serve as the basis for a decision.',
  },

  'documentsCard': { zh: '文档（{count}）', en: 'Documents ({count})' },
  'noDocuments': { zh: '尚未上传文档', en: 'No documents uploaded yet' },
  'colTitle': { zh: '标题', en: 'Title' },
  'colCounts': { zh: '条目', en: 'Entries' },
  'confirmedTag': { zh: '{count} 已确认', en: '{count} confirmed' },
  'pendingTag': { zh: '{count} 待审', en: '{count} pending' },

  'entriesTitle': { zh: '知识条目', en: 'Knowledge entries' },
  'pendingReviewTag': { zh: '{count} 待审核', en: '{count} pending review' },
  'noEntries': { zh: '尚无条目', en: 'No entries yet' },
  'colCitation': { zh: '引用', en: 'Citation' },
  'colContent': { zh: '内容', en: 'Content' },
  'colAnchor': { zh: '锚定', en: 'Anchor' },
  'unanchored': { zh: '未锚定', en: 'Unanchored' },
  'colStatus': { zh: '状态', en: 'Status' },
  'review': { zh: '审核', en: 'Review' },

  'loadOntologiesFailed': { zh: '加载本体列表失败', en: 'Could not load the ontology list' },
  'loadFailed': { zh: '加载知识库失败', en: 'Could not load the knowledge base' },
  'noFileSelected': { zh: '请选择文件', en: 'Choose a file first' },
  'splitDone': { zh: '已切分 {count} 个条目', en: 'Split into {count} entries' },
  'citationsLabel': { zh: '引用定位：', en: 'Citations: ' },
  'citationSeparator': { zh: '、', en: ', ' },
  'splitWarnings': { zh: '切分提示', en: 'Split warnings' },
  'uploadFailed': { zh: '上传失败', en: 'Upload failed' },
  'entryConfirmed': { zh: '条目已确认，可作为判定依据', en: 'Entry confirmed; it can now serve as the basis for a decision' },
  'entryUpdated': { zh: '条目已更新', en: 'Entry updated' },
  'actionFailed': { zh: '操作失败', en: 'The action failed' },

  'uploadTitle': { zh: '上传制度或合同文档', en: 'Upload a policy or contract document' },
  'uploadAndSplit': { zh: '上传并切分', en: 'Upload and split' },
  'fileLabel': { zh: '文件', en: 'File' },
  'fileHint': { zh: '支持 .docx 与 UTF-8 文本；按条款编号切分，保留可引用定位', en: 'Supports .docx and UTF-8 text; splits the document by clause number and keeps citable locators' },
  'draggerText': { zh: '点击或拖拽文件到此处', en: 'Click or drag a file here' },
  'documentTitleLabel': { zh: '文档标题', en: 'Document title' },
  'documentTitleHint': { zh: '留空则使用文件名；将作为引用出处显示', en: 'Leave blank to use the file name; the title is shown as the citation source' },
  'documentTitlePlaceholder': { zh: '售后政策', en: 'After-sales policy' },
  'defaultObjectLabel': { zh: '默认锚定业务对象（可选）', en: 'Default anchored business object (optional)' },
  'defaultObjectHint': { zh: '可在逐条审核时修正', en: 'You can correct it when you review each entry' },
  'defaultRuleLabel': { zh: '默认锚定规则（可选）', en: 'Default anchored rule (optional)' },

  'reviewTitle': { zh: '审核条目 {citation}', en: 'Review entry {citation}' },
  'reject': { zh: '驳回', en: 'Reject' },
  'cancel': { zh: '取消', en: 'Cancel' },
  'confirmAsEvidence': { zh: '确认为判定依据', en: 'Confirm as the basis for a decision' },
  'anchorObjectLabel': { zh: '锚定业务对象', en: 'Anchored business object' },
  'anchorObjectHint': { zh: '该条款解释哪个业务对象', en: 'Which business object this clause explains' },
  'anchorRuleLabel': { zh: '锚定规则', en: 'Anchored rule' },
  'anchorRuleHint': { zh: '该条款是哪条规则的文字依据', en: 'Which rule this clause supports' },
  'anchorRequired': { zh: '业务对象与规则至少填写一项', en: 'Fill in the business object, the rule, or both' },
};
