/**
 * graph —— 页面：pages/graph/OntologyGraph.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('graph.…')`。
 */
import type { MessageEntry } from './shell';

export const graph: Record<string, MessageEntry> = {
  'title': { zh: '知识图谱预览', en: 'Ontology graph preview' },
  'subtitle': { zh: '业务对象与关系的图结构，用于发现建模缺口', en: 'The graph of business objects and their relations, for spotting modelling gaps' },
  'issuesOnly': { zh: '只看有问题的对象', en: 'Only objects with problems' },
  'selectOntology': { zh: '选择本体', en: 'Select an ontology' },
  'publishedSuffix': { zh: '（已发布）', en: ' (published)' },

  'loadOntologiesFailed': { zh: '加载本体列表失败', en: 'Could not load the ontology list' },
  'loadGraphFailed': { zh: '加载知识图谱失败', en: 'Could not load the ontology graph' },
  'empty': { zh: '该本体尚无业务对象。请先接入数据源并生成本体草案。', en: 'This ontology has no business objects yet. Connect a data source and generate a draft ontology first.' },
  'ariaLabel': {
    zh: '{name} 的业务对象关系图，共 {objects} 个对象、{relations} 条关系',
    en: 'Graph of the business objects of {name}: {objects} objects and {relations} relations',
  },

  'legendNormal': { zh: '正常', en: 'Healthy' },
  'legendNoRules': { zh: '无规则（不产出判定）', en: 'No rules (producing no decisions)' },
  'legendUnbound': { zh: '未绑定来源表', en: 'Not bound to a source table' },
  'legendHint': { zh: '圆圈大小表示关联数量 · 悬停显示外键', en: 'Circle size shows the number of connections · hover a node to see its foreign key' },

  'structureTitle': { zh: '图结构', en: 'Graph structure' },
  'statObjects': { zh: '业务对象', en: 'Business objects' },
  'statRelations': { zh: '关系', en: 'Relations' },
  'statDomain': { zh: '领域', en: 'Domain' },
  'statVersion': { zh: '版本', en: 'Version' },

  'nodeCode': { zh: '编码', en: 'Code' },
  'nodeSourceTable': { zh: '来源表', en: 'Source table' },
  'nodeUnbound': { zh: '未绑定', en: 'Not bound' },
  'nodeAttributes': { zh: '属性', en: 'Attributes' },
  'nodeRules': { zh: '规则', en: 'Rules' },
  'nodeDegree': { zh: '关联', en: 'Connections' },

  'gapsTitle': { zh: '建模缺口', en: 'Modelling gaps' },
  'noGaps': { zh: '未发现孤立对象或缺失规则。', en: 'No isolated objects or missing rules.' },
  'isolatedTitle': { zh: '孤立对象（无任何关联）', en: 'Isolated objects (no connections)' },
  'noRulesTitle': { zh: '无规则对象（不产出判定）', en: 'Objects without rules (producing no decisions)' },
  'limitationTitle': { zh: '关系表达力限制', en: 'Limits of relation expressiveness' },
};
