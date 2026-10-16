/**
 * mapping —— 页面：pages/mapping/MappingList.tsx
 *
 * 两种语言都在这里，页面通过 `t('mapping.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const mapping: Record<string, MessageEntry> = {
  'title': { zh: '语义映射', en: 'Semantic mappings' },

  'ontologyLabel': { zh: '选择本体：', en: 'Ontology:' },
  'ontologyPlaceholder': { zh: '请选择本体', en: 'Select an ontology' },
  'ontologyOption': { zh: '{name} v{version}（{status}）', en: '{name} v{version} ({status})' },

  'bulkConfirm': { zh: '批量确认', en: 'Bulk confirm' },
  'bulkReject': { zh: '批量拒绝', en: 'Bulk reject' },
  // The count is in the message because paging makes the button ambiguous: it reviews every
  // *pending* mapping of the ontology, not the rows on the visible page.
  'bulkConfirmDone': { zh: '已确认 {count} 条待审核映射', en: 'Confirmed {count} pending mappings' },
  'bulkRejectDone': { zh: '已拒绝 {count} 条待审核映射', en: 'Rejected {count} pending mappings' },
  'totalRows': { zh: '共 {count} 条', en: '{count} total' },

  'colMappingType': { zh: '映射类型', en: 'Mapping type' },
  'colSourceTable': { zh: '来源表', en: 'Source table' },
  'colSourceColumn': { zh: '来源字段', en: 'Source column' },
  'colTargetObject': { zh: '目标对象', en: 'Target object' },
  'colTargetAttribute': { zh: '目标属性', en: 'Target attribute' },
  'colConfidence': { zh: '置信度', en: 'Confidence' },
  'colStatus': { zh: '状态', en: 'Status' },
  'colReviewer': { zh: '审核人', en: 'Reviewer' },

  'loadOntologiesFailed': { zh: '获取本体列表失败', en: 'Could not load the ontology list' },
  'loadMappingsFailed': { zh: '获取语义映射失败', en: 'Could not load the semantic mappings' },
  'reviewFailed': { zh: '审核失败', en: 'Review failed' },
  'retry': { zh: '重试', en: 'Retry' },
  'noOntologies': { zh: '没有可审核的本体', en: 'No ontologies to review' },
  // Mapping is the *destination* of a flow, so an empty selector here is not a state to
  // describe but a step to name. The page used to be a dead end on a fresh install: no
  // ontologies, no rows, and nothing saying where they come from.
  'noOntologiesHint': {
    zh: '映射依附于本体，本体由扫描到的表结构生成。请先到「数据接入」登记并扫描业务库，再回「本体建模」生成草案——之后待审核的映射会出现在这里。',
    en: 'Mappings hang off an ontology, and an ontology comes from a scanned schema. Register and scan the source under Data sources, generate a draft under Modelling, and the mappings to review will appear here.',
  },
  'noMappings': { zh: '该本体没有语义映射', en: 'This ontology has no semantic mappings' },
};
