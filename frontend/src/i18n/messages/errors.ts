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
};
