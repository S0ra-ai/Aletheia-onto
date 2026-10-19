/**
 * errors —— 组件：error-boundary/ErrorBoundary.tsx
 *
 * 两种语言都在这里，页面通过 `t('errors.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const errors: Record<string, MessageEntry> = {
  'title': { zh: '页面加载失败', en: 'This page could not be loaded' },
  'unknown': { zh: '发生未知错误，请刷新页面重试', en: 'Something went wrong. Reload the page to try again.' },
  'unknownShort': { zh: '发生未知错误', en: 'Something went wrong.' },

  'reload': { zh: '刷新页面', en: 'Reload' },
  'retry': { zh: '刷新重试', en: 'Reload and retry' },

  // Failures the HTTP client raises itself, before any page or the server has a say. They
  // are looked up by `translateNow` rather than by `t()`, because the interceptor runs
  // outside the component tree -- see `i18n/translate.ts`. Both were hard-coded Chinese
  // here, so in English mode the session-expiry and permission messages were the two
  // failures still reported in the other language.
  'sessionExpired': { zh: '登录已失效，请重新登录。', en: 'Your session has expired. Sign in again.' },
  // The last resort for a 403 that carries no recognisable code and no sentence -- a reverse
  // proxy answering on the platform’s behalf, say. A real refusal from this platform is named
  // (`errors.api.forbidden`, which says whose role and which capability), so this is not the
  // path a reader normally meets.
  'forbidden': { zh: '当前角色无权执行该操作。', en: 'Your role is not allowed to do that.' },

  // The refusals the server sends, keyed by the code beside its sentence
  // (`backend/ontology_platform/error_codes.py`).
  //
  // The server’s sentence travels with every failure and stays Chinese -- the CLI prints it,
  // and so do clients that do not know these codes. The console says the one below instead
  // when it recognises the code, and falls back to the server’s sentence when it does not. So
  // a missing key here is not a crash and not a blank: it is a Chinese line in an English
  // dialog, which is why `tests/test_error_codes.py` fails on one.
  //
  // The placeholders are the facts the server captured while identifying its own sentence, and
  // they have to match that side exactly -- a `{id}` here against `{ontologyId}` there renders
  // a literal brace to the reader.
  'api.login_failed': { zh: '用户名或密码不正确。', en: 'That username and password do not match.' },
  'api.account_disabled': { zh: '该账号已被禁用，请联系平台管理员。', en: 'That account is disabled. Contact a platform administrator.' },
  'api.current_password_wrong': { zh: '当前密码不正确。', en: 'That is not your current password.' },
  'api.password_too_short': { zh: '密码长度至少 8 位。', en: 'A password needs at least 8 characters.' },
  'api.username_required': { zh: '用户名不能为空。', en: 'A username is required.' },
  'api.unauthenticated': { zh: '缺少访问令牌，请先登录。', en: 'No access token was sent. Sign in first.' },
  'api.forbidden': {
    zh: '角色 {roleCode} 缺少所需权限 {capability}，无法执行该操作。',
    en: 'The role {roleCode} does not have {capability}, so it cannot do that.',
  },
  'api.token_invalid': { zh: '访问令牌无效。', en: 'That access token is not valid.' },
  'api.token_expired': { zh: '访问令牌已过期，请重新登录。', en: 'Your access token has expired. Sign in again.' },
  'api.token_revoked': { zh: '访问令牌已失效，请重新登录。', en: 'Your access token is no longer valid. Sign in again.' },
  'api.user_not_found': { zh: '用户 {username} 不存在。', en: 'There is no user named {username}.' },
  'api.user_status_invalid': { zh: '用户状态只能是 active 或 disabled。', en: 'A user’s status is either active or disabled.' },

  'api.ontology_not_found': { zh: '本体 {ontologyId} 不存在。', en: 'There is no ontology with id {ontologyId}.' },
  'api.data_source_not_found': { zh: '数据源 {dataSourceId} 不存在。', en: 'There is no data source with id {dataSourceId}.' },
  'api.object_not_found': { zh: '业务对象 {objectCode} 不存在。', en: 'There is no business object named {objectCode}.' },
  'api.instance_not_found': { zh: '{objectCode} 的实例 {instanceId} 不存在。', en: '{objectCode} has no instance {instanceId}.' },
  'api.rule_not_found': { zh: '规则 {ruleId} 不存在。', en: 'There is no rule with id {ruleId}.' },
  'api.conversation_not_found': { zh: '会话 {sessionId} 不存在。', en: 'There is no conversation {sessionId}.' },
  'api.workflow_not_found': { zh: '工作流 {workflowId} 不存在。', en: 'There is no workflow with id {workflowId}.' },
  'api.backup_not_found': { zh: '备份文件 {name} 不存在。', en: 'There is no backup archive named {name}.' },
  'api.knowledge_entry_not_found': { zh: '知识条目 {entryId} 不存在。', en: 'There is no knowledge entry with id {entryId}.' },

  'api.object_not_bound_to_source': {
    zh: '{objectCode} 还没有绑定可用的数据源，因此读不到实例。',
    en: '{objectCode} is not bound to a usable data source, so its instances cannot be read.',
  },
  'api.object_not_bound_to_table': {
    zh: '{objectCode} 还没有绑定来源表，判定缺少数据依据。',
    en: '{objectCode} is not bound to a source table, so a verdict has no data to rest on.',
  },
  'api.source_table_not_scanned': {
    zh: '这张表没有扫描过，或者不属于当前数据源。请在数据源详情页重新扫描后再试。',
    en: 'That table has not been scanned, or does not belong to this data source. Rescan the source and try again.',
  },
  'api.no_objects_modelled': {
    zh: '还没有建模任何业务对象。请先接入数据源并生成本体草案。',
    en: 'No business objects have been modelled yet. Connect a data source and generate an ontology draft first.',
  },

  'api.publish_needs_confirmed_mappings': {
    zh: '还有语义映射没有确认，不能发布本体——已发布的模型会成为判定的依据。',
    en: 'Some semantic mappings are still unconfirmed, so this ontology cannot be published: a published model becomes the basis for verdicts.',
  },
  'api.published_mappings_immutable': {
    zh: '这份本体已经发布，它的语义映射不能再直接审核。请派生新版本后再改。',
    en: 'This ontology is published, and its mappings can no longer be reviewed in place. Derive a new version and change that.',
  },
  'api.published_rules_immutable': {
    zh: '这份本体已经发布，它的规则不能再直接修改。请派生新版本后再改。',
    en: 'This ontology is published, and its rules can no longer be edited in place. Derive a new version and change that.',
  },
  'api.published_rules_undeletable': {
    zh: '这份本体已经发布，它的规则不能再直接删除。请派生新版本后再删。',
    en: 'This ontology is published, and its rules can no longer be deleted in place. Derive a new version and remove them there.',
  },
  'api.published_knowledge_immutable': {
    zh: '这份本体已经发布，不能再往里添加知识条目。请派生新版本后再加。',
    en: 'This ontology is published, so no knowledge entries can be added to it. Derive a new version and add them there.',
  },
  'api.published_cannot_regenerate': {
    zh: '「{name}」已经发布，重新生成草案会覆盖一份正在被引用的模型。请改为派生新版本。',
    en: '“{name}” is already published, and regenerating the draft would overwrite a model that decisions cite. Derive a new version instead.',
  },
  'api.derive_requires_published': {
    zh: '只有已发布的本体才能派生新版本——草案是重新生成的对象。',
    en: 'Only a published ontology can be derived into a new version; a draft is regenerated instead.',
  },

  'api.workflow_not_configured': {
    zh: '这个业务对象还没有配置工作流。请先在工作流页为它定义一个状态机。',
    en: 'This business object has no workflow yet. Define a state machine for it on the workflow page first.',
  },
  'api.instance_not_in_workflow': {
    zh: '这个实例还没有进入该工作流，因此没有可执行的状态迁移。',
    en: 'This instance has not entered that workflow, so it has no transition to run.',
  },

  'api.mappings_still_pending': { zh: '还有 {count} 条语义映射没有审核，不能发布本体——已发布的模型会成为判定的依据。', en: 'Some {count} semantic mappings are still unreviewed, so this ontology cannot be published: a published model becomes the basis for verdicts.' },
  'api.ontology_not_publishable': { zh: '本体当前是「{status}」状态，不能发布。', en: 'An ontology in the “{status}” state cannot be published.' },
  'api.ontology_version_exists': { zh: '{name} 的 {version} 已经存在，不能重复生成。', en: '{name} already has a {version}.' },
  'api.release_gate_blocked': { zh: '发布门禁未通过：{count} 项阻断。{detail}', en: 'The release gate has {count} blocking findings. {detail}' },
  'api.mapping_not_found': { zh: '语义映射 {mappingId} 不存在。', en: 'There is no semantic mapping with id {mappingId}.' },
  'api.rule_scope_object_not_found': { zh: '规则要挂在业务对象 {objectCode} 上，但这个对象不存在。', en: 'The rule names business object {objectCode}, which does not exist.' },
  'api.rule_type_unsupported': { zh: '不支持的规则类型 {ruleType}。', en: '“{ruleType}” is not a rule type this build knows.' },
  'api.rule_severity_unsupported': { zh: '不支持的规则严重级别 {severity}。', en: '“{severity}” is not a rule severity this build knows.' },
  'api.rule_expression_not_executable': { zh: '规则表达式无法求值：{expression}', en: 'This rule expression cannot be evaluated: {expression}' },
  'api.rule_override_not_superior': { zh: '只能覆盖上级类型的规则：{ruleCode} 属于 {objectCode}，不在 {scopeObjectCode} 的上级链（{ancestors}）中。', en: 'A rule can only override one from a supertype: {ruleCode} belongs to {objectCode}, which is not above {scopeObjectCode} (the chain is {ancestors}).' },
  'api.rule_override_self': { zh: '规则 {ruleCode} 不能覆盖自身。', en: 'Rule {ruleCode} cannot override itself.' },
  'api.rule_overridden_missing': { zh: '被 {ruleCode} 覆盖的那条规则不存在。', en: 'The rule {ruleCode} overrides does not exist.' },
  'api.aggregation_immutable': { zh: '这份本体已经发布，它的聚合定义不能再改。请派生新版本后再改。', en: 'This ontology is published, and its aggregation definitions can no longer be changed in place. Derive a new version and change them there.' },
  'api.derived_attribute_immutable': { zh: '这份本体已经发布，它的派生属性不能再改。请派生新版本后再改。', en: 'This ontology is published, and its derived attributes can no longer be changed in place. Derive a new version and change them there.' },
  'api.unit_immutable': { zh: '这份本体已经发布，属性的单位不能再改。请派生新版本后再改。', en: 'This ontology is published, and attribute units can no longer be changed in place. Derive a new version and change them there.' },
  'api.cross_source_immutable': { zh: '这份本体已经发布，它的跨源对应不能再改。请派生新版本后再改。', en: 'This ontology is published, and its cross-source links can no longer be changed in place. Derive a new version and change them there.' },
  'api.event_type_immutable': { zh: '这份本体已经发布，它的事件定义不能再改。请派生新版本后再改。', en: 'This ontology is published, and its event definitions can no longer be changed in place. Derive a new version and change them there.' },
  'api.instance_resolver_immutable': { zh: '这份本体已经发布，它的实例解析器不能再改。请派生新版本后再改。', en: 'This ontology is published, and its instance resolvers can no longer be changed in place. Derive a new version and change them there.' },
  'api.type_hierarchy_immutable': { zh: '这份本体已经发布，它的类型层级不能再改。请派生新版本后再改。', en: 'This ontology is published, and its type hierarchy can no longer be changed in place. Derive a new version and change it there.' },
  'api.value_mapping_immutable': { zh: '这份本体已经发布，它的值域映射不能再改。请派生新版本后再改。', en: 'This ontology is published, and its value-domain mappings can no longer be changed in place. Derive a new version and change them there.' },
  'api.source_directory_required': { zh: '文件数据源需要一个目录路径，不能是单个文件。', en: 'A file data source takes a directory, not a single file.' },
  'api.source_directory_missing': { zh: '目录 {path} 不存在。', en: 'There is no directory at {path}.' },
  'api.source_file_missing': { zh: '在 {directory} 里找不到 {filename}——请确认表名与文件名的对应关系。', en: '{directory} has no {filename} in it; check that the table name matches the file name.' },
  'api.mysql_uri_format': { zh: 'MySQL 连接串应写成 mysql://user:password@host:port/database。', en: 'A MySQL connection string is written mysql://user:password@host:port/database.' },
  'api.openapi_paths_missing': { zh: '这份 OpenAPI 文档里没有 paths 对象，读不出任何接口。', en: 'That OpenAPI document has no paths object, so it describes no endpoints.' },
  'api.openapi_url_invalid': { zh: 'OpenAPI 地址必须是 HTTP 或 HTTPS 地址。', en: 'An OpenAPI URL has to be an http:// or https:// address.' },
  'api.openapi_url_not_json': { zh: '这个地址返回的内容不是有效 JSON，无法当作 OpenAPI 文档解析。', en: 'That address did not return valid JSON, so it cannot be read as an OpenAPI document.' },
  'api.test_connection_input_required': { zh: '测试一个尚未登记的数据源时，必须同时给出类型与连接串。', en: 'Testing a data source that has not been registered yet needs both its type and its connection string.' },
  'api.upload_format_unsupported': { zh: '只支持 .docx 或 UTF-8 文本文件。', en: 'Only .docx files and UTF-8 text files are accepted.' },
  'api.document_title_required': { zh: '请填写文档标题。', en: 'Give the document a title.' },
  'api.document_already_imported': { zh: '这份文档的内容已经导入过（文档 #{documentId}），不用重复上传。', en: 'This document’s content is already in the knowledge base (document #{documentId}), so there is no need to upload it again.' },
  'api.word_no_rules_found': { zh: '没有从这份 Word 文档里识别出规则。建议表头为：规则编码、规则名称、适用对象、规则类型、规则表达式、严重程度、自然语言说明。', en: 'No rules were recognised in that Word document. The expected header row is: rule code, rule name, object, rule type, expression, severity, natural-language description.' },
  'api.word_not_a_docx': { zh: '这不是一个有效的 .docx 文件。常见原因是把别的格式改了扩展名，或上传时被截断；请用 Word／WPS 另存为 .docx 再试。', en: 'That is not a valid .docx. Usually the file is another format renamed, or it was truncated during upload; save it again as .docx from Word or WPS and retry.' },
  'api.word_support_missing': { zh: '服务端没有安装 python-docx，无法解析 Word 规则文档。请在服务端安装 requirements.txt。', en: 'The server does not have python-docx installed, so it cannot read Word rule documents. Install requirements.txt on the server.' },
  'api.scope_object_required': { zh: '确认一条知识条目前，必须指明它锚定在哪个业务对象或规则上——没有锚点的条款无法参与判定。', en: 'Before confirming a knowledge entry, say which business object or rule it anchors to: a clause with no anchor cannot take part in a verdict.' },
  'api.no_ontology_to_explain': { zh: '还没有生成过本体，无从解释实例。请先接入数据源并生成草案。', en: 'No ontology has been generated yet, so there is nothing to explain. Connect a data source and generate a draft first.' },
  'api.data_source_not_ready': { zh: '请选择一个已完成初始化的数据源。', en: 'Choose a data source that has been initialised.' },
  'api.instance_hint_required': { zh: '请说明要解释哪个实例，例如：{example}', en: 'Say which instance to explain, for example: {example}' },
  'api.model_key_missing': { zh: '还没有配置模型 API Key，无法调用远程模型。', en: 'No model API key is configured, so a remote model cannot be called.' },
  'api.model_auth_style_unsupported': { zh: '不支持的鉴权方式 {authStyle}；可选：{supported}。', en: '“{authStyle}” is not an authentication style this build knows; the options are {supported}.' },
  'api.model_auth_header_required': { zh: '鉴权方式选自定义时，必须填写鉴权请求头的名称。', en: 'A custom authentication style needs the header name to be filled in.' },
  'api.model_response_not_json': { zh: '模型没有返回 JSON 对象，无法解析这次调用。', en: 'The model did not return a JSON object, so this call could not be parsed.' },
  'api.tenant_id_required': { zh: '租户标识不能为空。', en: 'A tenant identifier is required.' },
  'api.tenant_id_invalid': { zh: '租户标识 {tenant} 不合法：只能以小写字母开头，用字母、数字与下划线，最长 39 个字符。', en: '“{tenant}” is not a valid tenant identifier: it starts with a lowercase letter, uses letters, digits and underscores, and is at most 39 characters.' },
  'api.quota_resource_unknown': { zh: '未知的配额资源 {resource}；可用的有：{supported}。', en: '“{resource}” is not a limitable resource; the available ones are {supported}.' },
  'api.quota_limit_negative': { zh: '配额上限不能是负数（收到 {limit}）。', en: 'A quota limit cannot be negative (received {limit}).' },
  'api.cross_tenant_access': { zh: '检测到跨租户的数据访问：期望 {expected}，实际 {actual}。这次操作已被阻止。', en: 'A cross-tenant data access was detected: {expected} was expected, {actual} arrived. The operation was blocked.' },
  'api.sso_group_required': { zh: '提供方组名不能为空。', en: 'The provider group name is required.' },
  'api.sso_role_unknown': { zh: '未知的平台角色 {roleCode}；可选：{supported}。', en: '“{roleCode}” is not a platform role; the options are {supported}.' },
  'api.sso_mapping_missing': { zh: '组映射 {providerGroup} 不存在。', en: 'There is no group mapping for {providerGroup}.' },
  'api.sso_identity_unmapped': { zh: '身份 {subject} 所在的组没有映射到任何平台角色，因此被拒绝。请由平台管理员声明组到角色的映射——未映射就是没有权限，不会给一个默认角色。', en: 'The groups of identity {subject} map to no platform role, so it was refused. A platform administrator has to declare the group-to-role mapping: unmapped means no access, not a default role.' },
  'api.sso_not_enabled': { zh: '单点登录尚未启用，缺少配置：{missing}。', en: 'Single sign-on is not enabled; it is missing {missing}.' },
  'api.sso_algorithm_unsupported': { zh: '不支持的签名算法 {algorithm}；可选：{supported}。', en: '“{algorithm}” is not a supported signing algorithm; the options are {supported}.' },
  'api.sso_assertion_expired': { zh: '这份断言已经过期。', en: 'That assertion has expired.' },
  'api.sso_assertion_no_expiry': { zh: '断言里没有 exp，不接受永不过期的凭据。', en: 'The assertion has no exp, and a credential that never expires is not accepted.' },
  'api.sso_assertion_malformed': { zh: '断言格式不对：应当是三段式的 JWT。', en: 'That assertion is malformed: a JWT has three segments.' },
  'api.sso_signature_invalid': { zh: '断言签名校验失败，这份凭据不是签发方给出的。', en: 'The assertion’s signature did not verify, so this credential did not come from the issuer.' },
  'api.sso_issuer_mismatch': { zh: '签发方不匹配：收到 {issuer}。', en: 'The issuer does not match: got {issuer}.' },
  'api.sso_audience_mismatch': { zh: '受众不匹配：收到 {audience}。', en: 'The audience does not match: got {audience}.' },
  'api.instance_already_in_workflow': { zh: '实例 {instanceId} 已经在工作流里了。', en: 'Instance {instanceId} is already in the workflow.' },
  'api.transition_not_allowed': { zh: '当前状态「{fromState}」不允许执行动作「{actionCode}」。', en: 'The state “{fromState}” does not allow the action “{actionCode}”.' },
  'api.guard_rejected': { zh: '流转守卫没有通过，动作「{actionCode}」被拦下：{reason}', en: 'A transition guard rejected the action “{actionCode}”: {reason}' },
  'api.unsupported_status': { zh: '不支持的状态：{status}。', en: '“{status}” is not a status this build knows.' },
  'api.rule_function_not_allowed': { zh: '规则表达式只允许使用 {allowed} 这些函数。', en: 'A rule expression may only use these functions: {allowed}.' },
  'api.migration_failed': { zh: '迁移 {version}（{description}）执行失败，后续迁移没有执行：{reason}', en: 'Migration {version} ({description}) failed, and the migrations after it did not run: {reason}' },
  'api.scaffold_project_name_invalid': { zh: '项目名 {name} 不合法：需以小写字母开头，2–40 位小写字母／数字／下划线（它会成为 Python 包名）。', en: '“{name}” is not a valid project name: it starts with a lowercase letter and uses 2–40 lowercase letters, digits or underscores (it becomes the Python package name).' },
  'api.scaffold_files_exist': { zh: '这些文件已经存在，没有做任何改动：{files}。请生成到新目录再对比合并——脚手架不会覆盖既有代码。', en: 'These files already exist and nothing was changed: {files}. Generate into a new directory and merge by hand; the scaffold does not overwrite existing code.' },
  'api.scaffold_extension_unknown': { zh: '未知的扩展点 {extension}；可选：{supported}。', en: '“{extension}” is not an extension point; the options are {supported}.' },

  'api.question_required': { zh: '请先输入要问的问题。', en: 'Enter a question first.' },
  'api.file_name_required': { zh: '请选择要上传的文件。', en: 'Choose a file to upload.' },
  'api.file_content_empty': { zh: '这个文件是空的，没有可以解析的内容。', en: 'That file is empty, so there is nothing to parse.' },

  'api.aggregate_name_invalid': {
    zh: '聚合名必须是合法标识符: {name}（规则表达式要按此名引用它）',
    en: 'An aggregate name has to be a valid identifier, because a rule expression refers to it by name; got “{name}”.',
  },
  'api.aggregate_name_underscore': {
    zh: '聚合名不能以下划线开头，避免与沙箱内部名冲突',
    en: 'An aggregate name cannot start with an underscore: names beginning with `_` are reserved for the rule sandbox’s own internals.',
  },
  'api.aggregate_function_unsupported': {
    zh: '不支持的聚合函数: {name}。可选: {supported}',
    en: '“{name}” is not an aggregate function this build knows. The available ones are {supported}.',
  },
  'api.aggregate_value_column_required': {
    zh: '{name} 聚合必须指定 valueColumn',
    en: 'An aggregate of kind “{name}” has to say which column to aggregate — `valueColumn` is required.',
  },
  'api.aggregate_self_column_required': {
    zh: 'excludeSelf 为真时必须指定 selfColumn',
    en: 'With `excludeSelf` set, `selfColumn` has to say which column holds the instance being excluded.',
  },
  'api.axiom_code_required': {
    zh: '公理编码不能为空',
    en: 'An axiom needs a code.',
  },
  'api.axiom_kind_unknown': {
    zh: '未知公理类型 {kind}，支持: {supported}',
    en: '“{kind}” is not an axiom kind this build knows. The supported ones are {supported}.',
  },
  'api.axiom_subject_required': {
    zh: '公理主体不能为空',
    en: 'An axiom needs a subject — the object or relation it is about.',
  },
  'api.axiom_operand_required': {
    zh: '{kind} 需要两个操作数，object 不能为空',
    en: '“{kind}” takes two operands, and the object one is empty.',
  },
  'api.axiom_operands_identical': {
    zh: '{kind} 的两个操作数不能相同: {operand}',
    en: '“{kind}” cannot take the same value twice; both operands are {operand}.',
  },
  'api.axiom_not_found': {
    zh: '公理不存在: {axiomCode}',
    en: 'There is no axiom named {axiomCode}.',
  },
  'api.axiom_reference_format': {
    zh: '属性引用需为 对象编码.属性编码 形式: {reference}',
    en: 'An attribute reference is written `objectCode.attributeCode`; got “{reference}”.',
  },
  'api.axiom_reference_incomplete': {
    zh: '属性引用不完整: {reference}',
    en: 'That attribute reference is incomplete: {reference}',
  },
  'api.axiom_relation_not_found': {
    zh: '业务关系不存在: {relationCode}',
    en: 'There is no business relation named {relationCode}.',
  },
  'api.axiom_attribute_not_found': {
    zh: '业务属性不存在: {reference}',
    en: 'There is no business attribute named {reference}.',
  },
  'api.axiom_exclusive_same_object': {
    zh: '互斥属性必须属于同一对象: {first} / {second}',
    en: 'Mutually exclusive attributes have to belong to the same object; {first} and {second} do not.',
  },
  'api.writeback_semicolon_forbidden': {
    zh: '{name}不允许包含分号（多语句会绕过单语句审计）',
    en: '{name} may not contain a semicolon: more than one statement would bypass the per-statement audit.',
  },
  'api.writeback_statement_forbidden': {
    zh: '{name}不允许使用 {statement}：自动化用于推进业务状态，不用于变更结构或权限',
    en: '{name} may not use {statement}: automation exists to advance business state, not to change structure or permissions.',
  },
  'api.writeback_name_invalid': {
    zh: '写回名称必须是字母数字、下划线或连字符: {name}',
    en: 'A writeback name has to be letters, digits, underscores or hyphens; got “{name}”.',
  },
  'api.writeback_kind_unsupported': {
    zh: '不支持的写回类型: {kind}。可选: {supported}',
    en: '“{kind}” is not a writeback kind this build knows. The available ones are {supported}.',
  },
  'api.writeback_delete_not_allowed': {
    zh: '{name}: 删除类写回必须显式设置 allowDelete=True。自动化用于推进业务状态，销毁数据需要单独的授权决定。',
    en: 'A delete-class writeback for “{name}” has to set `allowDelete=True` explicitly. Automation exists to advance business state; destroying data needs a separate authorisation decision.',
  },
  'api.writeback_procedure_required': {
    zh: '{name}: call 类写回必须指定 procedure',
    en: 'A call-class writeback for “{name}” has to name its procedure.',
  },
  'api.writeback_param_name_invalid': {
    zh: '{name}: 参数名必须是合法标识符: {parameter}',
    en: '{name}: a parameter name has to be a valid identifier; got “{parameter}”.',
  },
  'api.writeback_table_required': {
    zh: '{name}: 结构化写回必须指定 table',
    en: 'A structured writeback for “{name}” has to name its table.',
  },
  'api.writeback_columns_required': {
    zh: '{name}: {kind} 写回必须指定 columns',
    en: 'A {kind} writeback for “{name}” has to declare its columns.',
  },
  'api.writeback_key_columns_required': {
    zh: '{name}: {kind} 写回必须指定 keyColumns。缺少 WHERE 条件的更新会改写整张表，且事后无法从判定记录看出这一点。',
    en: 'A {kind} writeback for “{name}” has to declare `keyColumns`. An update without a WHERE clause rewrites the whole table, and afterwards the decision record cannot show that it happened.',
  },
  'api.writeback_where_required': {
    zh: '{name}: UPDATE／DELETE 语句必须包含 WHERE 条件，否则会作用于整张表。',
    en: '{name}: an UPDATE or DELETE has to carry a WHERE clause, or it acts on the whole table.',
  },
  'api.writeback_param_missing': {
    zh: '{name}: 缺少参数 {parameter}。写回不会用 NULL 代替缺失值。',
    en: '{name}: the parameter {parameter} is missing. A writeback will not substitute NULL for a value that was not supplied.',
  },
  'api.writeback_param_missing_bare': {
    zh: '缺少参数 {parameter}。写回不会用 NULL 代替缺失值。',
    en: 'The parameter {parameter} is missing. A writeback will not substitute NULL for a value that was not supplied.',
  },
  'api.writeback_scheme_invalid': {
    zh: '写回 scheme 必须是字母数字或下划线: {scheme}',
    en: 'A writeback scheme has to be letters, digits or underscores; got “{scheme}”.',
  },
  'api.writeback_uri_required': {
    zh: '{scheme}: 必须提供连接串',
    en: '{scheme} has to provide a connection string.',
  },
  'api.writeback_driver_required': {
    zh: '{scheme}: 必须指定驱动模块',
    en: '{scheme} has to declare its driver module.',
  },
  'api.writeback_undeclared': {
    zh: '{name}: 未声明的写回 {operation}。已声明: {declared}。写回语句必须预先声明，不能由请求构造。',
    en: '{name}: the writeback {operation} is not declared. Declared: {declared}. A writeback statement has to be declared in advance; it cannot be built from a request.',
  },
  'api.writeback_driver_missing': {
    zh: '{scheme}: 写回需要安装驱动 {module}',
    en: 'The writeback channel {scheme} needs the {module} driver installed.',
  },
  'api.writeback_failed': {
    zh: '{objectCode}/{instanceId}: 写回失败: {detail}',
    en: 'Writeback failed for {objectCode}/{instanceId}: {detail}',
  },
  'api.writeback_no_rows': {
    zh: '{objectCode}/{instanceId}: 语句执行成功但影响 0 行，目标实例可能不存在或条件不匹配。',
    en: '{objectCode}/{instanceId}: the statement ran but affected 0 rows, so the target instance may not exist or the condition did not match.',
  },
  'api.writeback_channel_exists': {
    zh: '写回通道已存在: {scheme}。要覆盖请显式传 replace=True。',
    en: 'The writeback channel {scheme} already exists. To replace it, pass `replace=True` explicitly.',
  },
  'api.unit_code_invalid': {
    zh: '单位编码必须是合法标识符: {unitCode}',
    en: 'A unit code has to be a valid identifier; got “{unitCode}”.',
  },
  'api.unit_factor_invalid': {
    zh: '单位换算系数必须为正数: {factor}',
    en: 'A unit conversion factor has to be positive; got {factor}.',
  },
  'api.unit_exists': {
    zh: '单位已存在: {unitCode}。要覆盖请显式传 replace=True。',
    en: 'The unit {unitCode} already exists. To replace it, pass `replace=True` explicitly.',
  },
  'api.unit_unknown': {
    zh: '未知单位: {unitCode}。已登记: {known}',
    en: 'There is no unit named {unitCode}. Registered: {known}.',
  },
  'api.unit_dimension_mismatch': {
    zh: '无法在不同量纲间换算: {from}（{fromDimension}）→ {to}（{toDimension}）。这通常意味着建模有误，而不是需要换算。',
    en: 'Cannot convert between dimensions: {from} ({fromDimension}) to {to} ({toDimension}). That usually means the model is wrong rather than that a conversion is needed.',
  },
  'api.derived_code_invalid': {
    zh: '派生属性编码必须是合法标识符: {name}（规则要按此名引用它）',
    en: 'A derived attribute code has to be a valid identifier, because a rule refers to it by name; got “{name}”.',
  },
  'api.derived_code_underscore': {
    zh: '派生属性编码不能以下划线开头，避免与沙箱内部名冲突',
    en: 'A derived attribute code cannot start with an underscore: names beginning with `_` are reserved for the rule sandbox’s own internals.',
  },
  'api.derived_expression_invalid': {
    zh: '派生表达式不可执行: {expression}',
    en: 'That derived expression cannot be evaluated: {expression}',
  },
  'api.derived_column_conflict': {
    zh: '属性 {attributeCode} 已绑定来源列，不能改为派生属性。请换一个编码，或先解除映射。',
    en: 'Attribute {attributeCode} is bound to a source column, so it cannot become derived. Use a different code, or lift the mapping first.',
  },
  'api.derived_attribute_not_found': {
    zh: '属性不存在: {objectCode}.{attributeCode}',
    en: 'There is no attribute {objectCode}.{attributeCode}.',
  },
  'api.cross_source_name_invalid': {
    zh: '跨源对应名称必须是合法标识符: {name}',
    en: 'A cross-source link name has to be a valid identifier; got “{name}”.',
  },
  'api.cross_source_object_required': {
    zh: '{name}: 必须指定主源业务对象',
    en: '{name} has to name the primary business object.',
  },
  'api.cross_source_source_required': {
    zh: '{name}: 必须指定副源数据源 id',
    en: '{name} has to name the secondary data source id.',
  },
  'api.cross_source_match_required': {
    zh: '{name}: 必须声明至少一个匹配列对。跨源判定会把「这两行是同一实例」写进判定链，因此它必须是声明的，不能是推断的。',
    en: '“{name}” has to declare at least one pair of matching columns. A cross-source verdict records “these two rows are the same instance” in the decision trail, so it has to be declared rather than inferred.',
  },
  'api.cross_source_conflict_unsupported': {
    zh: '{name}: 不支持的冲突策略 {strategy}。可选: {supported}',
    en: '{name} does not declare a conflict strategy this build knows: “{strategy}”. The available ones are {supported}.',
  },
  'api.cross_source_object_not_found': {
    zh: '主源业务对象不存在: {objectCode}',
    en: 'There is no business object named {objectCode} on the primary source.',
  },
  'api.cross_source_source_not_found': {
    zh: '副源数据源不存在: {dataSourceId}',
    en: 'There is no data source with id {dataSourceId} on the secondary side.',
  },
  'api.cross_source_value_conflict': {
    zh: '字段 {field} 在两个数据源中取值不同（主源={primary}，副源={secondary}），无法参与比较。请在跨源对应中声明冲突策略，或修正源数据。',
    en: '“{field}” holds different values in the two sources (primary={primary}, secondary={secondary}), so it cannot take part in the comparison. Declare a conflict strategy for it, or correct the source data.',
  },
  'api.event_code_invalid': {
    zh: '事件编码必须是合法标识符: {eventCode}',
    en: 'An event code has to be a valid identifier; got “{eventCode}”.',
  },
  'api.event_name_required': {
    zh: '事件名称不能为空',
    en: 'An event needs a name.',
  },
  'api.event_category_unsupported': {
    zh: '不支持的事件类别: {category}。可选: {supported}',
    en: '“{category}” is not an event category this build knows. The available ones are {supported}.',
  },
  'api.event_payload_field_invalid': {
    zh: '载荷字段名必须是合法标识符: {field}',
    en: 'A payload field name has to be a valid identifier; got “{field}”.',
  },
  'api.event_type_undeclared': {
    zh: '未声明的事件类型: {objectCode}.{eventCode}。请先声明事件类型，否则历史将无法按类型检索。',
    en: 'The event type {objectCode}.{eventCode} has not been declared. Declare it first, or the history cannot be searched by type.',
  },
  'api.sql_source_type_invalid': {
    zh: '数据源类型必须是字母数字或下划线: {sourceType}',
    en: 'A data source type has to be letters, digits or underscores; got “{sourceType}”.',
  },
  'api.sql_driver_not_declared': {
    zh: '{sourceType} 未声明驱动模块',
    en: '{sourceType} does not declare a driver module.',
  },
  'api.sql_driver_no_connect': {
    zh: '驱动 {module} 没有 {attribute}()，无法建立连接。',
    en: 'The driver {module} has no {attribute}(), so a connection cannot be made.',
  },
  'api.resolver_identifier_invalid': {
    zh: '{kind}不合法: {value}。只允许字母或下划线开头的字母、数字、下划线，最长 64 字符。',
    en: 'That {kind} is not usable: “{value}”. Only letters, digits and underscores are allowed, starting with a letter or underscore, up to 64 characters.',
  },
  'api.resolver_joins_required': {
    zh: 'joined_tables 解析器至少需要一个 joins 配置',
    en: 'A `joined_tables` resolver needs at least one join.',
  },
  'api.resolver_discriminator_required': {
    zh: 'discriminated 解析器必须指定判别值',
    en: 'A `discriminated` resolver has to say which value it discriminates on.',
  },
  'api.resolver_query_required': {
    zh: 'custom_sql 解析器必须提供 query',
    en: 'A `custom_sql` resolver has to provide its query.',
  },
  'api.resolver_query_kind': {
    zh: 'custom_sql 只允许 select 或 with 查询',
    en: 'A `custom_sql` resolver may only run a `select` or a `with` query.',
  },
  'api.resolver_query_semicolon': {
    zh: 'custom_sql 不允许包含分号',
    en: 'A `custom_sql` query may not contain a semicolon.',
  },
  'api.resolver_custom_unsupported': {
    zh: '运行时不支持自定义查询',
    en: 'The runtime does not support custom queries.',
  },
  'api.word_support_missing_bare': {
    zh: '解析 Word 文档需要安装 python-docx。',
    en: 'Reading Word documents needs python-docx installed.',
  },
  'api.registry_name_required': {
    zh: '{kind}的名称不能为空',
    en: 'A {kind} needs a name.',
  },
  'api.registry_name_taken': {
    zh: '{kind} ‘{name}’ 已被占用。如确实要覆盖，请显式传入 replace=True。',
    en: 'That {kind} name, “{name}”, is already taken. To replace it, pass `replace=True` explicitly.',
  },
  'api.registry_kind_unsupported': {
    zh: '不支持的{kind}: {name}。当前已注册: {registered}',
    en: '“{name}” is not a {kind} this build knows. Currently registered: {registered}.',
  },
  'api.rest_resource_name_invalid': {
    zh: '资源名必须是字母数字或下划线: {name}',
    en: 'A resource name has to be letters, digits or underscores; got “{name}”.',
  },
  'api.rest_list_path_invalid': {
    zh: '{name} 的 listPath 必须以 / 开头: {path}',
    en: '`listPath` for {name} has to start with `/`; got “{path}”.',
  },
  'api.rest_fields_required': {
    zh: '{name} 必须声明字段列表：REST 响应没有可供发现的模式',
    en: '“{name}” has to declare its fields: a REST response has no schema to discover them from.',
  },
  'api.rest_key_not_declared': {
    zh: '{name} 的主键 {key} 不在已声明字段中',
    en: 'The primary key {key} of “{name}” is not among its declared fields.',
  },
  'api.rest_resources_required': {
    zh: '{name} 未声明任何资源',
    en: '“{name}” declares no resources.',
  },
  'api.rest_resource_duplicate': {
    zh: '{name} 存在重名资源: {duplicates}',
    en: '“{name}” declares the same resource twice: {duplicates}',
  },
  'api.rest_resource_undeclared': {
    zh: '未声明的资源: {name}。已声明: {declared}',
    en: '“{name}” is not a declared resource. Declared: {declared}.',
  },
  'api.rest_items_path_missing': {
    zh: '响应中找不到 itemsPath 片段 {path}',
    en: 'The response has no fragment at `itemsPath`: {path}',
  },
  'api.rest_response_not_list': {
    zh: '响应不是对象列表: {detail}',
    en: 'The response is not a list of objects: {detail}',
  },
  'api.rest_request_failed_status': {
    zh: '请求 {operation} 返回 {status}: {detail}',
    en: '{operation} returned {status}: {detail}',
  },
  'api.rest_request_failed': {
    zh: '请求 {operation} 失败: {detail}',
    en: 'The request for {operation} failed: {detail}',
  },
  'api.rest_response_not_json': {
    zh: '{name} 返回的不是 JSON',
    en: '{name} did not return JSON.',
  },
  'api.rest_no_collection_endpoint': {
    zh: 'OpenAPI 文档中没有可用于声明的集合端点（需要返回对象数组的 GET 端点）。请手工声明 RestResource。',
    en: 'That OpenAPI document has no collection endpoint a declaration could use — it needs a GET that returns an array of objects. Declare a `RestResource` by hand instead.',
  },
  'api.rule_function_name_invalid': {
    zh: '规则函数名必须是合法标识符: {name}',
    en: 'A rule function name has to be a valid identifier; got “{name}”.',
  },
  'api.rule_function_name_underscore': {
    zh: '规则函数名不能以下划线开头，避免与沙箱内部名冲突: {name}',
    en: 'A rule function name cannot start with an underscore: {name}',
  },
  'api.rule_function_not_callable': {
    zh: '规则函数 {name} 必须可调用',
    en: 'The rule function {name} has to be callable.',
  },
  'api.rule_expression_node_forbidden': {
    zh: '不允许的规则表达式节点: {node}',
    en: 'A rule expression may not use that construct: {node}',
  },
  'api.rule_function_no_kwargs': {
    zh: '规则函数不支持关键字参数',
    en: 'Rule functions do not take keyword arguments.',
  },
  'api.rule_expression_attribute_forbidden': {
    zh: '不允许访问内部属性: {attribute}',
    en: 'That attribute cannot be reached from a rule expression: {attribute}',
  },
  'api.dialect_name_invalid': {
    zh: '方言名必须是字母数字或下划线: {name}',
    en: 'A dialect name has to be letters, digits or underscores; got “{name}”.',
  },
  'api.dialect_paramstyle_unsupported': {
    zh: '不支持的参数风格: {style}。可选: format、qmark、numeric',
    en: '“{style}” is not a parameter style this build knows. The available ones are `format`, `qmark` and `numeric`.',
  },
  'api.dialect_paging_unsupported': {
    zh: '不支持的分页风格: {style}。可选: limit_offset、fetch_first',
    en: '“{style}” is not a paging style this build knows. The available ones are `limit_offset` and `fetch_first`.',
  },
  'api.dialect_quote_required': {
    zh: '标识符引号不能为空',
    en: 'A dialect needs an identifier quote character.',
  },
  'api.dialect_exists': {
    zh: '方言已存在: {name}。要覆盖请显式传 replace=True。',
    en: 'The dialect {name} already exists. To replace it, pass `replace=True` explicitly.',
  },
  'api.dialect_unknown': {
    zh: '未知 SQL 方言: {name}。已登记: {registered}',
    en: 'There is no SQL dialect named “{name}”. Registered: {registered}.',
  },
  'api.moment_required': {
    zh: '{what}不能为空',
    en: '{what} cannot be empty.',
  },
  'api.moment_unparseable': {
    zh: '无法解析{what}: {value}。请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS。',
    en: 'Cannot read {what} from “{value}”. Use `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`.',
  },
  'api.temporal_schema_missing': {
    zh: '时态表尚未创建，请先运行 init_temporal_schema()。',
    en: 'The temporal tables have not been created. Run `init_temporal_schema()` first.',
  },
  'api.hierarchy_self_parent': {
    zh: '对象不能是自身的子类型: {objectCode}',
    en: 'An object cannot be its own supertype: {objectCode}.',
  },
  'api.hierarchy_too_deep': {
    zh: '类型层级超过 {depth} 层，请检查是否存在环。',
    en: 'The type hierarchy is more than {depth} levels deep. That usually means there is a cycle.',
  },
  'api.value_mapping_raw_required': {
    zh: '原始值不能为空',
    en: 'A value mapping needs the raw value.',
  },
  'api.value_mapping_state_required': {
    zh: '语义状态名不能为空',
    en: 'A value mapping needs the semantic state it maps to.',
  },

  // -- Refusals an operator meets, not a developer ---------------------------------------------
  //
  // These were the tail of the unregistered set, and the readiness page claimed all of it
  // "fires only when the platform itself is misassembled". Reading them showed most were the
  // opposite: a .doc upload on a host without LibreOffice, a malformed backup archive, a broken
  // SSO assertion. What is left after this batch really is the misassembly set.
  'api.audit_period_required': {
    zh: '审计报表必须给出起止时间：覆盖范围不明的报表无法作为审计依据。',
    en: 'An audit report needs a start and an end. A report that does not say what period it covers cannot serve as audit evidence.',
  },
  'api.backup_config_missing': {
    zh: '缺少 config.json',
    en: 'The backup archive has no config.json in it.',
  },
  'api.backup_database_invalid': {
    zh: '备份中的数据库不是有效的 SQLite 文件',
    en: 'The database inside this backup is not a valid SQLite file.',
  },
  'api.backup_database_missing': {
    zh: '备份中找不到数据库文件',
    en: 'No database file was found inside this backup.',
  },
  'api.backup_name_invalid': {
    zh: '备份名不合法：需为 1-120 位字母／数字／下划线／连字符／点，且以字母或数字开头（不能包含路径分隔符）。',
    en: 'That is not a valid backup name: 1–120 letters, digits, underscores, hyphens or dots, starting with a letter or digit, and no path separators.',
  },
  'api.backup_path_escape': {
    zh: '备份路径不在备份目录内',
    en: 'That backup resolves to a path outside the backup directory.',
  },
  'api.backup_sqlite_only': {
    zh: '内置备份仅支持 SQLite 平台库；服务端数据库请使用其原生备份工具。',
    en: 'The built-in backup covers the SQLite platform database only; back a server database up with its own tooling.',
  },
  'api.decision_value_invalid': {
    zh: 'decision 必须是 approved 或 rejected',
    en: 'A decision is either approved or rejected.',
  },
  'api.document_conversion_timeout': {
    zh: 'LibreOffice 转换超时（30秒），请手动将 .doc 转换为 .docx 格式后重试。',
    en: 'LibreOffice timed out after 30 seconds. Convert the .doc to .docx yourself and upload that.',
  },
  'api.document_converter_missing': {
    zh: '未检测到 LibreOffice，无法自动转换 .doc 文件。请手动将 .doc 另存为 .docx 格式，或安装 LibreOffice 后重试。',
    en: 'LibreOffice was not found, so .doc files cannot be converted automatically. Save the file as .docx and upload that, or install LibreOffice and try again.',
  },
  'api.export_format_unsupported': {
    zh: '仅支持 jsonld 或 turtle 导出格式',
    en: 'That export format is not supported here; use jsonld or turtle.',
  },
  'api.operation_object_unresolved': {
    zh: '无法从业务操作推断业务对象，请显式传入 objectCode',
    en: 'The business object could not be inferred from the operation; pass objectCode explicitly.',
  },
  'api.preflight_data_source_required': {
    zh: '无法定位数据源，不能进行操作预检',
    en: 'The data source could not be located, so the operation cannot be preflighted.',
  },
  'api.preflight_operations_missing': {
    zh: '该数据源尚未登记任何业务操作，无法进行操作预检',
    en: 'This data source has no business operations registered, so there is nothing to preflight.',
  },
  'api.sso_assertion_payload_not_object': {
    zh: '断言载荷不是对象',
    en: 'The identity provider’s assertion payload is not a JSON object.',
  },
  'api.sso_assertion_payload_unparseable': {
    zh: '断言载荷无法解析',
    en: 'The identity provider’s assertion payload could not be parsed.',
  },
  'api.sso_assertion_signature_undecodable': {
    zh: '断言签名无法解码',
    en: 'The identity provider’s assertion signature could not be decoded.',
  },
  'api.writeback_api_base_url_required': {
    zh: '真实执行需要配置业务 API 基址 apiBaseUrl；数据库连接地址仅用于元数据和实例读取。',
    en: 'Executing for real needs a business API base URL (apiBaseUrl). The database connection is used for metadata and instance reads only.',
  },
};