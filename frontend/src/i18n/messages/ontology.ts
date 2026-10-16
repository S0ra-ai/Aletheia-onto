/**
 * ontology —— 页面：pages/ontology/OntologyList.tsx、OntologyDetail.tsx、ModellingExtensions.tsx
 *
 * 两种语言都在这里，页面通过 `t('ontology.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const ontology: Record<string, MessageEntry> = {
  // Shared by the list and the detail page.
  'loadFailed': { zh: '读取本体失败', en: 'Could not load the ontology' },
  'name': { zh: '名称', en: 'Name' },
  'version': { zh: '版本', en: 'Version' },
  'status': { zh: '状态', en: 'Status' },
  'domain': { zh: '业务领域', en: 'Business domain' },
  'objects': { zh: '业务对象', en: 'Business objects' },

  // OntologyList.
  'title': { zh: '本体建模', en: 'Ontology modelling' },
  'listLoadFailed': { zh: '获取本体列表失败', en: 'Could not load the ontology list' },
  'importBlueprint': { zh: '导入行业蓝图', en: 'Import industry blueprint' },
  'createDraft': { zh: '生成本体草案', en: 'Generate ontology draft' },
  'view': { zh: '查看', en: 'View' },
  'edit': { zh: '编辑', en: 'Edit' },
  'emptyNoSource': {
    zh: '本体由扫描到的表结构生成，因此需要先接入一个数据源。请到「数据接入」登记业务库，扫描后再回来生成草案',
    en: 'An ontology is generated from scanned table structures, so a data source comes first. Register the database under "Data sources", scan it, then come back to generate a draft',
  },
  'emptyData': { zh: '暂无本体数据', en: 'No ontology data yet' },
  'goToDataSource': { zh: '去接入数据源', en: 'Go to data sources' },
  'createFirst': { zh: '生成第一个本体', en: 'Generate the first ontology' },
  'draftCreated': { zh: '本体草案生成成功', en: 'Ontology draft created' },
  'draftRebuilt': {
    zh: '草案已重新生成；原有 {summary} 已随之清除',
    en: 'The draft was rebuilt; the previous {summary} was cleared with it',
  },
  // What a rebuild removed, counted. The server sends the counts and a sentence of its own;
  // the sentence is Chinese, and it was being interpolated into the English one -- "the
  // previous 9 条规则、32 条映射 was cleared". So the console says it from the numbers, and
  // keeps the server's sentence only for a category it has no phrase for.
  // The `<category>.one` entries exist because English inflects and Chinese does not: the
  // Chinese text is the same sentence, repeated so the dictionary stays one shape. The
  // composer picks `.one` at a count of exactly one -- "the previous 1 workflows was cleared"
  // is the kind of English that reads as a machine wrote it.
  'discarded.rules': { zh: '{count} 条规则', en: '{count} rules' },
  'discarded.rules.one': { zh: '{count} 条规则', en: '{count} rule' },
  'discarded.mappings': { zh: '{count} 条映射', en: '{count} mappings' },
  'discarded.mappings.one': { zh: '{count} 条映射', en: '{count} mapping' },
  'discarded.relations': { zh: '{count} 条关系', en: '{count} relations' },
  'discarded.relations.one': { zh: '{count} 条关系', en: '{count} relation' },
  'discarded.workflows': { zh: '{count} 个工作流', en: '{count} workflows' },
  'discarded.workflows.one': { zh: '{count} 个工作流', en: '{count} workflow' },
  'discarded.documents': { zh: '{count} 份知识文档', en: '{count} knowledge documents' },
  'discarded.documents.one': { zh: '{count} 份知识文档', en: '{count} knowledge document' },
  'createFailed': { zh: '生成失败', en: 'Could not generate the draft' },
  'blueprintImported': { zh: '行业蓝图已导入', en: 'Industry blueprint imported' },
  'blueprintJsonInvalid': { zh: '蓝图 JSON 格式不正确', en: 'The blueprint JSON is not valid' },
  'blueprintImportFailed': { zh: '蓝图导入失败', en: 'Could not import the blueprint' },
  'rebuildWarning': { zh: '重新生成会清空原有草案', en: 'Regenerating clears the existing draft' },
  'rebuildDetail': {
    zh: '草案由当前扫描结果重建。若该数据源已有草案，挂在它上面的规则、映射、关系、工作流与知识文档会随之清除——生成后会告诉你清除了什么。',
    en: 'The draft is rebuilt from the current scan. If this data source already has a draft, the rules, mappings, relations, workflows and knowledge documents attached to it are cleared -- the result tells you what was removed.',
  },
  'selectDataSource': { zh: '选择数据源', en: 'Data source' },
  'dataSourceRequired': { zh: '请选择数据源', en: 'Choose a data source' },
  'dataSourcePlaceholder': { zh: '请选择要生成本体的数据源', en: 'Choose the data source to model' },
  'blueprint': { zh: '行业蓝图', en: 'Industry blueprint' },
  'blueprintPlaceholder': { zh: '自动推断行业蓝图', en: 'Infer the industry blueprint automatically' },
  'ontologyName': { zh: '本体名称', en: 'Ontology name' },
  'namePlaceholder': { zh: '留空将自动生成', en: 'Leave blank to generate one' },
  'domainPlaceholder': { zh: '例如：合同管理', en: 'e.g. Contract management' },
  'blueprintJson': { zh: '蓝图 JSON', en: 'Blueprint JSON' },
  'blueprintJsonRequired': { zh: '请粘贴行业蓝图 JSON', en: 'Paste the industry blueprint JSON' },
  'blueprintJsonPlaceholder': {
    zh: '{"id":"retail-order","name":"零售订单蓝图","domain":"零售订单","objectHints":{"order":"订单"},"attributeHints":{"order_no":"订单号"},"rules":[],"tableKeywords":["order"],"capabilityTags":["order-governance"]}',
    en: '{"id":"retail-order","name":"Retail order blueprint","domain":"Retail orders","objectHints":{"order":"Order"},"attributeHints":{"order_no":"Order number"},"rules":[],"tableKeywords":["order"],"capabilityTags":["order-governance"]}',
  },

  // OntologyDetail.
  'back': { zh: '返回', en: 'Back' },
  'detailTitle': { zh: '本体详情', en: 'Ontology detail' },
  'retry': { zh: '重试', en: 'Retry' },
  'notFound': { zh: '未找到本体数据', en: 'No ontology found' },
  'exportFailed': { zh: '导出失败', en: 'Could not export the ontology' },
  'published': { zh: '本体已发布：{name} v{version}', en: 'Ontology published: {name} v{version}' },
  'publishFailed': { zh: '发布失败', en: 'Could not publish' },
  'domainUnset': { zh: '未标注', en: 'Not set' },
  'createdAt': { zh: '创建时间', en: 'Created' },
  'code': { zh: '编码', en: 'Code' },
  'sourceTable': { zh: '来源表', en: 'Source table' },
  'description': { zh: '描述', en: 'Description' },
  'dataType': { zh: '数据类型', en: 'Data type' },
  'sourceColumn': { zh: '来源字段', en: 'Source column' },
  'type': { zh: '类型', en: 'Type' },
  'foreignKey': { zh: '外键', en: 'Foreign key' },
  'targetObject': { zh: '目标对象', en: 'Target object' },
  'targetAttribute': { zh: '目标属性', en: 'Target attribute' },
  'confidence': { zh: '置信度', en: 'Confidence' },
  'severity': { zh: '严重程度', en: 'Severity' },
  'enabled': { zh: '启用', en: 'Enabled' },
  'yes': { zh: '是', en: 'Yes' },
  'no': { zh: '否', en: 'No' },
  'expression': { zh: '表达式', en: 'Expression' },
  'gate': { zh: '门禁', en: 'Gate' },
  'passed': { zh: '通过', en: 'Passed' },
  'notPassed': { zh: '未通过', en: 'Not passed' },
  'gateLevel': { zh: '级别', en: 'Severity' },
  // The release gate, said by the console. The server sends each gate's code, whether it
  // passed, the facts behind it (`numbers`, `status`) and its own Chinese wording; the wording
  // is the fallback for a code this build does not know. A gate is the last thing a reader
  // looks at before publishing, so it is the worst place to leave a sentence in the wrong
  // language.
  'gate.ontology_status.label': { zh: '本体状态', en: 'Ontology status' },
  'gate.ontology_status.evidence': { zh: '当前状态 {status}。', en: 'Current status: {status}.' },
  'gate.ontology_status.remediation': {
    zh: '仅 draft、reviewing 或已发布版本可进入发布评估。',
    en: 'Only draft, reviewing or published versions can be assessed for release.',
  },
  'gate.business_objects.label': { zh: '业务对象', en: 'Business objects' },
  'gate.business_objects.evidence': { zh: '识别到 {objects} 个业务对象。', en: '{objects} business objects identified.' },
  'gate.business_objects.remediation': {
    zh: '先基于数据源扫描结果生成本体草案。',
    en: 'Generate an ontology draft from the scan results first.',
  },
  'gate.source_bindings.label': { zh: '来源绑定', en: 'Source bindings' },
  'gate.source_bindings.evidence': {
    zh: '{bound}/{objects} 个对象绑定来源表。',
    en: '{bound} of {objects} objects are bound to a source table.',
  },
  'gate.source_bindings.remediation': {
    zh: '为每个业务对象绑定传统系统来源表。',
    en: 'Bind every business object to its table in the legacy system.',
  },
  'gate.primary_keys.label': { zh: '实例标识', en: 'Instance identity' },
  'gate.primary_keys.evidence': {
    zh: '{withKey}/{objects} 个对象具备主键。',
    en: '{withKey} of {objects} objects have a primary key.',
  },
  'gate.primary_keys.remediation': {
    zh: '为缺少主键的来源表配置稳定实例标识。',
    en: 'Give the source tables without a primary key a stable instance identity.',
  },
  'gate.pending_mappings.label': { zh: '映射审核', en: 'Mapping review' },
  'gate.pending_mappings.evidence': { zh: '待审核映射 {pending} 条。', en: '{pending} mappings await review.' },
  'gate.pending_mappings.remediation': {
    zh: '发布前必须完成全部语义映射审核。',
    en: 'Every semantic mapping has to be reviewed before release.',
  },
  'gate.confirmed_mappings.label': { zh: '确认映射', en: 'Confirmed mappings' },
  'gate.confirmed_mappings.evidence': { zh: '已确认映射 {confirmed} 条。', en: '{confirmed} mappings confirmed.' },
  'gate.confirmed_mappings.remediation': {
    zh: '至少确认关键对象和关键字段映射。',
    en: 'Confirm at least the key objects and the key fields.',
  },
  'gate.published_rules.label': { zh: '业务规则', en: 'Business rules' },
  'gate.published_rules.evidence': { zh: '已发布规则 {published} 条。', en: '{published} published rules.' },
  'gate.published_rules.remediation': {
    zh: '至少为核心业务对象配置一组发布态规则。',
    en: 'Configure at least one set of published rules for the core business objects.',
  },
  'gate.object_rule_coverage.label': { zh: '对象规则覆盖', en: 'Rule coverage' },
  'gate.object_rule_coverage.evidence': {
    zh: '{withRules}/{objects} 个对象具备规则。',
    en: '{withRules} of {objects} objects have rules.',
  },
  'gate.object_rule_coverage.remediation': {
    zh: '为缺少规则的业务对象补充校验、风险或权限规则。',
    en: 'Add validation, risk or permission rules to the objects that have none.',
  },
  'gate.axioms_satisfied.label': { zh: '公理一致性', en: 'Axiom consistency' },
  'gate.axioms_satisfied.evidence.satisfied': {
    zh: '已声明 {declared} 条公理，全部成立。',
    en: 'All {declared} declared axioms hold.',
  },
  'gate.axioms_satisfied.remediation': {
    zh: '修正模型声明，或移除已不适用的公理。公理描述模型本身，不针对单个实例。',
    en: 'Correct the model, or remove the axioms that no longer apply. An axiom describes the model itself, not an instance.',
  },
  'gate.data_source.readiness.label': { zh: '数据源 {id} 接入准备度', en: 'Data source {id}: readiness' },
  'gate.data_source.readiness.evidence': {
    zh: '准备度 {score} 分，状态 {status}。',
    en: 'Score {score}, status {status}.',
  },
  'gate.data_source.readiness.remediation': {
    zh: '完成元数据扫描、实例定位、映射治理等阻断项。',
    en: 'Clear the blockers: metadata scan, instance identity, mapping governance.',
  },
  'gate.data_source.coverage.label': { zh: '数据源 {id} 语义覆盖', en: 'Data source {id}: semantic coverage' },
  'gate.data_source.coverage.evidence': { zh: '覆盖度 {score} 分，状态 {status}。', en: 'Score {score}, status {status}.' },
  'gate.data_source.coverage.remediation': {
    zh: '补齐对象映射、业务规则和语义 API。',
    en: 'Fill in the object mappings, business rules and semantic APIs.',
  },
  'gate.data_source.schema_drift.label': { zh: '数据源 {id} 结构漂移', en: 'Data source {id}: schema drift' },
  'gate.data_source.schema_drift.evidence': { zh: '结构漂移状态 {status}。', en: 'Drift status: {status}.' },
  'gate.data_source.schema_drift.remediation': {
    zh: '发布前先处理结构漂移并重新确认受影响语义资产。',
    en: 'Resolve the drift and re-confirm the affected semantic assets before releasing.',
  },
  'gate.allPassed': {
    zh: '发布门禁全部通过，可按治理流程发布本体版本。',
    en: 'Every release gate passed. The ontology can be published through the governance flow.',
  },
  'evidence': { zh: '证据', en: 'Evidence' },
  'remediation': { zh: '修复动作', en: 'Remediation' },
  'releaseReadiness': { zh: '发布就绪度', en: 'Release readiness' },
  'dataSources': { zh: '数据源', en: 'Data sources' },
  'blockers': { zh: '阻断', en: 'Blockers' },
  'warnings': { zh: '预警', en: 'Warnings' },
  'confirmedMappings': { zh: '确认映射', en: 'Confirmed mappings' },
  'pendingMappings': { zh: '待审映射', en: 'Pending mappings' },
  'publishedRules': { zh: '发布规则', en: 'Published rules' },
  'nextActions': { zh: '下一步动作', en: 'Next actions' },
  'objectsTab': { zh: '业务对象 ({count})', en: 'Business objects ({count})' },
  'attributesTab': { zh: '业务属性 ({count})', en: 'Business attributes ({count})' },
  'relationsTab': { zh: '业务关系 ({count})', en: 'Business relations ({count})' },
  'mappingsTab': { zh: '语义映射 ({count})', en: 'Semantic mappings ({count})' },
  'rulesTab': { zh: '业务规则 ({count})', en: 'Business rules ({count})' },
  'releaseGatesTab': { zh: '发布门禁', en: 'Release gates' },
  'extensionsTab': { zh: '建模扩展', en: 'Modelling extensions' },
  'publish': { zh: '发布本体', en: 'Publish ontology' },
  'publishConfirm': {
    zh: '发布后该版本不可修改，只能派生新版本。确认发布？',
    en: 'A published version cannot be modified, only derived from. Publish it?',
  },
  'publishOk': { zh: '发布', en: 'Publish' },
  'isPublished': { zh: '已发布', en: 'Published' },
  'blockerHintPrefix': {
    zh: '还有 {count} 项阻断项，先按上面的「下一步动作」处理；需要强行发布时用命令行 ',
    en: '{count} blockers remain; work through the "next actions" above first. To force a release from a terminal, run ',
  },
  'blockerHintSuffix': {
    zh: '，它会把这处覆盖写进审计。',
    en: ', which records this override in the audit log.',
  },
  'publishNote': {
    zh: '发布后该版本不可修改：改动要派生新版本，判定仍能追溯到发布时的模型。',
    en: 'A published version cannot be modified: to make changes, derive a new version, so decisions stay traceable to the model as published.',
  },

  // ModellingExtensions.
  'eventTypes': { zh: '事件类型', en: 'Event types' },
  'declareEventType': { zh: '声明事件类型', en: 'Declare event type' },
  'eventTypesLoadFailed': { zh: '读取事件类型失败', en: 'Could not load event types' },
  'eventTypeDeclared': { zh: '事件类型已声明', en: 'Event type declared' },
  'declareFailed': { zh: '声明事件类型失败', en: 'Could not declare the event type' },
  'eventTypesIntro': {
    zh: '事件必须声明类型后才能记录：不存在「先记下来，以后再分类」——«驳回»、«拒绝» 与 «rejected» 一旦各记各的，历史就不再可检索。记录某个实例的事件在「对象浏览」的实例解释里做。',
    en: 'An event must be declared before it can be recorded: there is no "write it down now, classify it later" -- once the same meaning is recorded under different type codes, the history stops being searchable. To record an event for a single instance, use the instance explanation under "Business objects".',
  },
  'readOnlyTitle': { zh: '本体已发布或正在审核，不能修改事件定义', en: 'The ontology is published or under review, so event declarations cannot change' },
  'readOnlyDetail': {
    zh: '这是刻意设计：已发布的模型不应在无人察觉时改变含义。要改请先派生新版本。',
    en: 'This is deliberate: a published model should not change meaning unnoticed. Derive a new version to make changes.',
  },
  'selectObject': { zh: '选择业务对象', en: 'Select a business object' },
  'declaredCount': { zh: '共声明 {total} 种，其中本对象 {here} 种', en: '{total} declared in total, {here} for this object' },
  'event': { zh: '事件', en: 'Event' },
  'category': { zh: '类别', en: 'Category' },
  'payloadFields': { zh: '载荷字段', en: 'Payload fields' },
  'noExpectedFields': { zh: '未声明预期字段', en: 'No expected fields declared' },
  'note': { zh: '说明', en: 'Description' },
  'noEventTypes': { zh: '该对象尚未声明任何事件类型，因此无法记录事件', en: 'This object has no event types declared, so events cannot be recorded' },
  'declareFor': { zh: '为 {code} 声明事件类型', en: 'Declare an event type for {code}' },
  'eventCode': { zh: '事件编码', en: 'Event code' },
  'eventCodeRequired': { zh: '请填写事件编码', en: 'Enter an event code' },
  'identifierRule': {
    zh: '需为合法标识符：字母或下划线开头，只含字母、数字、下划线',
    en: 'Must be a valid identifier: start with a letter or an underscore, containing only letters, digits and underscores',
  },
  'identifierHint': {
    zh: '会进入规则表达式与查询条件，因此限制为标识符。已存在的编码会被更新而非重复创建。',
    en: 'It appears in rule expressions and query conditions, so it is restricted to an identifier. An existing code is updated rather than created twice.',
  },
  'nameRequired': { zh: '请填写名称', en: 'Enter a name' },
  'eventNamePlaceholder': { zh: '合同签订', en: 'Contract signed' },
  'payloadHint': {
    zh: '可选，逗号分隔。它是对生产方的期望而非校验：载荷缺少这些字段时平台会在事件上标注，而不是拒绝写入。',
    en: 'Optional, comma-separated. It is an expectation for producers, not a validation: a payload missing these fields is flagged on the event rather than refused.',
  },
  'eventDescriptionPlaceholder': { zh: '这个事件代表业务上发生了什么', en: 'What this event means in the business' },
};
