/**
 * workflow —— 页面：pages/workflow/WorkflowManager.tsx
 *
 * 两种语言都在这里，页面通过 `t('workflow.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const workflow: Record<string, MessageEntry> = {
  'title': { zh: '工作流管理', en: 'Workflow management' },
  'createButton': { zh: '新建工作流', en: 'New workflow' },
  'empty': { zh: '还没有工作流。工作流为一个业务对象定义状态与流转条件，流转时的守卫表达式会在规则沙箱中求值。', en: 'No workflows yet. A workflow defines the states and transition conditions of a business object; the guards on a transition are evaluated in the rule sandbox.' },

  // The table, the detail dialog and the create form share these labels.
  'name': { zh: '名称', en: 'Name' },
  'object': { zh: '业务对象', en: 'Business object' },
  'ontology': { zh: '本体', en: 'Ontology' },
  'initialState': { zh: '初始状态', en: 'Initial state' },
  'status': { zh: '状态', en: 'Status' },

  'details': { zh: '详情', en: 'Details' },
  'transition': { zh: '转移', en: 'Transition' },
  'history': { zh: '历史', en: 'History' },
  'deleteConfirm': { zh: '确认删除？', en: 'Delete this workflow?' },

  'loadFailed': { zh: '加载工作流失败', en: 'Could not load the workflows' },
  'loadOntologiesFailed': { zh: '加载本体列表失败', en: 'Could not load the ontology list' },
  'createSuccess': { zh: '工作流创建成功', en: 'Workflow created' },
  'createFailed': { zh: '创建失败', en: 'Could not create the workflow' },
  'deleteSuccess': { zh: '已删除', en: 'Deleted' },
  'deleteFailed': { zh: '删除失败', en: 'Could not delete the workflow' },
  'loadDetailFailed': { zh: '加载详情失败', en: 'Could not load the details' },
  'transitionSuccess': { zh: '状态转移成功', en: 'Transition applied' },
  'transitionFailed': { zh: '转移失败', en: 'The transition failed' },

  // Create form.
  'selectOntology': { zh: '选择本体', en: 'Select an ontology' },
  'objectCodeLabel': { zh: '业务对象编码', en: 'Business object code' },
  'objectCodePlaceholder': { zh: '如 contract, equipment', en: 'e.g. contract, equipment' },
  'nameLabel': { zh: '工作流名称', en: 'Workflow name' },
  'namePlaceholder': { zh: '合同审批流程', en: 'Contract approval flow' },
  'description': { zh: '描述', en: 'Description' },
  'optional': { zh: '可选', en: 'Optional' },

  // Detail dialog.
  'detailTitle': { zh: '工作流详情', en: 'Workflow details' },
  'states': { zh: '状态节点', en: 'States' },
  'terminal': { zh: ' [终态]', en: ' [terminal]' },
  'transitions': { zh: '转移规则', en: 'Transition rules' },
  'action': { zh: '动作', en: 'Action' },
  'from': { zh: '来源', en: 'From' },
  'to': { zh: '目标', en: 'To' },
  'requiresReview': { zh: '需审核', en: 'Needs review' },
  'yes': { zh: '是', en: 'Yes' },

  // Instance transition dialog.
  'transitionTitle': { zh: '实例状态转移', en: 'Instance state transition' },
  'instanceIdPlaceholder': { zh: '输入实例 ID', en: 'Enter an instance ID' },
  'loadActionButton': { zh: '查询可用动作', en: 'Load available actions' },
  'loadActionsFailed': { zh: '读取可执行动作失败', en: 'Could not read the available actions' },
  'noActions': { zh: '该实例暂无可用动作', en: 'No actions are available for this instance' },

  // History dialog.
  'historyTitle': { zh: '工作流历史', en: 'Workflow history' },
  'queryHistory': { zh: '查询历史', en: 'Load history' },
  'historyPrompt': { zh: '输入要查看的实例 ID。流转历史属于某个实例，不是一个工作流的属性。', en: 'Enter the instance ID to inspect. Transition history belongs to an instance, not to a workflow.' },
  'loadHistoryFailed': { zh: '读取流转历史失败', en: 'Could not read the transition history' },
  'initial': { zh: '初始', en: 'Initial' },
  'noHistory': { zh: '暂无历史记录', en: 'No history' },
};
