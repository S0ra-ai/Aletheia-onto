/**
 * mapping —— 页面：pages/mapping/MappingList.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('mapping.…')`。
 */
import type { MessageEntry } from './shell';

export const mapping: Record<string, MessageEntry> = {
  'title': { zh: '语义映射', en: 'Semantic mappings' },

  'ontologyLabel': { zh: '选择本体：', en: 'Ontology:' },
  'ontologyPlaceholder': { zh: '请选择本体', en: 'Select an ontology' },
  'ontologyOption': { zh: '{name} v{version}（{status}）', en: '{name} v{version} ({status})' },

  'bulkConfirm': { zh: '批量确认', en: 'Bulk confirm' },
  'bulkReject': { zh: '批量拒绝', en: 'Bulk reject' },
  'bulkConfirmDone': { zh: '已批量确认', en: 'Confirmed in bulk' },
  'bulkRejectDone': { zh: '已批量拒绝', en: 'Rejected in bulk' },

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
  'noMappings': { zh: '该本体没有语义映射', en: 'This ontology has no semantic mappings' },
};
