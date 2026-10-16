/**
 * objects —— 页面：pages/objects/ObjectBrowser.tsx、InstanceDrawer.tsx
 *
 * 两种语言都在这里，页面通过 `t('objects.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const objects: Record<string, MessageEntry> = {
  // ObjectBrowser —— the page itself.
  'title': { zh: '业务对象浏览', en: 'Business objects' },
  'subtitle': {
    zh: '按本体中声明的业务对象查看实例。数据经实例解析器读取，并按你的角色做行级过滤，与直接浏览来源表不是同一件事。',
    en: 'Browse instances of the business objects declared in an ontology. Data is read through the instance resolver and row-filtered for your role, which is not the same as browsing the source tables directly.',
  },

  // ObjectBrowser —— what could not be read.
  'loadOntologiesFailed': { zh: '获取本体列表失败', en: 'Could not load the ontology list' },
  'loadOntologyDetailFailed': { zh: '读取本体详情失败', en: 'Could not load the ontology details' },
  'loadInstancesFailed': { zh: '读取业务对象实例失败', en: 'Could not load the business object instances' },
  'loadFailed': { zh: '读取失败', en: 'Could not load' },

  // ObjectBrowser —— the two selectors and the resolver line.
  'selectOntology': { zh: '选择本体', en: 'Select an ontology' },
  'selectObject': { zh: '选择业务对象', en: 'Select a business object' },
  // A display name and its code, e.g. 合同（contract）. The code is data and stays as it is.
  'nameWithCode': { zh: '{name}（{code}）', en: '{name} ({code})' },
  'sourceLine': { zh: '来源：{tables}', en: 'Source: {tables}' },
  // How a list of table names reads inside the sentence above.
  'listSeparator': { zh: '、', en: ', ' },

  // ObjectBrowser —— the table.
  'instanceColumn': { zh: '实例', en: 'Instance' },
  'actionsColumn': { zh: '操作', en: 'Actions' },
  'explainAction': { zh: '解释', en: 'Explain' },

  // ObjectBrowser —— row-level filtering, applied or broken.
  'rowFilterApplied': { zh: '结果已按你的角色做行级过滤', en: 'Results are row-filtered for your role' },
  'rowFilterAppliedDescription': {
    zh: '没有看到某条实例，可能是它不在你的可见范围内，而不是它不存在。',
    en: 'A missing instance may be beyond what you are allowed to see rather than absent.',
  },
  'rowFilterError': {
    zh: '行级过滤表达式无法求值，因此没有返回任何实例',
    en: 'The row filter could not be evaluated, so no instances were returned',
  },
  'rowFilterErrorDescription': {
    zh: '这不是「没有数据」：平台为避免越权披露，在过滤条件无法判断时按不可见处理。请修正该角色在本对象上的过滤表达式后重试。',
    en: 'This is not "no data": to avoid disclosing more than allowed, the platform treats the data as not visible when the filter cannot be evaluated. Fix the filter expression this role has on this object and try again.',
  },

  // ObjectBrowser —— the empty states.
  'emptyNoOntologies': {
    zh: '还没有可浏览的本体。请先到「数据接入」登记并扫描业务库，再回「本体建模」生成本体草案',
    en: 'No ontologies to browse yet. Register and scan a business database under "Data sources", then go back to "Modelling" to draft the ontology',
  },
  'emptySelectOntologyAndObject': { zh: '请选择本体与业务对象', en: 'Select an ontology and a business object' },
  'emptyNoVisibleInstances': { zh: '按当前角色的可见范围内没有实例', en: 'No instances fall within the visible range for your current role' },
  'emptyNoInstances': { zh: '该对象没有实例', en: 'This object has no instances' },

  // InstanceDrawer —— what could not be read or written.
  'loadExplainFailed': { zh: '读取实例解释失败', en: 'Could not load the instance explanation' },
  'loadEventsFailed': { zh: '读取事件历史失败', en: 'Could not load the event history' },
  'loadVersionsFailed': { zh: '读取取值沿革失败', en: 'Could not load the value history' },
  'payloadInvalidJson': { zh: '载荷必须是合法 JSON', en: 'The payload must be valid JSON' },
  'eventRecorded': { zh: '事件已记录', en: 'Event recorded' },
  'recordEventFailed': { zh: '记录事件失败', en: 'Could not record the event' },

  // InstanceDrawer —— the header summary.
  'ontologyLabel': { zh: '本体', en: 'Ontology' },
  'objectLabel': { zh: '业务对象', en: 'Business object' },
  'sourceTableLabel': { zh: '来源表', en: 'Source table' },
  'primaryKeyLabel': { zh: '主键', en: 'Primary key' },
  'typeHierarchyLabel': { zh: '类型层级', en: 'Type hierarchy' },
  'ancestorNote': { zh: '这些类型的规则同样适用于本实例', en: 'Rules on these types apply to this instance too' },

  // InstanceDrawer —— attributes and their sources.
  'attributesHeading': { zh: '属性与来源', en: 'Attributes and sources' },
  'attributesHint': {
    zh: '每个值都列出它读自哪一列。列与属性对不上时，问题出在映射上而不是数据上。',
    en: 'Every value names the column it was read from. When a column does not match its attribute, the fault lies in the mapping rather than the data.',
  },
  'attributeColumn': { zh: '属性', en: 'Attribute' },
  'sourceColumn': { zh: '来源', en: 'Source' },
  'valueColumn': { zh: '值', en: 'Value' },
  'unitColumn': { zh: '单位', en: 'Unit' },
  'tagDerived': { zh: '计算', en: 'Computed' },
  'tagFromHistory': { zh: '历史', en: 'From history' },
  'derivedFromExpression': { zh: '由表达式计算', en: 'Computed from an expression' },
  'computeFailed': { zh: '无法计算：{error}', en: 'Could not compute: {error}' },
  'emptyValue': { zh: '空值', en: 'No value' },

  // InstanceDrawer —— aggregates. The paragraph is split around its bold middle phrase:
  // 'aggregatesHint' runs before it, 'aggregatesHintEmphasis' is the bold part, and
  // 'aggregatesHintEnd' is the full stop that follows it in the page.
  'aggregatesHeading': { zh: '聚合值', en: 'Aggregates' },
  'aggregatesHint': {
    zh: '规则可以直接按名称引用这些值。它们不属于本行的任何属性，而是对其他行的一次查询，所以单独列出——',
    en: 'Rules can reference these values by name. They are not attributes of this row but a query over other rows, so they are listed separately — ',
  },
  'aggregatesHintEmphasis': { zh: '判定引用了某个聚合值，这里就必须看得到它', en: 'if a decision references an aggregate, it has to be visible here' },
  'aggregatesHintEnd': { zh: '。', en: '.' },
  'nameColumn': { zh: '名称', en: 'Name' },
  'definitionColumn': { zh: '定义', en: 'Definition' },
  'truncatedTag': { zh: '已达取数上限', en: 'Row limit reached' },
  'rowCountColumn': { zh: '行数', en: 'Rows' },

  // InstanceDrawer —— the event history.
  'eventsHeading': { zh: '事件历史', en: 'Event history' },
  'recordEventButton': { zh: '记录事件', en: 'Record an event' },
  'eventsHint': {
    zh: '解释里只带最近 20 条：解释是交互阅读的，而完整历史在这里。',
    en: 'The explanation carries only the 20 most recent events: it is read interactively, while the full history lives here.',
  },
  // The leading space is deliberate: this sentence is appended right after the hint above.
  'eventsNoTypesHint': {
    zh: ' 该对象尚未声明事件类型，因此无法记录事件——请先到本体详情的「建模扩展」中声明。',
    en: ' This object has no declared event types, so events cannot be recorded — declare them first under "Modelling extensions" on the ontology detail.',
  },
  'emptyNoEvents': {
    zh: '该实例没有已记录事件（事件类型需先声明，否则历史无法按类型检索）',
    en: 'This instance has no recorded events (event types must be declared first, or the history cannot be searched by type)',
  },
  'occurredAtColumn': { zh: '时间（UTC）', en: 'Time (UTC)' },
  'eventColumn': { zh: '事件', en: 'Event' },
  'categoryColumn': { zh: '类别', en: 'Category' },
  'actorColumn': { zh: '操作者', en: 'Actor' },
  'payloadColumn': { zh: '载荷', en: 'Payload' },

  // InstanceDrawer —— the value history. Split around its bold phrase, like the aggregates.
  'versionsHeading': { zh: '取值沿革', en: 'Value history' },
  'versionsHint': {
    zh: '判定可以按过去某一时刻产出，所以「上个月的金额是多少」是复核旧结论时绕不开的问题。',
    en: 'A decision can be produced as of a past moment, so "what was the amount last month" cannot be avoided when re-checking an old conclusion.',
  },
  'versionsHintEmphasis': { zh: '没记录过取值的属性不会出现在这里', en: ' Attributes whose values were never recorded do not appear here' },
  'versionsHintTail': {
    zh: '——这不是数据缺失，是沿革从未被记录。',
    en: ' — this is not missing data; the history was simply never recorded.',
  },
  'emptyNoVersions': { zh: '该实例没有任何已记录的取值版本', en: 'This instance has no recorded value versions' },
  'versionValueColumn': { zh: '取值', en: 'Value' },
  'validityColumn': { zh: '生效区间', en: 'Validity period' },
  'toPresent': { zh: '至今', en: 'present' },
  'recordedAtColumn': { zh: '记录时间（UTC）', en: 'Recorded at (UTC)' },
  'recordedByColumn': { zh: '记录人', en: 'Recorded by' },

  // InstanceDrawer —— the record-event dialog.
  'recordEventTitle': { zh: '记录事件：{object} / {instance}', en: 'Record an event: {object} / {instance}' },
  'recordEventNote': { zh: '记录事件不会触发任何动作', en: 'Recording an event triggers nothing' },
  'recordEventNoteDescription': {
    zh: '它只把「发生了什么」写进历史，因此它是可复核的凭据，而不是一条自动化指令。',
    en: 'It only writes what happened into the history, so it is a checkable record rather than an automated instruction.',
  },
  'selectEventRequired': { zh: '请选择事件', en: 'Select an event' },
  'selectEventType': { zh: '选择已声明的事件类型', en: 'Select a declared event type' },
  'eventTypeOption': { zh: '{name}（{category}）', en: '{name} ({category})' },
  'occurredAtLabel': { zh: '发生时间', en: 'Occurred at' },
  'occurredAtHint': {
    zh: '留空表示「现在」。历史是补记的常见情形，因此这里可以填过去的时间。',
    en: 'Leave it empty to mean "now". Backfilled history is common, so a past time is allowed here.',
  },
  'payloadHint': {
    zh: '可选，JSON 对象。与已声明的载荷字段不一致时平台会在事件上标注，而不是拒绝写入。',
    en: 'Optional, a JSON object. When it does not match the declared payload fields the platform flags the event instead of refusing the write.',
  },
  'payloadPlaceholder': { zh: '{"party": "甲方"}', en: '{"party": "Party A"}' },
};
